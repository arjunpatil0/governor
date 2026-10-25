"""Freeze the tuned constants of the evaluation (plan addendum O-6 section 5): reads the decisions of the tuning sittings and writes data/w5b/constants.json, which is then COMMITTED; the evaluation runner
refuses a constants file whose sha256 differs from the one given on its command line (like the W5a cell list).
   python experiments/w5b/freeze.py --tuning data/w5b/tuning/decisions.json --t3b data/w5b/t3b/decisions.json --t3c data/w5b/t3c/decisions.json --out data/w5b/constants.json
c0 and g'B come from the T1-T3 sitting, d'B's margin from T3b, c'B's constants from T3c (the full 10-combination grid; when the miss rule is not met the fallback of addendum O-7 with the tolerance file
of o7.py, the registered lowest-miss pick kept in the record as c_b_registered). The headroom is recomputed from the T3b cells ONLY (addendum O-7). Rule flags are recorded, not hidden."""
import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import tune_lib as tl  # noqa: E402


def sha256_file(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def _t3b_headroom(t3b):
    cells = Path(t3b).parent / "cells"
    if not cells.is_dir():
        return None
    res = {}
    for f in cells.glob("*/cell.json"):
        c = json.loads(f.read_text(encoding="utf-8"))
        if c.get("metrics"):
            res[c["id"]] = c["metrics"]
    return tl.headroom_from_results(res)


def _ran_with(t3c, fallback):
    """The headroom the T3c confirmation cells (dbh_*) actually ran with, from their own spec."""
    ws = [json.loads(f.read_text(encoding="utf-8")).get("spec", {}).get("headroom_w") for f in (Path(t3c).parent / "cells").glob("dbh_*/cell.json")]
    ws = [w for w in ws if w is not None]
    return float(ws[0]) if ws else fallback


def build_constants(tuning, t3b, t3c, out, o7=None):
    t, b, c = (json.loads(Path(x).read_text(encoding="utf-8")) for x in (tuning, t3b, t3c))
    g = {k: (None if v is None else v["setting"]) for k, v in t["g_b"].items()}
    if "headroom" not in c or "d_b_headroom" not in c:
        raise SystemExit("refused: the T3c decisions lack the power headroom / its d'B confirmation (addendum O-6 amendment)")
    cbd = c["c_b"]
    reg = cbd["params"]
    if cbd["rule_met"]:
        sel, pick, tol = "registered (rule met)", reg, None
    else:
        if o7 is None:
            raise SystemExit("refused: the c'B miss rule is not met, so the O-7 fallback needs the tolerance file (experiments/w5b/o7.py)")
        tol = json.loads(Path(o7).read_text(encoding="utf-8"))
        if tol.get("d") is None or not cbd.get("grid"):
            raise SystemExit("refused: the O-7 tolerance or the T3c grid is missing")
        sel, pick = "O-7", tl.pick_cb_o7(cbd["grid"], tol["d"])["params"]
    head_t3b = _t3b_headroom(t3b)
    head = dict(head_t3b, source=f"T3b cells ({head_t3b['n_cells_sensor']} cells), recomputed by freeze.py (the T3c decisions.json carried {c['headroom']['w']:.3f} W from a merged set: addendum O-7)") if head_t3b else dict(c["headroom"], source="T3c decisions.json")
    git = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    keys = ("w", "sensor_p95_w", "spread_p95_w", "steady_target_w", "margin", "formula", "source", "n_cells_sensor", "n_cells_spread")
    mk = lambda p: dict(target=p["target"], ki=p["ki"], guard0=p.get("guard0", 0.5), gmin=p.get("gmin", 0.3))                    # noqa: E731
    const = dict(c0=t["c0"], g_b=g, c_b=mk(pick), c_b_selection=sel, c_b_registered=dict(mk(reg), status="registered pick, sensitivity only, NOT run in the evaluation" if sel == "O-7" else "same as c_b (rule met)"),
                 d_b=dict(margin=b["d_b"]["margin"]), power_source="sampled", headroom={k: head[k] for k in keys if k in head},
                 rules=dict(c_b_rule_met=cbd["rule_met"], c_b_at_grid_edge=cbd.get("at_grid_edge"), d_b_rule_met=b["d_b"]["rule_met"], d_b_headroom_rule_holds=c["d_b_headroom"]["rule_holds"], d_b_headroom_mean_miss=c["d_b_headroom"]["mean_miss"],
                            d_b_headroom_ran_with_w=_ran_with(t3c, c["headroom"]["w"]), g_b_feasible_cells={k: (None if v is None else v.get("feasible_cells")) for k, v in t["g_b"].items()}),
                 sources={f"{Path(x).parent.name}/{Path(x).name}": sha256_file(x) for x in (tuning, t3b, t3c) + ((o7,) if tol else ())}, git_head=git)
    if tol:
        const["o7"] = {k: tol[k] for k in ("d", "p95_abs_diff", "n_pairs", "n_cells", "formula") if k in tol}
    Path(out).write_text(json.dumps(const, indent=1), encoding="utf-8")
    return const


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tuning", required=True); ap.add_argument("--t3b", required=True); ap.add_argument("--t3c", required=True); ap.add_argument("--out", required=True)
    ap.add_argument("--o7", default=None, help="tolerance file of experiments/w5b/o7.py (required when the c'B miss rule is not met)")
    ap.add_argument("--write-sha", default=None, help="write the sha256 of the constants file to this path (used by the unattended chain)")
    a = ap.parse_args()
    const = build_constants(a.tuning, a.t3b, a.t3c, a.out, o7=a.o7)
    if a.write_sha:
        Path(a.write_sha).write_text(sha256_file(a.out), encoding="utf-8")
    print(json.dumps(const, indent=1))
    print("sha256 of", a.out, "=", sha256_file(a.out), "(commit the file, then pass this hash to evaluate.py --constants-sha256)")


if __name__ == "__main__":
    main()
