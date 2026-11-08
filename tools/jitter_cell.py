"""v2 sprint 3 cells (docs/V2_SPRINT3_JITTER.md): the sprint-2 cell (v1 synthetic 60 fps foreground in this process publishing the live hint; patched decode gated on the hint in another process) with the
JITTERED foreground of workloads/foreground/jitter_loop.py. Arms: solo (no decode), 3b_whole (3B, whole-token gate), 3b_g14 (3B, 14-group gate), 8b_g14 (8B, 14-group gate). The same seed and the same frame
sequence for every arm at a (level, rep). Level 'none' uses the v1 FrameLoop exactly as sprint 2 did (reproduction check); moderate and heavy use the jitter loop (hint updated only at the real submit).
   python tools/jitter_cell.py --run [--reps 3]         the full matrix (28 cells), 1800 MHz lock, guard 0, spin-wait, 5 s warm-up + 60 s measured
Needs the admin clock helper (actuators/clock_helper.py) in an Administrator window and nothing else on the GPU. The clock is always reset in a finally block."""
import argparse
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
sys.path.insert(0, str(ROOT / "tools"))
import handover_cell as H  # noqa: E402  (also sets up sys.path for the project modules)
import smoke as S  # noqa: E402
from experiments.w5a.w5a_metrics import summarise_cell  # noqa: E402
from experiments.w5b.executors import fg_spec  # noqa: E402
from telemetry.fg_publisher import FramePublisher  # noqa: E402
from telemetry.ring import SeqBlock, SharedRing  # noqa: E402
from workloads.foreground.frame_loop import FmaFrameRunner, FrameLoop  # noqa: E402
from workloads.foreground.jitter_loop import JitterFrameLoop, make_sequence  # noqa: E402

ARMS = {"solo": None, "3b_whole": dict(model="3b", G=1, scene="S1"), "3b_g14": dict(model="3b", G=14, scene="S1"), "8b_g14": dict(model="8b", G=14, scene="S5")}
SEED_BASE = {"none": 1000, "moderate": 2000, "heavy": 3000}
WARM_S, MEASURE_S = 5.0, 60.0


def run_cell_j(w, cal, arm, level, rep, out, warm_s=WARM_S, measure_s=MEASURE_S):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    spec = ARMS[arm]
    scene = spec["scene"] if spec else "S1"                         # the foreground of S5 is the S1 loop (only the model differs), so SOLO at S1 is the SOLO of both
    seed = SEED_BASE[level] + rep
    n_frames = int(round((warm_s + measure_s) * 60.0))
    tag = uuid.uuid4().hex[:8]
    pace_name, fr_name = f"Local\\gov_jt_pace_{tag}", f"Local\\gov_jt_fr_{tag}"
    pace, frames_ring = SeqBlock(pace_name, 3, True), SharedRing(fr_name, 16384, 3, True)
    drv, dlog = None, out / "driver.log"
    if spec:
        env = dict(os.environ, PATH=str(H.BIN) + ";" + os.environ["PATH"], GGML_CUDA_PAUSE_GROUPS=str(spec["G"]), HINT_NAME=pace_name, GATE="1", GUARD_MS="0")
        drv = subprocess.Popen([str(H.EXE), str(H.MODELS[spec["model"]]), str(H.PROMPT), str(out / "decode"), "512"], stdin=subprocess.PIPE, stdout=open(dlog, "w"), stderr=subprocess.STDOUT, text=True, env=env)
    smp = None
    try:
        if drv:
            H.wait_line(dlog, "READY", drv, 300)
        smp = S.NvmlSampler()
        smp.start()
        e = {}
        t0 = time.perf_counter() + 0.5
        if drv:
            drv.stdin.write(f"GO {t0 + warm_s + measure_s + 0.3!r}\n")
            drv.stdin.flush()

        def energy():
            for key, t in (("start", t0 + warm_s), ("end", t0 + warm_s + measure_s)):
                while time.perf_counter() < t:
                    time.sleep(0.002)
                e[key] = smp.nv.nvmlDeviceGetTotalEnergyConsumption(smp.h)
        th = threading.Thread(target=energy, daemon=True)
        th.start()
        runner = FmaFrameRunner(w, cal)
        fg = fg_spec(scene, 7.0, 5000.0)
        pub = FramePublisher(frames_ring, pace)
        if level == "none":
            loop = FrameLoop(fg, runner, pub)                      # exactly the sprint-2 loop (busy 1 ms before the scheduled arrival)
        else:
            loop = JitterFrameLoop(fg, runner, pub, make_sequence(seed, n_frames, level))
        recs = loop.run(duration_s=warm_s + measure_s, t0=t0)
        th.join(10)
        smp.stop()
        if drv:
            drv.wait(timeout=60)
            if drv.returncode != 0:
                raise RuntimeError(f"decode driver failed ({drv.returncode}); log {dlog}")
            tk = np.genfromtxt(out / "decode_tokens.csv", delimiter=",", skip_header=1).reshape(-1, 3)
        else:
            tk = np.zeros((0, 3))
        res = summarise_cell(recs, tk[:, 0], tk[:, 1], t0, warm_s, measure_s, e.get("start", 0.0), e.get("end", 0.0), H.PERIOD_MS)
        sm, st_ = np.array(smp.sm), np.array(smp.t)
        win = (st_ >= t0 + warm_s) & (st_ < t0 + warm_s + measure_s)
        res.update(arm=arm, level=level, rep=rep, seed=seed, scene=scene, t0=t0, power_rejected=int(smp.guard.rejected), sm_mhz_median=float(np.median(sm[win])) if win.any() else None,
                   abandoned=int(loop.abandoned), exec=[l for l in dlog.read_text(errors="replace").splitlines() if l.startswith(("EXEC_MODE", "DONE"))] if drv else [])
        k = np.array([r.get("k", int(round((r["t_sched"] - t0) * 60.0))) for r in recs])
        np.savez_compressed(out / "frames.npz", k=k, t_sched=[r["t_sched"] for r in recs], t_submit=[r.get("t_submit", r["t_sched"]) for r in recs], t_start=[r["t_start"] for r in recs],
                            t_end=[r["t_end"] for r in recs], lat_ms=[r["lat_ms"] for r in recs], cost_ms=[r["cost_ms"] for r in recs], burst=[bool(r.get("burst", False)) for r in recs],
                            spike=[bool(r.get("spike", False)) for r in recs])
        (out / "result.json").write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")
        return res
    finally:
        if smp is not None and smp.is_alive():
            smp.stop()
        if drv is not None and drv.poll() is None:
            try:
                drv.stdin.write(f"GO {time.perf_counter()!r}\n")
                drv.stdin.flush()
            except Exception:                                              # noqa: BLE001
                pass
            try:
                drv.wait(timeout=30)
            except subprocess.TimeoutExpired:
                drv.kill()


def run_matrix(reps):
    out = ROOT / "data" / "v2" / "s3" / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_jitter")
    out.mkdir(parents=True, exist_ok=True)

    def body(w, cal, cl):
        for rep in range(1, reps + 1):
            for level in ("none", "moderate", "heavy"):
                if level == "none" and rep > 1:
                    continue                                              # none: one rep, a reproduction check against sprint 2
                for arm in ARMS:
                    print(f"[{level} rep {rep} {arm}]", flush=True)
                    r = run_cell_j(w, cal, arm, level, rep, out / f"{level}_{arm}_rep{rep}")
                    print(f"   late {100 * r['miss_frac']:.2f}%  tok/s {r['bg_tok_s']:.1f}  power {r['power_w']:.1f} W  p99 {r['fg_p99_ms']:.1f} ms  sm {r['sm_mhz_median']}  rejected {r['power_rejected']}", flush=True)
                    time.sleep(4)
    H.session(1800, body)
    print("saved in", out)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--reps", type=int, default=3)
    a = ap.parse_args()
    if not H.EXE.exists():
        sys.exit(f"missing {H.EXE}: build it with workloads/background/build_llama_handover.bat")
    if a.run:
        run_matrix(a.reps)
    else:
        ap.error("give --run")


if __name__ == "__main__":
    main()
