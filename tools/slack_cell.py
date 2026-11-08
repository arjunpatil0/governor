"""v2 sprint 4 (docs/V2_SPRINT4_LOW_SLACK.md): low slack. Calibrates the nominal frame cost of a constant-cost foreground (scene S0, moderate jitter of sprint 3, same seeds) so that the SOLO median frame time (launch to
completion) is 12.5 ms (TIGHT) and 14.5 ms (VERY TIGHT), then runs 6 arms x 2 levels x 2 reps of 60 s cells at the 1800 MHz lock, spin-wait: SOLO; 3B whole-token (guard 0); 3B 14 groups (guard 0); 3B 14 groups
(guard 1.0 ms); 8B 14 groups (guard 1.0); 8B 28 groups (guard 1.0). The guard is the early-start margin m: a unit launches only if now + predicted unit time + m <= the nominal next deadline.
   python tools/slack_cell.py --run [--reps 2]
Needs the admin clock helper (actuators/clock_helper.py) in an Administrator window and nothing else on the GPU. The clock is always reset in a finally block."""
import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import handover_cell as H  # noqa: E402
import jitter_cell as J  # noqa: E402

LEVELS = {"tight": 12.5, "very_tight": 14.5}                       # target SOLO median frame time in ms
ARMS = [("solo", False, 0.0), ("3b_whole", dict(model="3b", G=1), 0.0), ("3b_g14_m0", dict(model="3b", G=14), 0.0), ("3b_g14_m1", dict(model="3b", G=14), 1.0),
        ("8b_g14_m1", dict(model="8b", G=14), 1.0), ("8b_g28_m1", dict(model="8b", G=28), 1.0)]


def solo_median_ms(cell, warm_s):
    r = json.loads((Path(cell) / "result.json").read_text())
    f = np.load(Path(cell) / "frames.npz")
    keep = f["t_sched"] >= r["t0"] + warm_s
    return float(np.median((f["t_end"][keep] - f["t_start"][keep]) * 1e3))


def calibrate(w, cal, target_ms, out):
    """Scale the nominal cost until a 10 s SOLO cell (moderate jitter, sprint-3 seed) has a median frame time within 0.05 ms of the target (at most 4 rounds)."""
    c0, hist = target_ms, []
    for i in range(4):
        cell = out / f"calib_{target_ms:g}_{i}"
        J.run_cell_j(w, cal, "solo", "moderate", 1, cell, warm_s=2.0, measure_s=10.0, c0=c0, spec_override=False, scene_override="S0")
        med = solo_median_ms(cell, 2.0)
        hist.append((c0, med))
        print(f"   calibration target {target_ms} ms: c0 {c0:.3f} -> SOLO median {med:.3f} ms", flush=True)
        if abs(med - target_ms) <= 0.05:
            break
        c0 *= target_ms / med
        time.sleep(2)
    return c0, hist


def run_matrix(reps):
    out = ROOT / "data" / "v2" / "s4" / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_slack")
    out.mkdir(parents=True, exist_ok=True)

    def body(w, cal, cl):
        calib = {}
        for name, target in LEVELS.items():
            c0, hist = calibrate(w, cal, target, out)
            calib[name] = dict(target_ms=target, c0=c0, history=hist)
        (out / "calibration.json").write_text(json.dumps(calib, indent=1), encoding="utf-8")
        for rep in range(1, reps + 1):
            for level in LEVELS:
                for arm, spec, guard in ARMS:
                    print(f"[{level} rep {rep} {arm}]", flush=True)
                    r = J.run_cell_j(w, cal, arm, "moderate", rep, out / f"{level}_{arm}_rep{rep}", c0=calib[level]["c0"], guard_ms=guard, spec_override=spec, scene_override="S0")
                    print(f"   late {100 * r['miss_frac']:.2f}%  tok/s {r['bg_tok_s']:.1f}  power {r['power_w']:.1f} W  p99 {r['fg_p99_ms']:.1f} ms  sm {r['sm_mhz_median']}  rejected {r['power_rejected']}", flush=True)
                    time.sleep(4)
    H.session(1800, body)
    print("saved in", out)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--reps", type=int, default=2)
    a = ap.parse_args()
    if not H.EXE.exists():
        sys.exit(f"missing {H.EXE}: build it with workloads/background/build_llama_handover.bat")
    if a.run:
        run_matrix(a.reps)
    else:
        ap.error("give --run")


if __name__ == "__main__":
    main()
