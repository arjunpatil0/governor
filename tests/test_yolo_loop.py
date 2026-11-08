"""v2 YOLO foreground loop (workloads/foreground/yolo_loop.py): timing logic and protocol publishing with a fake clock and a fake inference backend. No GPU, no ultralytics.
Instruction (Arjun, 2026-11-07): "A few focused tests (yolo loop timing logic, protocol publishing, VRAM reader), not an exhaustive suite." """
import math
import sys
import uuid
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
import slackhint as sh  # noqa: E402
from workloads.foreground.yolo_loop import FixedRateLoop, VideoFrames, percentile, summarize  # noqa: E402

FPS = 30.0
PERIOD = 1.0 / FPS


class FakeTime:
    """A clock that advances by 10 us per read (so a spin-wait terminates) and by the requested amount on sleep; infer() advances it by the frame cost."""
    def __init__(self, t=1000.0):
        self.t = t

    def clock(self):
        self.t += 1e-5
        return self.t

    def sleep(self, s):
        self.t += s


class FakeInfer:
    def __init__(self, ft, costs_s):
        self.ft, self.costs, self.i = ft, costs_s, 0

    def __call__(self, frame):
        cost = self.costs(self.i) if callable(self.costs) else self.costs
        self.i += 1
        t_start = self.ft.clock()
        self.ft.t += cost
        return t_start, self.ft.clock(), cost * 1000.0


def make_loop(ft, infer, pub=None, **kw):
    return FixedRateLoop(FPS, infer, lambda: None, pub, clock=ft.clock, sleep=ft.sleep, **kw)


def test_absolute_schedule_late_frames_are_recorded_and_never_skipped():
    ft = FakeTime()
    infer = FakeInfer(ft, lambda i: 0.100 if i == 3 else 0.005)           # frame 3 takes 3 periods
    t0 = ft.t + 0.1
    recs = make_loop(ft, infer).run(1.0, t0=t0)
    assert len(recs) == 30 and infer.i == 30                              # nothing skipped
    assert [r["t_sched"] for r in recs] == pytest.approx([t0 + k * PERIOD for k in range(30)], abs=1e-9)   # the schedule never moves
    late = [k for k, r in enumerate(recs) if r["late"]]
    assert late == [3, 4, 5]                                              # 3 overran; 4 and 5 started at once but were due earlier than they could finish
    assert recs[4]["t_start"] == pytest.approx(recs[3]["t_end"], abs=1e-3)   # catch-up: no waiting while behind
    assert not recs[6]["late"]                                            # back on schedule
    assert all(r["lat_ms"] == pytest.approx((r["t_end"] - r["t_sched"]) * 1000.0) for r in recs)
    assert recs[0]["gpu_ms"] == pytest.approx(5.0)


def test_summary_trims_the_start_and_matches_numpy_percentiles():
    ft = FakeTime()
    rng = np.random.default_rng(1)
    costs = rng.uniform(0.004, 0.030, size=300)
    t0 = ft.t + 0.1
    recs = make_loop(ft, FakeInfer(ft, lambda i: costs[i])).run(10.0, t0=t0)
    s = summarize(recs, trim_s=2.0, t0=t0)
    keep = [r for r in recs if r["t_sched"] >= t0 + 2.0]
    lat = np.array([r["lat_ms"] for r in keep])
    assert s["frames"] == len(keep) == 240
    assert s["lat_p99_ms"] == pytest.approx(np.percentile(lat, 99))
    assert s["late"] == int((lat > PERIOD * 1000).sum()) and s["late_pct"] == pytest.approx(100.0 * s["late"] / 240)
    assert percentile([5.0], 99) == 5.0
    assert summarize([], 0.0, 0.0)["frames"] == 0


def test_hopeless_backlog_is_counted_not_hidden():
    ft = FakeTime()
    loop = make_loop(ft, FakeInfer(ft, 10.0), grace_s=1.0)                # one frame takes 10 s: far past duration + grace
    recs = loop.run(1.0, t0=ft.t + 0.1)
    assert len(recs) == 1 and loop.abandoned == 29


class Recorder:
    def __init__(self):
        self.ev = []

    def frame_started(self, now, nxt):
        self.ev.append(("busy", now, nxt))

    def frame_done(self, now, nxt):
        self.ev.append(("done", now, nxt))

    def idle(self, now):
        self.ev.append(("idle", now, None))


def test_hints_busy_before_the_frame_done_with_next_deadline_idle_at_the_end():
    ft = FakeTime()
    rec = Recorder()
    t0 = ft.t + 0.1
    loop = make_loop(ft, FakeInfer(ft, 0.005), rec, lead_ms=1.0)
    recs = loop.run(0.2, t0=t0)                                          # 6 frames
    assert [e[0] for e in rec.ev] == ["busy", "done"] * 6 + ["idle"]
    for k, r in enumerate(recs):
        busy, done = rec.ev[2 * k], rec.ev[2 * k + 1]
        assert busy[1] == pytest.approx(r["t_sched"] - 0.001, abs=1e-3)   # published lead_ms before the frame is due
        assert busy[1] < r["t_sched"]
        assert busy[2] == pytest.approx(r["t_sched"] + PERIOD) == pytest.approx(done[2])
        assert done[1] == pytest.approx(r["t_end"])                      # not-busy goes out when the frame completes


def test_hints_reach_a_real_slackhint_consumer():
    """Through the real shared-memory block: during a frame the consumer sees busy + the next deadline, after the run it sees idle."""
    name = "Local\\gov_test_yolo_" + uuid.uuid4().hex
    prod = sh.Producer(name, create=True)
    cons = sh.Consumer(name)
    ft = FakeTime()
    seen = []

    def infer(frame):
        seen.append(cons.get(ft.t))
        t_start = ft.clock()
        ft.t += 0.004
        return t_start, ft.clock(), 4.0

    t0 = ft.t + 0.1
    make_loop(ft, infer, prod).run(0.2, t0=t0)
    assert len(seen) == 6
    for k, (busy, nxt) in enumerate(seen):
        assert busy is True and nxt == pytest.approx(t0 + k * PERIOD + PERIOD)
    busy, nxt = cons.get(ft.t)
    assert busy is False and math.isinf(nxt)


def test_video_frames_loop_at_the_end_and_refuse_a_bad_file(tmp_path):
    cv2 = pytest.importorskip("cv2")
    path = tmp_path / "t.mp4"
    w = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 30.0, (64, 48))
    for i in range(10):
        w.write(np.full((48, 64, 3), 20 * i, np.uint8))
    w.release()
    vf = VideoFrames(path)
    frames = [vf() for _ in range(25)]                                   # 2.5 passes: it rewinds
    assert all(f.shape == (48, 64, 3) for f in frames)
    assert vf.info["frames"] == 10 and vf.info["width"] == 64
    with pytest.raises(RuntimeError):
        VideoFrames(tmp_path / "missing.mp4")
