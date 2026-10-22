"""POST-HOC round 2 of the power-budget simulator study (review 2026-10-22_w5_yaml_review.md finding 3; SIMULATION ONLY; round-1 results are unchanged).
Adds the unseen-workload scene S5 (S1 foreground, background with the fp16-proxy curve, knee 1050) that NO controller or static was tuned on, and the d'B v2 fixes (online token-time
model, quantised token-rate model, learned guard, multiplicative bg-power correction, 0.05 duty grid). d'B v2 constants are chosen on the TUNING seeds 100-109 over the L-plant scenarios
S0-S4 at both budgets only; then ONE new held-out evaluation on seeds 300-329 (round 1 used 200-229). g'B / c'B / eB keep their round-1 constants (tuned on the L plant); the
per-scenario oracle b'B for S5 is tuned on S5 tuning seeds (it knows the workload).
Writes data/sim_tuned_round2.json, data/w45_sim_round2.csv, data/w45_sim_round2.md.   Run: python analysis/w45_sim_round2.py"""
import concurrent.futures as cf
import dataclasses
import itertools
import json
import sys
import zlib
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "analysis"))
from controllers.common import ALLOWED_CLOCKS  # noqa: E402
from controllers.model import ModelController  # noqa: E402
from controllers.static import tune_static  # noqa: E402
from sim.params import load_params  # noqa: E402
from sim.plant import Plant, summarise  # noqa: E402
from sim.run import TUNING_SEEDS, load_tuned, run_matrix  # noqa: E402
from sim.scenarios import SCENARIOS, build  # noqa: E402
from w45_sim_budget import BUDGETS, _f, paired  # noqa: E402

ROUND2_SEEDS = tuple(range(300, 330))
EVAL_SCENARIOS = (*SCENARIOS, "S5")
CONTROLLERS = ("a", "g'B", "eB", "c'B", "d'B", "d'B2", "b'B")
GRID = dict(safety=(0.8, 0.9), switch_gain=(0.5, 2.0), clock_every=(10, 20), guard_k=(3.0,), sigma_w=(0.0, 1.0), guard_floor=(0.0, 0.05))
OUT_TUNED = ROOT / "data" / "sim_tuned_round2.json"


def _score(a):
    P, params = a
    cells, toks = [], []
    for b in BUDGETS:
        for scn in SCENARIOS:                                   # S0-S4 on the L plant; S5 is never used for tuning
            sc = build(scn)
            ss = [summarise(Plant(P, sc, seed=s).run(ModelController(P, "aligned", v2=True, power_budget_w=b, **params))) for s in TUNING_SEEDS]
            feas = np.array([(x["miss_frac"] <= 0.01) and (x["power_w"] <= b) for x in ss])
            cells.append(dict(budget=b, scenario=scn, frac_feasible=float(feas.mean()), mean_miss=float(np.mean([x["miss_frac"] for x in ss]))))
            toks.append(float(np.mean([x["bg_tok_s"] for x in ss])))
    holds = all(c["frac_feasible"] >= 0.9 and c["mean_miss"] <= 0.01 for c in cells)
    return dict(params=params, holds=holds, min_frac_feasible=min(c["frac_feasible"] for c in cells), tok_s_mean=float(np.mean(toks)), cells=cells)


def tune_v2(P, workers=8):
    keys = list(GRID)
    combos = [dict(zip(keys, v)) for v in itertools.product(*(GRID[k] for k in keys))]
    with cf.ProcessPoolExecutor(max_workers=workers) as ex:
        res = list(ex.map(_score, [(P, c) for c in combos], chunksize=1))
    ok = [r for r in res if r["holds"]]
    best = max(ok, key=lambda r: r["tok_s_mean"]) if ok else max(res, key=lambda r: (r["min_frac_feasible"], r["tok_s_mean"]))
    return dict(best, n_combos=len(res), n_holding=len(ok))


def _s5_job(a):
    P, b, clk = a
    return b, tune_static(P, "S5", "aligned", TUNING_SEEDS, clocks=(clk,), power_budget_w=b)


def tune_s5_oracle(P, workers=8):
    with cf.ProcessPoolExecutor(max_workers=workers) as ex:
        res = list(ex.map(_s5_job, [(P, b, c) for b in BUDGETS for c in ALLOWED_CLOCKS(P)], chunksize=1))
    out = {}
    for b in BUDGETS:
        rows = [r for bb, r in res if bb == b]
        ok = [r for r in rows if r["feasible"]]
        best = max(ok, key=lambda r: r["objective"]) if ok else min(rows, key=lambda r: (r["miss_max_seen"], r["power_max_seen"]))
        out[str(int(b))] = dict(action=dataclasses.asdict(best["action"]), tok_s=best["tok_s"], power_max_seen=best["power_max_seen"], feasible=best["feasible"])
    return out


def reading(df, b=60.0):
    """Pre-stated reading (review finding 2): d'B earns its place if it WINS (90% CI of the paired tok/s difference above 0) against c'B in S1 OR S5 under 60 W and does not LOSE (CI below 0) in S0 or S2.
    The stricter variant uses the best of g'B / eB as the comparator."""
    d = df[df.budget_w == b]
    out = {}
    for comp_name, comps in (("c'B", ("c'B",)), ("best simple (g'B, eB)", ("g'B", "eB"))):
        res = {}
        for scn in ("S0", "S1", "S2", "S5"):
            rs = [paired(d, "d'B2", c, scn, "bg_tok_s", zlib.crc32(f"r|{b}|{c}|{scn}".encode())) for c in comps]
            res[scn] = dict(win=all(r["n"] > 0 and r["lo"] > 0 for r in rs), loss=any(r["n"] > 0 and r["hi"] < 0 for r in rs), rows=rs)
        out[comp_name] = dict(by_scene=res, earns=bool((res["S1"]["win"] or res["S5"]["win"]) and not res["S0"]["loss"] and not res["S2"]["loss"]))
    return out


def report(dfs, tuned2, v2_info):
    L = ["# W4-5 simulator, ROUND 2 (POST-HOC / SENSITIVITY; SIMULATION ONLY; rounds 0-1 unchanged)", "",
         "Adds scene S5 (S1 foreground + UNSEEN background: fp16-proxy curve from data/w2_C_results.md, knee 1050; absolute rate scaled to the L unlocked rate, only the shape is from C) and d'B v2. "
         f"d'B v2 constants chosen on tuning seeds 100-109 over S0-S4 at both budgets ({v2_info['n_holding']} of {v2_info['n_combos']} parameter sets hold the SLO and budget in every cell); "
         "round-2 evaluation seeds 300-329 (new). g'B, c'B, eB keep round-1 constants tuned on the L plant; b'B for S5 is an oracle tuned on S5 tuning seeds. The plant is unchanged except for the S5 profile and the token-duration observation.", "",
         "Chosen d'B v2 constants:", "```", json.dumps(tuned2["params_v2"], indent=1), "```", ""]
    for b, df in dfs.items():
        L += [f"## Budget {b:.0f} W", ""]
        for scn in EVAL_SCENARIOS:
            sub = df[df.scenario == scn]
            rows = []
            for c in CONTROLLERS:
                x = sub[sub.controller == c]
                rows.append(dict(controller=c, mean_miss=x.miss_frac.mean(), pct_within_budget=100 * x.within.mean(), pct_feasible=100 * x.feasible.mean(), power_w_med=x.power_w.median(), tok_s_med=x.bg_tok_s.median(),
                                 tok_s_med_feasible=x[x.feasible].bg_tok_s.median() if x.feasible.any() else np.nan, holds=bool(x.feasible.mean() >= 0.9 and x.miss_frac.mean() <= 0.01)))
            L += [f"### {scn}", _f(pd.DataFrame(rows).set_index("controller"))]
        L += ["### Paired comparisons on tok/s (median of A - B over seeds where BOTH are feasible; 90% bootstrap CI)", ""]
        for a, c in (("d'B2", "c'B"), ("d'B2", "g'B"), ("d'B2", "eB"), ("d'B2", "b'B"), ("d'B2", "d'B"), ("c'B", "g'B")):
            rows = [dict(scenario=s, **paired(df, a, c, s, "bg_tok_s", zlib.crc32(f"{b}|{a}|{c}|{s}".encode()))) for s in EVAL_SCENARIOS]
            L += [f"#### {a} minus {c} (tok/s)", _f(pd.DataFrame(rows).set_index("scenario"), 3)]
    allf = pd.concat(dfs.values())
    rd = reading(allf)
    L += ["## Pre-stated reading at 60 W (review finding 2): does d'B (v2) earn its place?", ""]
    for name, r in rd.items():
        L.append(f"- comparator {name}: **{'EARNS ITS PLACE' if r['earns'] else 'DOES NOT EARN ITS PLACE'}**; " + "; ".join(f"{s}: win={v['win']} loss={v['loss']}" for s, v in r["by_scene"].items()))
    L += ["", "Rule: win (CI above 0) in S1 OR S5 and no loss (CI below 0) in S0 or S2. S5 is the held-out-workload scene; the S1 win alone does not decide the question for the strict comparator.", "",
          "## S5 oracle static settings (tuned on S5 tuning seeds; knows the workload)", "```", json.dumps(tuned2["s5_oracle"], indent=1), "```"]
    return L


def main():
    P = load_params(ROOT)
    v2 = tune_v2(P)
    s5 = tune_s5_oracle(P)
    tuned2 = dict(params_v2=v2["params"], s5_oracle=s5, v2_tuning={k: v for k, v in v2.items() if k != "cells"}, meta=dict(tuning_seeds=list(TUNING_SEEDS), eval_seeds=list(ROUND2_SEEDS)))
    OUT_TUNED.write_text(json.dumps(tuned2, indent=1), encoding="utf-8")
    print("tuned:", v2["params"], "holds" if v2["holds"] else "DOES NOT HOLD", f"{v2['n_holding']}/{v2['n_combos']}", flush=True)
    tuned = dict(load_tuned())
    fu = json.loads((ROOT / "data" / "sim_tuned_followup.json").read_text(encoding="utf-8"))
    tuned["global"] = {k: v["action"] for k, v in fu["global_nojit"].items()}
    bud = json.loads((ROOT / "data" / "sim_tuned_budget.json").read_text(encoding="utf-8"))["budget"]
    for b in BUDGETS:
        bud[str(int(b))]["static"]["S5"] = s5[str(int(b))]["action"]
    tuned["budget"], tuned["params_v2"] = bud, v2["params"]
    dfs = {}
    for b in BUDGETS:
        df = run_matrix(P, CONTROLLERS, EVAL_SCENARIOS, ROUND2_SEEDS, tuned, budget=b)
        df["within"], df["budget_w"] = df.power_w <= b, b
        df["feasible"] = (df.miss_frac <= 0.01) & df.within
        dfs[b] = df
    pd.concat(dfs.values()).to_csv(ROOT / "data" / "w45_sim_round2.csv", index=False)
    (ROOT / "data" / "w45_sim_round2.md").write_text("\n".join(report(dfs, tuned2, v2)), encoding="utf-8")
    print("written data/w45_sim_round2.md")


if __name__ == "__main__":
    main()
