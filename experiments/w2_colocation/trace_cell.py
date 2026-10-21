r"""Descriptive Nsight Systems trace of one B cell (fma_60hz + memory background), review 2026-10-21_w2_B_review finding 3.
Run under nsys from an Administrator shell (clock locks need admin), e.g.
  nsys profile -t cuda,osrt --force-overwrite true -o data/nsys/fma60_membg_1800 python experiments\w2_colocation\trace_cell.py --level 1800
Known gap (review 2026-10-21_w2_traces_review, finding 2): the children are killed after writing output, so CUPTI never flushes and the trace has no kernel table;
a future trace should call cudaProfilerStop() (or cuptiActivityFlushAll) in each child right after writing its output, before the hang-prone exit. Not implemented.
Reuses run.py's fg and bg children, the B run's calibration.json and the pilot frame size; nothing here is a hypothesis test."""
import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "workloads" / "common"))
import run as R                                              # noqa: E402
from design import frame_units_from_pilot                    # noqa: E402
from loadgen import gamma_slice_durations                    # noqa: E402
from w2lib import units_for                                  # noqa: E402

def wait_or_kill(procs, outs, deadline_s, grace_s=5.0):
    """Wait on a fixed window (not on request completion). A child that has written its output file but not exited within grace_s is killed
    ('killed_after_output': the nsys/WDDM exit hang of journal 0018); a child with no output at the deadline is killed ('killed_deadline')."""
    t0 = time.time(); seen = {}
    while time.time() - t0 < deadline_s:
        now = time.time()
        for i, (p, o) in enumerate(zip(procs, outs)):
            if i not in seen and Path(o).exists():
                seen[i] = now
        if all(p.poll() is not None or (i in seen and now - seen[i] > grace_s) for i, p in enumerate(procs)):
            break
        time.sleep(0.2)
    st = []
    for i, (p, o) in enumerate(zip(procs, outs)):
        if p.poll() is not None:
            st.append("exited" if Path(o).exists() else f"died_rc{p.returncode}")
            continue
        p.kill(); p.wait(timeout=30)
        st.append("killed_after_output" if Path(o).exists() else "killed_deadline")
    return st


CAL = R.ROOT / "data" / "raw" / "w2_B" / "20261021T105205Z" / "calibration.json"


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--level", required=True); ap.add_argument("--seconds", type=float, default=3.0)
    ap.add_argument("--no-clock-control", action="store_true", help="test only (no admin): clocks are not touched")
    ap.add_argument("--out", default=str(R.ROOT / "data" / "nsys"))
    a = ap.parse_args()
    R.NO_CLOCK_CONTROL = a.no_clock_control
    lv = a.level if a.level == "unlocked" else int(a.level)
    out = Path(a.out) / f"fma60_membg_{lv}"; out.mkdir(parents=True, exist_ok=True)
    cal = json.loads(CAL.read_text(encoding="utf-8"))
    units_fg = frame_units_from_pilot(R.PILOT)["fma_60hz"]
    procs = []
    try:
        R.set_mem(8001); R.set_sm(lv)
        t_sync = time.perf_counter() + 5.0
        n = int(round(60 * (a.seconds + 1)))
        arr = t_sync + np.arange(n) / 60.0
        np.save(out / "arrivals.npy", arr)
        dur = gamma_slice_durations(20000, 1.0, 0.0, 1)
        np.save(out / "bg_units.npy", units_for(cal["mem"], dur))
        t_stop = arr[-1] + 1.0
        procs = [R.spawn("fg", dict(out=str(out / "fg.npz"), arrivals=str(out / "arrivals.npy"), kind=R.KIND_ID["fma"], units=units_fg, cpu=R.FG_CPU, priority="normal"), out),
                 R.spawn("bg", dict(out=str(out / "bg.npz"), units=str(out / "bg_units.npy"), kind=R.KIND_ID["mem"], t_sync=t_sync, t_stop=t_stop, cap=200000, duty=1.0, cpu=R.BG_CPU), out)]
        # fixed window: the arrival span plus the start lead, a grace for the last frames, then kill (under overload the fg queue may never drain)
        st = wait_or_kill(procs, [out / "fg.npz", out / "bg.npz"], deadline_s=5.0 + (a.seconds + 1) + 15.0)
        (out / "trace_cell_status.json").write_text(json.dumps(dict(level=str(lv), children=dict(fg=st[0], bg=st[1]))), encoding="utf-8")
        print("done", st)
    finally:
        for p in procs:
            if p.poll() is None:
                p.kill()
        if not R.NO_CLOCK_CONTROL:
            subprocess.run(["nvidia-smi", "-rgc"]); subprocess.run(["nvidia-smi", "-rmc"])


if __name__ == "__main__":
    main()
