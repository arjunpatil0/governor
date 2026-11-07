"""v2 foreground: YOLOv8 inference at a fixed rate (default 30 FPS) over a fixed video file, on an ABSOLUTE schedule (frame k is due at t0 + k/fps whatever happened before).
A late frame is recorded as late and the next frame starts at once: frames are never skipped and the schedule is never re-timed, so lateness shows up as latency (no coordinated omission).
Each frame record: t_sched, t_start, t_end (QPC seconds, time.perf_counter), lat_ms = t_end - t_sched, gpu_ms = CUDA-event time of the inference (preprocess, forward, NMS) on the GPU
timeline, late = finished after the next frame was due (lat_ms > period). Video decoding happens before the frame's wait, so it is outside lat_ms unless it overruns the slack.
Hints go out through the existing frame-slack protocol (python/slackhint, docs/SPEC_FRAME_SLACK_HINTS.md): busy + next deadline `lead_ms` before the frame, not-busy + next deadline on completion, idle at the end.
The inference backend is injected: infer(frame) -> (t_start_s, t_end_s, gpu_ms). UltralyticsYolo is the hardware one; tests use fakes.
CLI (normally started by tools/bench.py):  python -m workloads.foreground.yolo_loop --video clip.mp4 --duration 60 --out DIR [--pace-name NAME] [--handshake]
  --handshake: print READY after warm-up, wait for 'GO <t0_qpc_s>' on stdin, then start at that QPC time (so a parent can start the sampling and the other workload first)."""
import argparse
import hashlib
import json
import math
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "python"))


class NullPublisher:
    def frame_started(self, now, next_deadline_s):
        pass

    def frame_done(self, now, next_deadline_s):
        pass

    def idle(self, now):
        pass


class FixedRateLoop:
    def __init__(self, fps, infer, next_frame, publisher=None, lead_ms=1.0, grace_s=5.0, clock=time.perf_counter, sleep=time.sleep):
        self.period = 1.0 / fps
        self.infer, self.next_frame, self.pub = infer, next_frame, publisher or NullPublisher()
        self.lead_s, self.grace_s, self.clock, self.sleep = lead_ms / 1000.0, grace_s, clock, sleep
        self.t0, self.abandoned = None, 0

    def _sleep_until(self, t):
        while True:
            rem = t - self.clock()
            if rem <= 0:
                return
            if rem > 0.003:
                self.sleep(rem - 0.002)

    def run(self, duration_s, t0=None):
        """Run round(duration_s * fps) frames. Returns a list of frame dicts. If the loop is still running grace_s after the nominal end (a hopeless backlog), the frames not yet started are
        counted in self.abandoned and the run stops; they are not skipped silently."""
        self.t0 = self.clock() + 0.05 if t0 is None else t0
        n_total = int(round(duration_s / self.period))
        recs, self.abandoned = [], 0
        for k in range(n_total):
            t_sched = self.t0 + k * self.period
            if self.clock() > self.t0 + duration_s + self.grace_s:
                self.abandoned = n_total - k
                break
            frame = self.next_frame()
            self._sleep_until(t_sched - self.lead_s)
            self.pub.frame_started(self.clock(), t_sched + self.period)
            t_start, t_end, gpu_ms = self.infer(frame)
            self.pub.frame_done(t_end, t_sched + self.period)
            lat_ms = (t_end - t_sched) * 1000.0
            recs.append(dict(t_sched=t_sched, t_start=t_start, t_end=t_end, lat_ms=lat_ms, gpu_ms=gpu_ms, late=lat_ms > self.period * 1000.0 + 1e-9))
        self.pub.idle(self.clock())
        return recs


def percentile(sorted_vals, q):
    """Linear-interpolation percentile of an ascending list (numpy's default method)."""
    n = len(sorted_vals)
    if n == 1:
        return float(sorted_vals[0])
    x = (n - 1) * q / 100.0
    lo = int(math.floor(x))
    hi = min(lo + 1, n - 1)
    return float(sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (x - lo))


def summarize(recs, trim_s=0.0, t0=None):
    """Frames scheduled at least trim_s after t0 (the start-up transient is excluded, as in the v1 smoke runs): count, late count and %, latency p50/p99 (ms, schedule to completion), GPU ms p50."""
    keep = [r for r in recs if t0 is None or r["t_sched"] >= t0 + trim_s]
    if not keep:
        return dict(frames=0, late=0, late_pct=None, lat_p50_ms=None, lat_p99_ms=None, gpu_p50_ms=None)
    lat, gpu = sorted(r["lat_ms"] for r in keep), sorted(r["gpu_ms"] for r in keep)
    late = sum(1 for r in keep if r["late"])
    return dict(frames=len(keep), late=late, late_pct=100.0 * late / len(keep), lat_p50_ms=percentile(lat, 50), lat_p99_ms=percentile(lat, 99), gpu_p50_ms=percentile(gpu, 50))


class VideoFrames:
    """Frames of a fixed video file, looped at the end. Refuses a file that does not open or has no frames."""

    def __init__(self, path):
        import cv2
        self.path, self.cv2 = str(path), cv2
        self.cap = cv2.VideoCapture(self.path)
        if not self.cap.isOpened() or int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT)) <= 0:
            raise RuntimeError(f"cannot read frames from {self.path}")
        self.info = dict(width=int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH)), height=int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
                         native_fps=float(self.cap.get(cv2.CAP_PROP_FPS)), frames=int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT)))

    def __call__(self):
        ok, frame = self.cap.read()
        if not ok:
            self.cap.set(self.cv2.CAP_PROP_POS_FRAMES, 0)
            ok, frame = self.cap.read()
            if not ok:
                raise RuntimeError(f"video read failed after rewind: {self.path}")
        return frame


class UltralyticsYolo:
    """YOLOv8 through ultralytics on the CUDA device; refuses to run without CUDA (no silent CPU fallback). Returns (t_start, t_end, gpu_ms) per frame: wall times around the call (synchronised) and the
    CUDA-event time between the first and last GPU work of the call."""

    def __init__(self, weights="yolov8n.pt", imgsz=640, half=True, device=0, clock=time.perf_counter):
        import torch
        if not torch.cuda.is_available():
            raise RuntimeError("CUDA is not available: refusing to run YOLO on the CPU")
        from ultralytics import YOLO
        self.torch, self.clock, self.imgsz, self.half, self.device = torch, clock, imgsz, half, device
        self.model = YOLO(weights)
        self.weights = str(weights)

    def _predict(self, frame):
        return self.model.predict(frame, imgsz=self.imgsz, half=self.half, device=self.device, verbose=False)

    def warm(self, frame, n=20):
        for _ in range(n):
            self._predict(frame)
        self.torch.cuda.synchronize()

    def __call__(self, frame):
        t = self.torch
        s, e = t.cuda.Event(enable_timing=True), t.cuda.Event(enable_timing=True)
        t_start = self.clock()
        s.record()
        self._predict(frame)
        e.record()
        t.cuda.synchronize()
        return t_start, self.clock(), float(s.elapsed_time(e))


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--video", required=True)
    ap.add_argument("--weights", default="yolov8n.pt")
    ap.add_argument("--imgsz", type=int, default=640)
    ap.add_argument("--fps", type=float, default=30.0)
    ap.add_argument("--duration", type=float, default=60.0)
    ap.add_argument("--out", required=True, help="directory for frames.npz and result.json")
    ap.add_argument("--pace-name", default=None, help="name of an existing slackhint block to publish to (created by the parent); default: no hints")
    ap.add_argument("--lead-ms", type=float, default=1.0)
    ap.add_argument("--trim-s", type=float, default=2.0, help="seconds at the start excluded from the summary (start-up transient)")
    ap.add_argument("--warm-frames", type=int, default=20)
    ap.add_argument("--handshake", action="store_true")
    a = ap.parse_args(argv)

    import numpy as np
    frames = VideoFrames(a.video)
    yolo = UltralyticsYolo(a.weights, a.imgsz)
    yolo.warm(frames(), a.warm_frames)
    pub = None
    if a.pace_name:
        import slackhint
        pub = slackhint.Producer(a.pace_name, create=False)
    loop = FixedRateLoop(a.fps, yolo, frames, pub, lead_ms=a.lead_ms)
    if a.handshake:
        print("READY", flush=True)
        line = sys.stdin.readline().split()
        if len(line) != 2 or line[0] != "GO":
            raise SystemExit(f"yolo_loop: expected 'GO <t0>' on stdin, got {line!r}")
        t0 = float(line[1])
    else:
        t0 = time.perf_counter() + 0.5
    recs = loop.run(a.duration, t0=t0)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    np.savez(out / "frames.npz", **{k: np.array([r[k] for r in recs]) for k in ("t_sched", "t_start", "t_end", "lat_ms", "gpu_ms", "late")})
    res = dict(t0=t0, fps=a.fps, duration_s=a.duration, trim_s=a.trim_s, abandoned=loop.abandoned, weights=yolo.weights, imgsz=a.imgsz, half=yolo.half, video=a.video,
               video_sha256=sha256_file(a.video), video_info=frames.info, pace_name=a.pace_name, summary=summarize(recs, a.trim_s, t0))
    (out / "result.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
    print(json.dumps(res["summary"]), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
