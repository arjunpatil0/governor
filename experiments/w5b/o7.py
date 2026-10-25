"""Addendum O-7 (decided after T3c, before any evaluation block): the miss tolerance d of the c'B fallback, estimated ONLY from existing replicate pairs.
A pair = two finished, non-discarded cells of the final controller code on the sampled power source (metrics.power_source == "sampled") with the same spec (kind, workload, scene, c0, params, setting, budget) found in
different cell directories (diag / T3b / T3c). Pairs whose specs also differ in the steering budget (the d'B cells re-run with the power headroom) are labelled near replicates; the pair set is fixed here, before the
fallback is applied, and nothing is tuned on it:
   python experiments/w5b/o7.py --dirs data/w5b/diag data/w5b/t3b data/w5b/t3c --out data/w5b/o7_tolerance.json"""
import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import tune_lib as tl  # noqa: E402


def _key(spec):
    sid = (spec.get("setting") or {}).get("sid")
    return json.dumps([spec.get("kind"), spec.get("workload"), spec.get("scene"), spec.get("c0"), spec.get("params"), sid, spec.get("budget_w")], sort_keys=True)


def collect_pairs(dirs):
    groups = defaultdict(list)
    for di, d in enumerate(dirs):
        for f in sorted((Path(d) / "cells").glob("*/cell.json")):
            c = json.loads(f.read_text(encoding="utf-8"))
            s, m = c.get("spec", {}), c.get("metrics")
            if not m or s.get("discard") or m.get("power_source") != "sampled" or m.get("miss") is None:
                continue
            groups[_key(s)].append(dict(dir=Path(d).name, order=di, id=c["id"], miss=float(m["miss"]), steer=s.get("steer_budget_w")))
    pairs = []
    for key, mem in groups.items():
        mem.sort(key=lambda x: (x["order"], x["id"]))
        for a, b in zip(mem, mem[1:]):
            if a["dir"] == b["dir"]:
                continue
            pairs.append(dict(type="replicate" if a["steer"] == b["steer"] else "near_replicate_steering_target", id_a=a["id"], id_b=b["id"], dir_a=a["dir"], dir_b=b["dir"], a=a["miss"], b=b["miss"],
                              steer_budget_w=[a["steer"], b["steer"]], spec=json.loads(key)))
    return sorted(pairs, key=lambda p: (p["type"], p["id_a"]))


def write_tolerance(dirs, out):
    pairs = collect_pairs(dirs)
    r = tl.replicate_tolerance(pairs)
    r["pairs"] = pairs
    r["dirs"] = [str(d) for d in dirs]
    r["note"] = "replicate = identical spec; near_replicate_steering_target = identical except the d'B steering budget (headroom): its difference includes that perturbation, so it can only widen d"
    Path(out).write_text(json.dumps(r, indent=1), encoding="utf-8")
    return r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dirs", nargs="+", required=True); ap.add_argument("--out", required=True)
    a = ap.parse_args()
    r = write_tolerance(a.dirs, a.out)
    for p in r["pairs"]:
        print(f"{p['type']:32s} {p['id_a']:40s} {p['a'] * 100:6.2f}%  {p['id_b']:40s} {p['b'] * 100:6.2f}%  |diff| {abs(p['a'] - p['b']) * 100:.3f} pts")
    print(f"n_pairs {r['n_pairs']}  p95|diff| {r['p95_abs_diff'] * 100:.3f} pts  d = {r['d'] * 100:.4f} pts ({r['d']:.6f})" if r["d"] is not None else "no pairs")
    print(r["formula"])


if __name__ == "__main__":
    main()
