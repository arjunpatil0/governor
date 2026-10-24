"""W5b tuning blocks T1-T3 as ONE unattended sitting (plan addendum O section 4; docs/W5B_ADDENDUM_O.md). The plan itself (which cells, in which order, all decisions) is experiments/w5b/tune_lib.py;
this file is the loop around it: refusals, resumable storage, incident handling, meta.json, manifest.
   python experiments/w5b/tune.py --out data/w5b/tuning --armoury-mode Performance [--executor hw|sim] [--limit N] [--max-uptime-s 7200]
Needs (hardware): the admin clock helper in its own Administrator window; AC power; a FRESH restart (uptime <= 2 h, addendum M); Chrome closed; clean committed tree.
Writes <out>/cells/<id>/cell.json (+ driver.csv, frames.npz on hardware), <out>/meta.json, <out>/decisions.json, <out>/manifest.json. Re-running the same command resumes; decisions are recomputed from the stored cells."""
import argparse
import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "experiments" / "w5b")); sys.path.insert(0, str(ROOT / "experiments" / "w5a"))
sys.path.insert(0, str(ROOT / "experiments" / "w4_smoke")); sys.path.insert(0, str(ROOT / "workloads" / "common")); sys.path.insert(0, str(ROOT / "telemetry"))
import tune_lib as tl  # noqa: E402
from w5a_metrics import dirty_paths  # noqa: E402

RELAXATION = ("T1-T3 chained in one unattended sitting (plan addendum O section 4): the yaml 3 h session cap is relaxed for the tuning blocks only; evaluation blocks keep it. "
              "Tuning blocks are in no confirmatory test.")


def refusal(armoury_mode, plugged, uptime_s, max_uptime_s, porcelain, chrome):
    """Reason the sitting must not start, or None (hardware executor only)."""
    if not armoury_mode or not str(armoury_mode).strip():
        return "refused: pass --armoury-mode <the Armoury Crate mode now active> (journal 0021)"
    if plugged is False:
        return "refused: the laptop is on battery (registration: AC power)"
    if uptime_s > max_uptime_s:
        return f"refused: uptime {uptime_s / 3600:.1f} h > {max_uptime_s / 3600:.1f} h: restart the laptop first (plan addendum M: a fresh restart before every sitting)"
    bad = dirty_paths(porcelain)
    if bad:
        return "refused: the working tree is not clean (commit first): " + ", ".join(bad[:5])
    if chrome:
        return "refused: Chrome is running (close it; the checklist requires it closed)"
    return None


def is_resume(meta, boot_ts):
    """True when meta.json (of an earlier call of the SAME sitting) was written in this boot: the uptime rule applies to the start of a sitting, not to its resume after a plain stop."""
    try:
        return abs(datetime.fromisoformat(meta["boot_utc"]).timestamp() - boot_ts) < 5.0
    except Exception:                                                            # noqa: BLE001
        return False


def resolve_power_source(plan, requested, diag_dir):
    """Power source of the Governor loop (plan addendum O-4). 'auto': the first sitting keeps 'energy'; T3b takes the verdict of the diagnostic gate (power_source.json) and is REFUSED without a usable one."""
    if requested != "auto":
        return requested
    if plan != "t3b":
        return "energy"
    f = Path(diag_dir) / "power_source.json"
    if not f.exists():
        sys.exit(f"refused: {f} not found - run the diagnostic and its gate first (docs/W5B_T3B_SITTING.md)")
    v = json.loads(f.read_text(encoding="utf-8"))
    if v.get("power_source") not in ("energy", "sampled"):
        sys.exit(f"refused: the diagnostic gate verdict is {v.get('verdict')}: T3b must not start")
    return v["power_source"]


def load_results(cells_dir):
    res = {}
    for p in sorted(Path(cells_dir).glob("*/cell.json")):
        d = json.loads(p.read_text(encoding="utf-8"))
        res[d["id"]] = d["metrics"]
    return res


def run_sitting(out_dir, executor, limit=None, log=print, deadline=None, planner=None):
    out_dir = Path(out_dir)
    cells_dir = out_dir / "cells"
    cells_dir.mkdir(parents=True, exist_ok=True)
    results = load_results(cells_dir)
    fails, consecutive, ran = {}, 0, 0
    planner = planner or tl.next_batch
    while True:
        ans = planner(results)
        if not ans["batch"]:
            (out_dir / "decisions.json").write_text(json.dumps(dict(ans["decisions"], stop=ans["stop"], executor=executor.name, utc=datetime.now(timezone.utc).isoformat()), indent=1, default=str), encoding="utf-8")
            return dict(finished=True, stop=ans["stop"], cells_run=ran, decisions=ans["decisions"])
        for spec in ans["batch"]:
            if limit is not None and ran >= limit:
                return dict(finished=False, stop=None, cells_run=ran)
            if deadline is not None and time.time() >= deadline:
                return dict(finished=False, stop="deadline reached (--max-hours): no new cell is started; re-run the same command to resume", cells_run=ran)
            cdir = cells_dir / spec["id"]
            cdir.mkdir(parents=True, exist_ok=True)
            t0 = time.time()
            try:
                executor.between_cells()
                m = executor.run(spec, cdir)
            except Exception as ex:                                              # noqa: BLE001
                (cdir / "incident.json").write_text(json.dumps(dict(spec=spec, error=f"{type(ex).__name__}: {ex}", utc=datetime.now(timezone.utc).isoformat())), encoding="utf-8")
                log("INCIDENT", spec["id"], ex)
                fails[spec["id"]] = fails.get(spec["id"], 0) + 1
                consecutive += 1
                if consecutive >= 2:
                    return dict(finished=False, stop=f"two consecutive cell failures (last: {spec['id']}: {ex}); the sitting stops, finished cells are kept", cells_run=ran)
                if fails[spec["id"]] >= 2:
                    return dict(finished=False, stop=f"cell {spec['id']} failed twice; the sitting stops", cells_run=ran)
                continue
            consecutive = 0
            (cdir / "cell.json").write_text(json.dumps(dict(id=spec["id"], spec=spec, metrics=m, executor=executor.name, wall_s=time.time() - t0, utc=datetime.now(timezone.utc).isoformat()), indent=1, default=str), encoding="utf-8")
            results[spec["id"]] = m
            ran += 1
            log(f"[{len(results)}] {spec['id']}: tok/s {m.get('tok_s', float('nan')):.1f} miss {m.get('miss', float('nan')):.3f} power {m.get('power_w', float('nan')):.1f} W ({time.time() - t0:.0f} s)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True); ap.add_argument("--armoury-mode", default=None)
    ap.add_argument("--executor", choices=["hw", "sim"], default="hw"); ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--max-uptime-s", type=float, default=7200.0); ap.add_argument("--max-hours", type=float, default=None, help="stop starting new cells after this many hours (resumable)")
    ap.add_argument("--plan", choices=["t1t3", "t3b"], default="t1t3", help="t1t3 = the first sitting; t3b = d'B margin grid + c'B constants re-tuned (needs --c0)")
    ap.add_argument("--c0", type=int, default=None, help="the chosen c0 (ms nominal) for --plan t3b")
    ap.add_argument("--power-source", choices=["auto", "energy", "sampled"], default="auto", help="power signal of the Governor loop; auto = from the diagnostic gate for --plan t3b")
    ap.add_argument("--diag-dir", default=str(ROOT / "data" / "w5b" / "diag"), help="where the diagnostic gate wrote power_source.json")
    ap.add_argument("--diag", action="store_true", help="diagnostic A/B of the governed-cell power anomaly (4 cells; not data, not the plan)")
    ap.add_argument("--trial", action="store_true", help="supervised trial: one cell of every executor path (not data, not the plan), results printed and stored under --out")
    a = ap.parse_args()
    out = Path(a.out)
    if a.executor == "hw":
        import subprocess
        import psutil
        from workloads.common import procsnap
        bat = psutil.sensors_battery()
        porcelain = subprocess.run(["git", "-C", str(ROOT), "status", "--porcelain"], capture_output=True, text=True).stdout
        old = json.loads((out / "meta.json").read_text(encoding="utf-8")) if (out / "meta.json").exists() else None
        resume = old is not None and is_resume(old, psutil.boot_time())
        why = refusal(a.armoury_mode, None if bat is None else bool(bat.power_plugged), 0.0 if resume else time.time() - psutil.boot_time(), a.max_uptime_s, porcelain, procsnap.chrome_running(procsnap.snapshot(interval=1.0)))
        if why:
            sys.exit(why)
        from executors import HwExecutor
        out.mkdir(parents=True, exist_ok=True)
        import smoke
        if resume:                                                                  # same boot: keep the sitting's meta.json, note the resume
            old.setdefault("resumed_utc", []).append(datetime.now(timezone.utc).isoformat())
            (out / "meta.json").write_text(json.dumps(old, indent=1), encoding="utf-8")
            ex = HwExecutor(power_source=resolve_power_source(a.plan, a.power_source, a.diag_dir))
            return _finish(out, ex, a)
        smoke.write_meta(out, a.armoury_mode)
        m = json.loads((out / "meta.json").read_text(encoding="utf-8"))
        m.update(sitting_start_utc=datetime.now(timezone.utc).isoformat(), relaxation=RELAXATION, plan_addendum="docs/W5B_ADDENDUM_O.md", addendum_o_sha256=hashlib.sha256((ROOT / "docs" / "W5B_ADDENDUM_O.md").read_bytes()).hexdigest(),
                 yaml_sha256=hashlib.sha256((ROOT / "experiments" / "w5_governor.yaml").read_bytes()).hexdigest())
        (out / "meta.json").write_text(json.dumps(m, indent=1), encoding="utf-8")
        ex = HwExecutor(power_source=resolve_power_source(a.plan, a.power_source, a.diag_dir))
        m = json.loads((out / "meta.json").read_text(encoding="utf-8")); m["power_source"] = ex.power_source; m["plan"] = a.plan
        (out / "meta.json").write_text(json.dumps(m, indent=1), encoding="utf-8")
    else:
        from executors import SimExecutor
        out.mkdir(parents=True, exist_ok=True)
        ex = SimExecutor()
    return _finish(out, ex, a)


def _finish(out, ex, a):
    if a.trial or a.diag:
        try:
            for spec in (tl.trial_specs() if a.trial else tl.diag_specs()):
                ex.between_cells()
                cdir = out / "cells" / spec["id"]; cdir.mkdir(parents=True, exist_ok=True)
                t0 = time.time()
                m = ex.run(spec, cdir)
                (cdir / "cell.json").write_text(json.dumps(dict(id=spec["id"], spec=spec, metrics=m, executor=ex.name, wall_s=time.time() - t0), indent=1, default=str), encoding="utf-8")
                print(f"TRIAL {spec['id']}: " + ", ".join(f"{k}={v:.3f}" if isinstance(v, float) else f"{k}={v}" for k, v in m.items() if k in ("miss", "tok_s", "power_w", "power_sampled_w", "gov_reads_per_s", "power_source", "temp_after_c", "c0m", "clock_changes", "abandoned", "thermal_reason_bits", "sm_mhz_median", "exec_mode")) + f" ({time.time() - t0:.0f} s)", flush=True)
        finally:
            ex.close()
        return
    try:
        planner = None
        if a.plan == "t3b":
            if a.c0 is None:
                sys.exit("--plan t3b needs --c0 (the chosen c0 of the T1-T3 sitting)")
            planner = lambda r, c0=a.c0: tl.next_batch_t3b(r, c0)       # noqa: E731
        s = run_sitting(out, ex, limit=a.limit, deadline=None if a.max_hours is None else time.time() + 3600.0 * a.max_hours, planner=planner)
    finally:
        ex.close()
    sd = {str(p.relative_to(out)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(out.rglob("*")) if p.is_file() and p.name != "manifest.json"}
    (out / "manifest.json").write_text(json.dumps(sd, indent=0), encoding="utf-8")
    print(f"sitting ended: finished={s['finished']} stop={s.get('stop')} cells run in this call={s['cells_run']}; manifest of {len(sd)} files written")
    if s.get("stop"):
        sys.exit(3 if str(s["stop"]).startswith("deadline") else 2)


if __name__ == "__main__":
    main()
