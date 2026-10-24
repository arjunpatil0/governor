"""W5b EVALUATION blocks 4-13 (plan addenda O-5, O-6; composition in eval_lib.py, frozen constants in data/w5b/constants.json, tests/test_w5b_eval.py).
   python experiments/w5b/evaluate.py --blocks 4 5 --constants data/w5b/constants.json --constants-sha256 <hash> --armoury-mode Performance [--out data/w5b/eval] [--executor hw|sim]
Needs (hardware): the admin clock helper in its own Administrator window, AC power, a FRESH restart (uptime <= 2 h), Chrome closed, a clean committed tree. Whole blocks only, at most 3 h per session
(estimate 100 s per cell). Every governed cell uses the SAMPLED power source (plan addendum O-5): the Governor loop reads the energy counter zero times. A block interrupted by any incident is left on disk
as incomplete; the next call discards it whole (moved to <out>/discarded/) and asks for a rerun under the next block number with the same seed list (--blocks N --as-block M).
Writes <out>/block<NN>/cells/<id>/cell.json, <out>/block<NN>/block.json (complete blocks only) and <out>/results.csv (columns of analysis/w5_analysis.py)."""
import argparse
import csv
import hashlib
import json
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "experiments" / "w5b")); sys.path.insert(0, str(ROOT / "experiments" / "w5a"))
sys.path.insert(0, str(ROOT / "experiments" / "w4_smoke")); sys.path.insert(0, str(ROOT / "workloads" / "common")); sys.path.insert(0, str(ROOT / "telemetry"))
import eval_lib as el  # noqa: E402

COLUMNS = ["block", "scene", "controller", "budget_w", "bg_tok_s", "miss_frac", "power_w", "exploratory", "cell_id", "power_sampled_w", "gov_reads", "executor"]


def load_constants(path, expected_sha):
    p = Path(path)
    sha = hashlib.sha256(p.read_bytes()).hexdigest()
    if sha != expected_sha:
        sys.exit(f"refused: the constants file hash {sha} is not the frozen one {expected_sha}")
    return json.loads(p.read_text(encoding="utf-8"))


def prepare_block(out, block, as_block):
    """None if block `as_block` can be run now. An incomplete directory of that number is discarded whole (moved to <out>/discarded/) and the caller must rerun under the next block number."""
    out = Path(out)
    d = out / f"block{as_block:02d}"
    if (d / "block.json").exists():
        return f"block {as_block} is already complete; a block is never re-run under its own number"
    if d.exists():
        dest = out / "discarded" / f"block{as_block:02d}_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(d), str(dest))
        return f"block {as_block} was incomplete and is discarded whole (kept in {dest}); rerun it with --blocks {block} --as-block <the next free block number> (same seed list)"
    return None


def export_results(out):
    out = Path(out)
    rows = []
    for bj in sorted(out.glob("block*/block.json")):
        for cj in sorted((bj.parent / "cells").glob("*/cell.json")):
            d = json.loads(cj.read_text(encoding="utf-8"))
            sp, m = d["spec"], d["metrics"]
            rows.append([sp["block"], sp["scene"], sp["controller"], sp["budget_w"], m["tok_s"], m["miss"], m["power_w"], sp["exploratory"], sp["id"], m.get("power_sampled_w"), m.get("gov_reads"), d["executor"]])
    with open(out / "results.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(COLUMNS)
        w.writerows(rows)
    return len(rows)


TRIAL_KEYS = (("S5", "d'B", 60.0), ("S2", "eB", 60.0), ("S1d", "c'B", 60.0), ("S0", "g'B", 60.0), ("S5", "a", 60.0), ("S1", "d'B", 35.0))


def trial_cells(const):
    """Supervised hardware trial (not data, not a block): one cell for each path the evaluation adds - d'B on the held-out 8B, eB with an idle phase (S2), c'B in S1d, a static g'B, arm a on the 8B, a 35 W cell."""
    cells = {(c["scene"], c["controller"], c["budget_w"]): c for c in block_cells_all(const)}
    return [cells[k] for k in TRIAL_KEYS]


def block_cells_all(const):
    return el.block_cells(4, const)


def run_trial(out, const, executor, log=print):
    out = Path(out) / "trial"
    n = 0
    for spec in trial_cells(const):
        cdir = out / "cells" / spec["id"]
        cdir.mkdir(parents=True, exist_ok=True)
        t0 = time.time()
        executor.between_cells()
        m = executor.run(spec, cdir)
        (cdir / "cell.json").write_text(json.dumps(dict(id=spec["id"], spec=spec, metrics=m, executor=executor.name, wall_s=time.time() - t0), indent=1, default=str), encoding="utf-8")
        log(f"TRIAL {spec['id']} ({spec['workload']}): " + ", ".join(f"{k}={v:.3f}" if isinstance(v, float) else f"{k}={v}" for k, v in m.items() if k in ("miss", "tok_s", "power_w", "power_sampled_w", "gov_reads", "power_source", "temp_after_c", "clock_changes", "final_pacing_mode", "exec_mode")) + f" ({time.time() - t0:.0f} s)")
        n += 1
    return dict(cells=n)


def run_blocks(out, blocks, const, executor, log=print, as_blocks=None):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    as_blocks = list(as_blocks or blocks)
    done = []
    for block, n in zip(blocks, as_blocks):
        msg = prepare_block(out, block, n)
        if msg:
            log("BLOCK", n, msg)
            return dict(blocks_done=done, stop=msg)
        cells = el.block_cells(n, const, seed_block=block)
        bdir = out / f"block{n:02d}"
        for k, spec in enumerate(cells):
            cdir = bdir / "cells" / spec["id"]
            cdir.mkdir(parents=True, exist_ok=True)
            t0 = time.time()
            try:
                executor.between_cells()
                m = executor.run(spec, cdir)
            except Exception as ex:                                                  # noqa: BLE001
                (cdir / "incident.json").write_text(json.dumps(dict(spec=spec, error=f"{type(ex).__name__}: {ex}", utc=datetime.now(timezone.utc).isoformat())), encoding="utf-8")
                log("INCIDENT", spec["id"], ex)
                return dict(blocks_done=done, stop=f"incident in block {n} at {spec['id']}: {ex}; the block is incomplete and will be discarded whole by the next call")
            (cdir / "cell.json").write_text(json.dumps(dict(id=spec["id"], spec=spec, metrics=m, executor=executor.name, wall_s=time.time() - t0, utc=datetime.now(timezone.utc).isoformat()), indent=1, default=str), encoding="utf-8")
            log(f"[block {n}: {k + 1}/{len(cells)}] {spec['id']}: tok/s {m.get('tok_s', float('nan')):.1f} miss {m.get('miss', float('nan')):.3f} power {m.get('power_w', float('nan')):.1f} W ({time.time() - t0:.0f} s)")
        (bdir / "block.json").write_text(json.dumps(dict(block=n, seed_block=block, cells=[c["id"] for c in cells], seed=el.SEED, constants=const, power_source=const.get("power_source"),
                                                          utc=datetime.now(timezone.utc).isoformat()), indent=1, default=str), encoding="utf-8")
        done.append(n)
        export_results(out)
    return dict(blocks_done=done, stop=None)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--blocks", type=int, nargs="+", required=True); ap.add_argument("--as-block", type=int, nargs="+", default=None)
    ap.add_argument("--constants", required=True); ap.add_argument("--constants-sha256", required=True)
    ap.add_argument("--out", default=str(ROOT / "data" / "w5b" / "eval")); ap.add_argument("--armoury-mode", default=None)
    ap.add_argument("--executor", choices=["hw", "sim"], default="hw"); ap.add_argument("--max-uptime-s", type=float, default=7200.0)
    ap.add_argument("--trial", action="store_true", help="supervised trial: six cells, one per path the evaluation adds (not data, not a block)")
    a = ap.parse_args()
    const = load_constants(a.constants, a.constants_sha256)
    as_blocks = a.as_block or a.blocks
    why = el.check_session(as_blocks, const)
    if why:
        sys.exit(why)
    out = Path(a.out)
    if a.executor == "hw":
        import subprocess
        import psutil
        from tune import refusal
        from workloads.common import procsnap
        bat = psutil.sensors_battery()
        porcelain = subprocess.run(["git", "-C", str(ROOT), "status", "--porcelain"], capture_output=True, text=True).stdout
        why = refusal(a.armoury_mode, None if bat is None else bool(bat.power_plugged), time.time() - psutil.boot_time(), a.max_uptime_s, porcelain, procsnap.chrome_running(procsnap.snapshot(interval=1.0)))
        if why:
            sys.exit(why)
        from executors import HwExecutor
        import smoke
        out.mkdir(parents=True, exist_ok=True)
        sd = out / "sessions" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        sd.mkdir(parents=True, exist_ok=True)
        smoke.write_meta(sd, a.armoury_mode)
        m = json.loads((sd / "meta.json").read_text(encoding="utf-8"))
        m.update(blocks=a.blocks, as_blocks=as_blocks, power_source="sampled", constants_sha256=a.constants_sha256, plan_addenda="O-5, O-6", session_estimate_s=el.session_estimate_s(as_blocks, const))
        (sd / "meta.json").write_text(json.dumps(m, indent=1), encoding="utf-8")
        ex = HwExecutor(power_source="sampled")
    else:
        from executors import SimExecutor
        ex = SimExecutor()
    if a.trial:
        try:
            run_trial(out, const, ex)
        finally:
            ex.close()
        return
    try:
        s = run_blocks(out, a.blocks, const, ex, as_blocks=as_blocks)
    finally:
        ex.close()
    n_rows = export_results(out) if s["blocks_done"] else 0
    print(f"session ended: blocks done {s['blocks_done']} stop={s['stop']}; results.csv rows (all complete blocks) {n_rows}")
    if s["stop"]:
        sys.exit(2)


if __name__ == "__main__":
    main()
