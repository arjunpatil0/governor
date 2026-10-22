"""Tune controller constants and the best-static settings on the TUNING seeds only (docs/W45_SIM_PROTOCOL.md), write data/sim_tuned.json.
Selection rule per controller: among parameter sets that hold the SLO in every scenario on the tuning seeds (mean miss <= 1% and <= 1% in >= 90% of seeds),
the highest mean objective (bg tok/s - 0.5 x power W); if none holds it, the set with the smallest worst-scenario miss fraction (reported as a failure).
Run: python sim/tune.py   (simulation only)."""
import concurrent.futures as cf
import dataclasses
import itertools
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from controllers.model import ModelController  # noqa: E402
from controllers.pi import PIController  # noqa: E402
from controllers.static import LAMBDA, tune_static  # noqa: E402
from sim.params import load_params  # noqa: E402
from sim.plant import Plant, summarise  # noqa: E402
from sim.run import TUNED_PATH, TUNING_SEEDS  # noqa: E402
from sim.scenarios import SCENARIOS, build  # noqa: E402

GRIDS = {
    "c": dict(clock_margin=(0.35, 0.4, 0.5, 0.6), kp=(0.1, 0.3, 0.5), ki=(0.03, 0.08, 0.15), target=(0.5, 0.65, 0.8)),
    "c'": dict(ki=(0.05, 0.15, 0.3), target=(0.65, 0.8, 0.9), guard0=(0.5, 1.0, 2.0), gmin=(0.3, 0.5, 1.0)),
    "d": dict(safety=(0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9), gamma_alpha=(0.05, 0.1, 0.2), switch_gain=(0.5, 2.0)),     # round 2 (2026-10-22): round 1 had safety 0.6-0.9, no set held the SLO
    "d'": dict(safety=(0.8, 0.9), switch_gain=(0.5, 2.0, 5.0), clock_every=(10, 20)),
}


def build_ctl(P, name, params):
    return PIController(P, "unaligned" if name == "c" else "aligned", **params) if name in ("c", "c'") else ModelController(P, "unaligned" if name == "d" else "aligned", **params)


def score(args):
    P, name, params, seeds = args
    per_sc, objs = {}, []
    for scn in SCENARIOS:
        sc = build(scn)
        ss = [summarise(Plant(P, sc, seed=s).run(build_ctl(P, name, params))) for s in seeds]
        miss = np.array([x["miss_frac"] for x in ss])
        per_sc[scn] = dict(mean_miss=float(miss.mean()), frac_seeds_ok=float((miss <= 0.01).mean()))
        objs.append(float(np.mean([x["bg_tok_s"] - LAMBDA * x["power_w"] for x in ss])))
    holds = all(v["mean_miss"] <= 0.01 and v["frac_seeds_ok"] >= 0.9 for v in per_sc.values())
    return dict(params=params, holds=holds, worst_mean_miss=max(v["mean_miss"] for v in per_sc.values()), objective=float(np.mean(objs)), per_scenario=per_sc)


def tune_controller(P, name, seeds, workers=8):
    keys = list(GRIDS[name])
    combos = [dict(zip(keys, v)) for v in itertools.product(*(GRIDS[name][k] for k in keys))]
    with cf.ProcessPoolExecutor(max_workers=workers) as ex:
        res = list(ex.map(score, [(P, name, c, seeds) for c in combos], chunksize=1))
    ok = [r for r in res if r["holds"]]
    best = max(ok, key=lambda r: r["objective"]) if ok else min(res, key=lambda r: (r["worst_mean_miss"], -r["objective"]))
    return dict(best, n_combos=len(res), n_holding=len(ok))


def _static_job(args):
    P, scn, pacing, seeds = args
    r = tune_static(P, scn, pacing, seeds)
    a = r["action"]
    return scn, pacing, dict(action=dataclasses.asdict(a), tok_s=r["tok_s"], power_w=r["power_w"], miss_max_seen=r["miss_max_seen"], feasible=r["feasible"])


def tune_all(P, seeds=TUNING_SEEDS, workers=8):
    out = dict(meta=dict(seeds=list(seeds), lam=LAMBDA, note="chosen on tuning seeds only; docs/W45_SIM_PROTOCOL.md"), params={}, static={s: {} for s in SCENARIOS}, tuning={})
    with cf.ProcessPoolExecutor(max_workers=workers) as ex:
        for scn, pacing, r in ex.map(_static_job, [(P, s, p, seeds) for s in SCENARIOS for p in ("unaligned", "aligned")]):
            out["static"][scn]["b" if pacing == "unaligned" else "b'"] = dict(**r["action"])
            out["tuning"][f"static/{scn}/{pacing}"] = {k: v for k, v in r.items() if k != "action"}
    for name in GRIDS:
        r = tune_controller(P, name, seeds, workers)
        out["params"][name] = r["params"]
        out["tuning"][name] = {k: v for k, v in r.items() if k != "params"}
        print(name, "holds" if r["holds"] else "FAILS", r["params"], "obj %.2f worst miss %.4f (%d/%d combos hold)" % (r["objective"], r["worst_mean_miss"], r["n_holding"], r["n_combos"]), flush=True)
    return out


if __name__ == "__main__":
    P = load_params(ROOT)
    if len(sys.argv) > 2 and sys.argv[1] == "--only":              # re-tune one controller, keep the rest of data/sim_tuned.json
        res = json.loads(TUNED_PATH.read_text(encoding="utf-8"))
        r = tune_controller(P, sys.argv[2], TUNING_SEEDS)
        res["params"][sys.argv[2]] = r["params"]
        res["tuning"][sys.argv[2]] = {k: v for k, v in r.items() if k != "params"}
        print(sys.argv[2], "holds" if r["holds"] else "FAILS", r["params"], "obj %.2f worst miss %.4f (%d/%d)" % (r["objective"], r["worst_mean_miss"], r["n_holding"], r["n_combos"]))
        TUNED_PATH.write_text(json.dumps(res, indent=1), encoding="utf-8")
        sys.exit(0)
    res = tune_all(P)
    TUNED_PATH.write_text(json.dumps(res, indent=1), encoding="utf-8")
    print("written", TUNED_PATH)
