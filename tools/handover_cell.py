"""v2 sprint 2 hardware cells (docs/V2_SPRINT2_HANDOVER.md). One cell = the v1 synthetic 60 fps foreground (FrameLoop + FMA kernels, scene factor of the evaluation) in THIS process, publishing the live frame
hint, and the patched decode (workloads/background/llama_handover_bench.exe) in ANOTHER process, gated on that hint per token (G = 1, the v1 behaviour) or per layer group (G > 1). Cells run at a fixed
SM clock lock (default 1800 MHz, the v1 static setting), 5 s warm-up + 60 s measured window, power from two energy-counter reads and a guarded sampled-power stream (power_rejected is stored).
   python tools/handover_cell.py --readback               step 0: G1 and G14, 300 tokens each at the 1500 MHz lock, with nvidia-smi and NVML SM-clock readback during the run
   python tools/handover_cell.py --exp1 [--reps 2]        handover latency: the foreground frame is preceded by a marker kernel whose %globaltimer start is compared with the host submit time
   python tools/handover_cell.py --exp3 [--reps 3]        end to end: S1 (3B) and S5 (8B), whole-token gate against the 14-group gate
Needs the admin clock helper (actuators/clock_helper.py) running in an Administrator window and nothing else on the GPU. The clock is always reset in a finally block."""
import argparse
import ctypes
import json
import os
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
for p in (ROOT, ROOT / "workloads" / "common", ROOT / "telemetry", ROOT / "experiments" / "w4_smoke", ROOT / "analysis"):
    sys.path.insert(0, str(p))
import smoke as S  # noqa: E402
from experiments.w5a.w5a_metrics import summarise_cell  # noqa: E402
from experiments.w5b.executors import fg_spec  # noqa: E402
from telemetry.fg_publisher import FramePublisher  # noqa: E402
from telemetry.ring import SeqBlock, SharedRing  # noqa: E402
from workloads.foreground.frame_loop import FmaFrameRunner, FrameLoop  # noqa: E402

EXE = ROOT / "workloads" / "background" / "llama_handover_bench.exe"
BIN = ROOT / "third_party" / "llama.cpp_v2" / "build" / "bin"
PROMPT = ROOT / "data" / "llama" / "prompt.txt"
MODELS = {"3b": ROOT / "data" / "llama" / "Llama-3.2-3B-Instruct-Q4_K_M.gguf", "8b": ROOT / "data" / "llama" / "Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf"}
PERIOD_MS = 1000.0 / 60.0
WARM_S, MEASURE_S = 5.0, 60.0


class MarkerRunner(FmaFrameRunner):
    """Frame runner that first launches a tiny marker kernel (the W2 gt_sync primitive with n = 1: QPC just before the launch, %globaltimer inside the kernel, QPC after the sync) at the scheduled
    time and then runs the frame. delay = marker kernel start on the GPU clock, mapped to QPC, minus the host time just before the launch = the foreground's first-kernel delay."""
    def __init__(self, w2, cal):
        super().__init__(w2, cal)
        self.samples = []                                                  # (QPC before launch, raw %globaltimer in seconds, QPC after sync); the GPU timer drifts against QPC (about 70 us per second), so the mapping is applied afterwards from two calibrations

    def __call__(self, cost_ms, t_sched):
        while time.perf_counter() < t_sched:
            pass
        qb, qa, gt = np.zeros(1), np.zeros(1), np.zeros(1, dtype=np.uint64)
        import workloads.common.w2lib as L
        self.w.chk(self.w.d.w2_gt_sync(1, L.dbl(qb), L.dbl(qa), gt.ctypes.data_as(ctypes.c_void_p)), "gt_sync")
        self.samples.append((float(qb[0]), float(gt[0]) * 1e-9, float(qa[0])))
        return super().__call__(cost_ms, time.perf_counter())


def wait_line(path, token, proc, timeout):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if token in Path(path).read_text(errors="replace"):
            return
        if proc.poll() is not None:
            raise RuntimeError(f"process exited early ({proc.returncode}); log {path}:\n" + Path(path).read_text(errors="replace")[-1200:])
        time.sleep(0.1)
    raise RuntimeError(f"timeout waiting for {token} in {path}")


def run_cell(w, cal, cfg, out, marker=False, warm_s=WARM_S, measure_s=MEASURE_S):
    """cfg: dict(scene, model, G, gate). Returns the cell's metrics dict (also stored in out/result.json)."""
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    tag = uuid.uuid4().hex[:8]
    pace_name, fr_name = f"Local\\gov_ho_pace_{tag}", f"Local\\gov_ho_fr_{tag}"
    pace, frames_ring = SeqBlock(pace_name, 3, True), SharedRing(fr_name, 16384, 3, True)
    env = dict(os.environ, PATH=str(BIN) + ";" + os.environ["PATH"], GGML_CUDA_PAUSE_GROUPS=str(cfg["G"]), HINT_NAME=pace_name, GATE="1" if cfg["gate"] else "0", GUARD_MS=str(cfg.get("guard_ms", 0.0)))   # guard 0 ms = the registered v1 static setting (1800_a_g0_d1)
    dlog = out / "driver.log"
    drv = subprocess.Popen([str(EXE), str(MODELS[cfg["model"]]), str(PROMPT), str(out / "decode"), "512"], stdin=subprocess.PIPE, stdout=open(dlog, "w"), stderr=subprocess.STDOUT, text=True, env=env)
    smp = None
    try:
        wait_line(dlog, "READY", drv, 300)
        cal0 = None
        if marker:
            cal0 = w.gt_sync3(500)                                      # (offset_s, round_trip_s, qpc_s): idle calibration of the GPU clock against QPC (the decode is waiting for GO)
        runner = MarkerRunner(w, cal) if marker else FmaFrameRunner(w, cal)
        smp = S.NvmlSampler()
        smp.start()
        e = {}
        t0 = time.perf_counter() + 0.5
        t_stop = t0 + warm_s + measure_s + 0.3
        drv.stdin.write(f"GO {t_stop!r}\n")
        drv.stdin.flush()

        def energy():
            for key, t in (("start", t0 + warm_s), ("end", t0 + warm_s + measure_s)):
                while time.perf_counter() < t:
                    time.sleep(0.002)
                e[key] = smp.nv.nvmlDeviceGetTotalEnergyConsumption(smp.h)
        th = threading.Thread(target=energy, daemon=True)
        th.start()
        loop = FrameLoop(fg_spec(cfg["scene"], 7.0, 5000.0), runner, FramePublisher(frames_ring, pace))
        recs = loop.run(duration_s=warm_s + measure_s, t0=t0)
        th.join(10)
        smp.stop()
        drv.wait(timeout=60)
        if drv.returncode != 0:
            raise RuntimeError(f"decode driver failed ({drv.returncode}); log {dlog}")
        tk = np.genfromtxt(out / "decode_tokens.csv", delimiter=",", skip_header=1).reshape(-1, 3)
        res = summarise_cell(recs, tk[:, 0], tk[:, 1], t0, warm_s, measure_s, e.get("start", 0.0), e.get("end", 0.0), PERIOD_MS)
        sm = np.array(smp.sm)
        win = (np.array(smp.t) >= t0 + warm_s) & (np.array(smp.t) < t0 + warm_s + measure_s)
        res.update(cfg=cfg, t0=t0, power_rejected=int(smp.guard.rejected), sm_mhz_median=float(np.median(sm[win])) if win.any() else None, abandoned=int(loop.abandoned),
                   exec=[l for l in dlog.read_text(errors="replace").splitlines() if l.startswith(("EXEC_MODE", "DONE"))])
        np.savez_compressed(out / "frames.npz", t_sched=[r["t_sched"] for r in recs], t_start=[r["t_start"] for r in recs], t_end=[r["t_end"] for r in recs],
                            lat_ms=[r["lat_ms"] for r in recs], cost_ms=[r["cost_ms"] for r in recs])
        if marker:
            cal1 = w.gt_sync3(500)                                      # second idle calibration (the decode has exited): the offset is interpolated linearly between the two in the analysis
            np.savez_compressed(out / "marker.npz", samples=np.array(runner.samples), off0=cal0[0], rt0=cal0[1], q0=cal0[2], off1=cal1[0], rt1=cal1[1], q1=cal1[2])
        (out / "result.json").write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")
        return res
    finally:
        if smp is not None and smp.is_alive():
            smp.stop()
        if drv.poll() is None:
            try:
                drv.stdin.write(f"GO {time.perf_counter()!r}\n")
                drv.stdin.flush()
            except Exception:                                              # noqa: BLE001
                pass
            try:
                drv.wait(timeout=30)
            except subprocess.TimeoutExpired:
                drv.kill()


def session(clock, fn):
    """Lock the clock through the helper, calibrate the FMA frame at 1800 MHz, then lock `clock` and run fn(w, cal, cl); always reset the clock."""
    from actuators.startup_reset import reset_clocks
    from workloads.common.w2lib import W2
    w = W2()
    cl = S.SafeClient()                                                  # raises if the admin helper is not running: no silent unlocked run
    hb = S.Heartbeat(cl)
    hb.start()
    try:
        reset_clocks(cl, is_admin=False)
        cl.reset()
        time.sleep(1.1)
        if not cl.lock(1800):
            raise RuntimeError("the helper refused the 1800 MHz lock")
        time.sleep(1.5)
        cal = FmaFrameRunner.calibrate(w)                                # frame costs are defined at 1800 MHz, as in the v1 evaluation
        if clock != 1800:
            cl.reset()
            time.sleep(1.1)
            if not cl.lock(clock):
                raise RuntimeError(f"the helper refused the {clock} MHz lock")
            time.sleep(1.5)
        return fn(w, cal, cl)
    finally:
        hb.stop()
        cl.reset()
        cl.close()


def stamp_dir(name):
    d = ROOT / "data" / "v2" / "s2" / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + name)
    d.mkdir(parents=True, exist_ok=True)
    return d


def readback():
    """Step 0: G = 1 and G = 14, 300 tokens each with the sprint-1 driver at the 1500 MHz lock, SM clock read back by nvidia-smi (every 100 ms) and by NVML during the run."""
    sys.path.insert(0, str(ROOT / "tools"))
    import pause_bench as P
    out = stamp_dir("clock_readback")

    def body(w, cal, cl):
        res = {}
        for name, env in (("G1", {"GGML_CUDA_PAUSE_GROUPS": "1"}), ("G14", {"GGML_CUDA_PAUSE_GROUPS": "14"})):
            smi = subprocess.Popen(["nvidia-smi", "--query-gpu=clocks.sm,clocks.mem,power.draw.instant", "--format=csv,noheader,nounits", "-lms", "100"], stdout=subprocess.PIPE, text=True)
            smp = S.NvmlSampler()
            smp.start()
            time.sleep(0.5)
            P.run_exe(env, out / name, 300, 20)
            time.sleep(0.5)
            smp.stop()
            smi.terminate()
            lines = [l.split(",") for l in smi.stdout.read().splitlines() if l.strip()]
            clk = np.array([float(l[0]) for l in lines])
            res[name] = dict(nvidia_smi_samples=int(len(clk)), nvidia_smi_sm_mhz_min=float(clk.min()), nvidia_smi_sm_mhz_median=float(np.median(clk)), nvidia_smi_sm_mhz_max=float(clk.max()),
                             nvml_samples=len(smp.sm), nvml_sm_mhz_median=float(np.median(smp.sm)), nvml_sm_mhz_max=float(np.max(smp.sm)), power_rejected=int(smp.guard.rejected))
            print(name, json.dumps(res[name]))
            time.sleep(3)
        (out / "result.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
        return res
    return session(1500, body)


def exp1(reps):
    out = stamp_dir("exp1_handover")
    cfgs = [("G1_free", dict(G=1, gate=False)), ("G14_free", dict(G=14, gate=False)), ("G1_gate", dict(G=1, gate=True)), ("G14_gate", dict(G=14, gate=True))]

    def body(w, cal, cl):
        for rep in range(1, reps + 1):
            for name, c in cfgs:
                print(f"[exp1 {name} rep {rep}]", flush=True)
                r = run_cell(w, cal, dict(scene="S0", model="3b", **c), out / f"{name}_rep{rep}", marker=True)
                print(f"   late {100 * r['miss_frac']:.2f}%  tok/s {r['bg_tok_s']:.1f}  p99 {r['fg_p99_ms']:.1f} ms  sm {r['sm_mhz_median']}  rejected {r['power_rejected']}", flush=True)
                time.sleep(4)
    session(1800, body)
    print("saved in", out)


def exp3(reps):
    out = stamp_dir("exp3_end_to_end")
    cells = [("S1", "3b"), ("S5", "8b")]
    cfgs = [("whole", dict(G=1, gate=True)), ("g14", dict(G=14, gate=True))]

    def body(w, cal, cl):
        for rep in range(1, reps + 1):
            for scene, model in cells:
                for name, c in cfgs:
                    print(f"[exp3 {scene} {model} {name} rep {rep}]", flush=True)
                    r = run_cell(w, cal, dict(scene=scene, model=model, **c), out / f"{scene}_{name}_rep{rep}")
                    print(f"   late {100 * r['miss_frac']:.2f}%  tok/s {r['bg_tok_s']:.1f}  power {r['power_w']:.1f} W  sm {r['sm_mhz_median']}  rejected {r['power_rejected']}", flush=True)
                    time.sleep(5)
    session(1800, body)
    print("saved in", out)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--readback", action="store_true")
    ap.add_argument("--exp1", action="store_true")
    ap.add_argument("--exp3", action="store_true")
    ap.add_argument("--reps", type=int, default=None)
    a = ap.parse_args()
    if not EXE.exists():
        sys.exit(f"missing {EXE}: build it with workloads/background/build_llama_handover.bat")
    if a.readback:
        readback()
    elif a.exp1:
        exp1(a.reps or 2)
    elif a.exp3:
        exp3(a.reps or 3)
    else:
        ap.error("give --readback, --exp1 or --exp3")


if __name__ == "__main__":
    main()
