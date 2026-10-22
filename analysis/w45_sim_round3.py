"""POST-HOC round 3 of the power-budget simulator study - the LAST simulator round (reviewer note 2026-10-22: after it the sim work is frozen, because the smoke showed the plant's token
timing is wrong). SIMULATION ONLY; rounds 0-2 unchanged. d'B v3 = v2 + guard learned from the observed slack overrun + idle branch that respects the budget + a power loop on the model duty.
v3 constants are chosen on the TUNING seeds 100-109 over S0-S4 at both budgets (S5 never used); then ONE held-out evaluation on NEW seeds 400-429.
Pre-registered reading (reviewer, 2026-10-22), 60 W: d'B3 earns its place only if (i) it WINS in S5 (90% CI of the paired tok/s difference above 0) against EACH of c'B, g'B, eB, and (ii) it is NON-INFERIOR in S0 and S2:
the 90% CI lower bound of the paired ratio d'B3 / best-comparator tok/s is >= 0.95 (best comparator = highest median among c'B, g'B, eB in that scene). An S1 win is reported, not required.
Writes data/sim_tuned_round3.json, data/w45_sim_round3.csv, data/w45_sim_round3.md.   Run: python analysis/w45_sim_round3.py"""
import concurrent.futures as cf
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
from controllers.model import ModelController  # noqa: E402
from sim.params import load_params  # noqa: E402
from sim.plant import Plant, summarise  # noqa: E402
from sim.run import TUNING_SEEDS, load_tuned, run_matrix  # noqa: E402
from sim.scenarios import SCENARIOS, build  # noqa: E402
from w45_sim_budget import BUDGETS, _f, paired  # noqa: E402

ROUND3_SEEDS = tuple(range(400, 430))
EVAL_SCENARIOS = (*SCENARIOS, "S5")
CONTROLLERS = ("a", "g'B", "eB", "c'B", "d'B2", "d'B3", "b'B")
GRID = dict(safety=(0.8,), switch_gain=(0.5, 2.0), clock_every=(10, 20), guard_k=(3.0,), sigma_w=(0.0, 1.0), guard_floor=(0.0, 0.05), power_gain=(0.01, 0.03))
OUT_TUNED = ROOT / "data" / "sim_tuned_round3.json"
NI_MARGIN = 0.95


def paired_ratio(df, a, b, scn, seed, n_boot=2000, ci=0.90):
    """Median of the per-seed ratio tok/s(a) / tok/s(b) over seeds where BOTH are feasible; percentile bootstrap CI of the median."""
    x, y = df[(df.scenario == scn) & (df.controller == a)].set_index("seed"), df[(df.scenario == scn) & (df.controller == b)].set_index("seed")
    seeds = [s for s in x.index.intersection(y.index) if x.loc[s, "feasible"] and y.loc[s, "feasible"] and y.loc[s, "bg_tok_s"] > 0]
    if not seeds:
        return dict(n=0, median=np.nan, lo=np.nan, hi=np.nan)
    r = (x.loc[seeds, "bg_tok_s"] / y.loc[seeds, "bg_tok_s"]).to_numpy()
    meds = np.median(np.random.default_rng(seed).choice(r, size=(n_boot, len(r)), replace=True), axis=1)
    return dict(n=len(r), median=float(np.median(r)), lo=float(np.percentile(meds, 100 * (1 - ci) / 2)), hi=float(np.percentile(meds, 100 * (1 + ci) / 2)))


def earns_place_r3(res):
    """res = dict(s5_wins={comparator: paired-difference result}, ni={'S0': ratio result, 'S2': ratio result})."""
    win = all(r["n"] > 0 and r["lo"] > 0 for r in res["s5_wins"].values())
    ni = all(r["n"] > 0 and r["lo"] >= NI_MARGIN for r in res["ni"].values())
    return bool(win and ni)


def _score(a):
    P, params = a
    cells, toks = [], []
    for b in BUDGETS:
        for scn in SCENARIOS:
            sc = build(scn)
            ss = [summarise(Plant(P, sc, seed=s).run(ModelController(P, "aligned", v2=True, v3=True, power_budget_w=b, **params))) for s in TUNING_SEEDS]
            feas = np.array([(x["miss_frac"] <= 0.01) and (x["power_w"] <= b) for x in ss])
            cells.append(dict(budget=b, scenario=scn, frac_feasible=float(feas.mean()), mean_miss=float(np.mean([x["miss_frac"] for x in ss]))))
            toks.append(float(np.mean([x["bg_tok_s"] for x in ss])))
    holds = all(c["frac_feasible"] >= 0.9 and c["mean_miss"] <= 0.01 for c in cells)
    return dict(params=params, holds=holds, min_frac_feasible=min(c["frac_feasible"] for c in cells), tok_s_mean=float(np.mean(toks)), failing=[c for c in cells if c["frac_feasible"] < 0.9 or c["mean_miss"] > 0.01])


def tune_v3(P, workers=8):
    keys = list(GRID)
    combos = [dict(zip(keys, v)) for v in itertools.product(*(GRID[k] for k in keys))]
    with cf.ProcessPoolExecutor(max_workers=workers) as ex:
        res = list(ex.map(_score, [(P, c) for c in combos], chunksize=1))
    ok = [r for r in res if r["holds"]]
    best = max(ok, key=lambda r: r["tok_s_mean"]) if ok else max(res, key=lambda r: (r["min_frac_feasible"], r["tok_s_mean"]))
    return dict(best, n_combos=len(res), n_holding=len(ok))


def report(dfs, tuned3, v3):
    L = ["# W4-5 simulator, ROUND 3 (LAST simulator round; POST-HOC; SIMULATION ONLY; rounds 0-2 unchanged)", "",
         f"d'B v3 constants chosen on tuning seeds 100-109 over S0-S4 at both budgets ({v3['n_holding']} of {v3['n_combos']} parameter sets hold SLO and budget in every cell); evaluation on NEW seeds 400-429. "
         "g'B, eB, c'B, b'B and the S5 oracle keep their earlier constants; d'B2 = the round-2 controller with its round-2 constants. The plant is unchanged except for the overrun observation.", "",
         "Chosen d'B v3 constants:", "```", json.dumps(tuned3["params_v3"], indent=1), "```", ""]
    if v3["failing"]:
        L += ["**Tuning criterion NOT met in these cells:** " + json.dumps(v3["failing"]), ""]
    for b, df in dfs.items():
        L += [f"## Budget {b:.0f} W", ""]
        for scn in EVAL_SCENARIOS:
            sub = df[df.scenario == scn]
            rows = []
            for c in CONTROLLERS:
                x = sub[sub.controller == c]
                rows.append(dict(controller=c, mean_miss=x.miss_frac.mean(), pct_feasible=100 * x.feasible.mean(), power_w_med=x.power_w.median(), tok_s_med=x.bg_tok_s.median(),
                                 holds=bool(x.feasible.mean() >= 0.9 and x.miss_frac.mean() <= 0.01)))
            L += [f"### {scn}", _f(pd.DataFrame(rows).set_index("controller"))]
        L += ["### Paired tok/s difference, d'B3 minus comparator (median, 90% CI; seeds where both feasible)", ""]
        for c in ("c'B", "g'B", "eB", "d'B2", "b'B"):
            rows = [dict(scenario=s, **paired(df, "d'B3", c, s, "bg_tok_s", zlib.crc32(f"{b}|{c}|{s}".encode()))) for s in EVAL_SCENARIOS]
            L += [f"#### d'B3 minus {c}", _f(pd.DataFrame(rows).set_index("scenario"), 3)]
    d60 = dfs[60.0]
    res = dict(s5_wins={c: paired(d60, "d'B3", c, "S5", "bg_tok_s", zlib.crc32(f"w|{c}".encode())) for c in ("c'B", "g'B", "eB")}, ni={})
    L += ["## Pre-registered reading at 60 W (reviewer 2026-10-22)", ""]
    for scn in ("S0", "S2"):
        sub = d60[d60.scenario == scn]
        best = max(("c'B", "g'B", "eB"), key=lambda c: sub[sub.controller == c].bg_tok_s.median())
        res["ni"][scn] = paired_ratio(d60, "d'B3", best, scn, zlib.crc32(f"ni|{scn}".encode()))
        L.append(f"- {scn}: best comparator {best}; ratio d'B3/{best} median {res['ni'][scn]['median']:.3f}, 90% CI [{res['ni'][scn]['lo']:.3f}, {res['ni'][scn]['hi']:.3f}] (non-inferior if lower bound >= {NI_MARGIN})")
    for c, r in res["s5_wins"].items():
        L.append(f"- S5 vs {c}: median diff {r['median']:.2f} tok/s, 90% CI [{r['lo']:.2f}, {r['hi']:.2f}]")
    L += ["", f"**d'B3 {'EARNS ITS PLACE' if earns_place_r3(res) else 'DOES NOT EARN ITS PLACE'}** under the reading: S5 win against all three comparators AND non-inferior (>= {NI_MARGIN}) in S0 and S2. "
          "Simulation only; the plant's token timing is known to be wrong (smoke), so this is not evidence about hardware."]
    return L


def main():
    P = load_params(ROOT)
    v3 = tune_v3(P)
    tuned3 = dict(params_v3=v3["params"], v3_tuning={k: v for k, v in v3.items() if k != "params"}, meta=dict(tuning_seeds=list(TUNING_SEEDS), eval_seeds=list(ROUND3_SEEDS)))
    OUT_TUNED.write_text(json.dumps(tuned3, indent=1), encoding="utf-8")
    print("tuned:", v3["params"], "holds" if v3["holds"] else "DOES NOT HOLD", f"{v3['n_holding']}/{v3['n_combos']}", flush=True)
    tuned = dict(load_tuned())
    fu = json.loads((ROOT / "data" / "sim_tuned_followup.json").read_text(encoding="utf-8"))
    tuned["global"] = {k: v["action"] for k, v in fu["global_nojit"].items()}
    bud = json.loads((ROOT / "data" / "sim_tuned_budget.json").read_text(encoding="utf-8"))["budget"]
    r2 = json.loads((ROOT / "data" / "sim_tuned_round2.json").read_text(encoding="utf-8"))
    for b in BUDGETS:
        bud[str(int(b))]["static"]["S5"] = r2["s5_oracle"][str(int(b))]["action"]
    tuned["budget"], tuned["params_v2"], tuned["params_v3"] = bud, r2["params_v2"], v3["params"]
    dfs = {}
    for b in BUDGETS:
        df = run_matrix(P, CONTROLLERS, EVAL_SCENARIOS, ROUND3_SEEDS, tuned, budget=b)
        df["within"], df["budget_w"] = df.power_w <= b, b
        df["feasible"] = (df.miss_frac <= 0.01) & df.within
        dfs[b] = df
    pd.concat(dfs.values()).to_csv(ROOT / "data" / "w45_sim_round3.csv", index=False)
    (ROOT / "data" / "w45_sim_round3.md").write_text("\n".join(report(dfs, tuned3, v3)), encoding="utf-8")
    print("written data/w45_sim_round3.md")


if __name__ == "__main__":
    main()
