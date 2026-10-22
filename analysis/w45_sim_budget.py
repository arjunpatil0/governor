"""POST-HOC power-budget rerun of the frozen simulator study (decision 2026-10-22: primary objective = maximise bg tok/s subject to the fg SLO AND a GPU power budget;
the lambda Pareto front stays secondary). Frozen results (data/w45_sim_results.md) are NOT changed. SIMULATION ONLY.
Budgets: 60 W ("AC-quiet") and 35 W ("battery-like") on the MEAN GPU power over the 55 s measurement window. Feasible run = fg miss fraction <= 1% AND mean power <= budget.
Controllers (aligned family): b'B per-scenario budget-tuned static, g'B scenario-agnostic budget-tuned static, eB = g'B + idle-triggered clock drop, c'B (PI on frame time + PI on
power throttling the token rate), d'B (model-based, constrained choice of clock and throttle with an online power-bias correction). Frozen constants of c' and d' are reused
(only the budget is added); the statics are tuned on the tuning seeds 100-109. Reference rows: a, and the unbudgeted e, c', d'.
Writes data/sim_tuned_budget.json, data/w45_sim_budget.csv, data/w45_sim_budget.md.   Run: python analysis/w45_sim_budget.py"""
import concurrent.futures as cf
import dataclasses
import json
import sys
import zlib
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from controllers.common import ALLOWED_CLOCKS  # noqa: E402
from controllers.static import tune_static, tune_static_global  # noqa: E402
from sim.params import load_params  # noqa: E402
from sim.plant import ASSUMPTIONS  # noqa: E402
from sim.run import EVAL_SEEDS, TUNING_SEEDS, load_tuned, run_matrix  # noqa: E402
from sim.scenarios import SCENARIOS  # noqa: E402

BUDGETS = (60.0, 35.0)
OUT_TUNED = ROOT / "data" / "sim_tuned_budget.json"
BUDGETED = ("b'B", "g'B", "eB", "c'B", "d'B")
REFERENCE = ("a", "e", "c'", "d'")


def _job(a):
    P, budget, scn, clk = a
    if scn == "GLOBAL":
        return budget, scn, tune_static_global(P, "aligned", TUNING_SEEDS, SCENARIOS, clocks=(clk,), power_budget_w=budget)
    return budget, scn, tune_static(P, scn, "aligned", TUNING_SEEDS, clocks=(clk,), power_budget_w=budget)


def _pick(rows):
    ok = [r for r in rows if r["feasible"]]
    return max(ok, key=lambda r: r["objective"]) if ok else min(rows, key=lambda r: (r["miss_max_seen"], r["power_max_seen"]))


def tune_budget(P, workers=8):
    clocks = ALLOWED_CLOCKS(P)
    jobs = [(P, b, s, c) for b in BUDGETS for s in (*SCENARIOS, "GLOBAL") for c in clocks]
    with cf.ProcessPoolExecutor(max_workers=workers) as ex:
        res = list(ex.map(_job, jobs, chunksize=1))
    out = {"meta": dict(seeds=list(TUNING_SEEDS), budgets=list(BUDGETS), note="chosen on tuning seeds only; docs/W45_PLAN.md addendum 2026-10-22"), "budget": {}}
    for b in BUDGETS:
        d = {"static": {}, "tuning": {}}
        for s in (*SCENARIOS, "GLOBAL"):
            best = _pick([r for bb, ss, r in res if bb == b and ss == s])
            act = dataclasses.asdict(best["action"])
            meta = {k: best[k] for k in ("tok_s", "power_w", "power_max_seen", "miss_max_seen", "feasible")}
            if s == "GLOBAL":
                d["global"] = act
            else:
                d["static"][s] = act
            d["tuning"][s] = meta
        out["budget"][str(int(b))] = d
    return out


def paired(df, a, b, scn, metric, seed):
    x, y = df[(df.scenario == scn) & (df.controller == a)].set_index("seed"), df[(df.scenario == scn) & (df.controller == b)].set_index("seed")
    seeds = [s for s in x.index.intersection(y.index) if x.loc[s, "feasible"] and y.loc[s, "feasible"]]
    if not seeds:
        return dict(n=0, median=np.nan, lo=np.nan, hi=np.nan)
    d = (x.loc[seeds, metric] - y.loc[seeds, metric]).to_numpy()
    meds = np.median(np.random.default_rng(seed).choice(d, size=(2000, len(d)), replace=True), axis=1)
    return dict(n=len(d), median=float(np.median(d)), lo=float(np.percentile(meds, 5)), hi=float(np.percentile(meds, 95)))


def _f(t, nd=2):
    return "```\n" + t.round(nd).to_string() + "\n```"


def report(df_by_budget, tuned):
    L = ["# W4-5 simulator: POWER-BUDGET rerun of the frozen study (POST-HOC / SENSITIVITY; SIMULATION ONLY; frozen results unchanged)", "",
         "Primary objective (decision 2026-10-22): maximise bg tok/s subject to fg SLO (miss <= 1%) AND mean GPU power <= budget; feasible run = both. Budgets 60 W and 35 W over the 55 s window. "
         f"Evaluation seeds {EVAL_SEEDS[0]}-{EVAL_SEEDS[-1]}; statics tuned on tuning seeds 100-109; c', d' keep their frozen constants and only receive the budget.", "",
         "Plant assumptions (unchanged): " + "; ".join(ASSUMPTIONS), "",
         "Caveat: the budget constrains MEAN power of the plant's time-weighted model (fg W1 fma power, bg L power, idle 5 W); real board power also has CPU-side/fan/idle terms not modelled.", ""]
    for b, df in df_by_budget.items():
        L += [f"## Budget {b:.0f} W", ""]
        for scn in SCENARIOS:
            sub = df[df.scenario == scn]
            rows = []
            for c in (*REFERENCE, *BUDGETED):
                x = sub[sub.controller == c]
                if x.empty:
                    continue
                rows.append(dict(controller=c, mean_miss=x.miss_frac.mean(), pct_within_budget=100 * x.within.mean(), pct_feasible=100 * x.feasible.mean(), power_w_med=x.power_w.median(),
                                 tok_s_med=x.bg_tok_s.median(), tok_s_med_feasible=x[x.feasible].bg_tok_s.median() if x.feasible.any() else np.nan,
                                 holds=bool(x.feasible.mean() >= 0.9 and x.miss_frac.mean() <= 0.01)))
            L += [f"### {scn}", _f(pd.DataFrame(rows).set_index("controller"))]
        L += ["### Paired comparisons on tok/s (median of A - B over seeds where BOTH runs are feasible; 90% bootstrap CI)", ""]
        for a, c in (("d'B", "c'B"), ("d'B", "g'B"), ("c'B", "g'B"), ("d'B", "eB"), ("eB", "g'B"), ("g'B", "b'B")):
            rows = [dict(scenario=s, **paired(df, a, c, s, "bg_tok_s", zlib.crc32(f"{b}|{a}|{c}|{s}".encode()))) for s in SCENARIOS]
            L += [f"#### {a} minus {c} (tok/s)", _f(pd.DataFrame(rows).set_index("scenario"), 3)]
    L += ["## Budget-tuned static settings (tuning seeds)", "", "```", json.dumps(tuned["budget"], indent=1), "```"]
    return L


def main():
    P = load_params(ROOT)
    tuned_budget = tune_budget(P)
    OUT_TUNED.write_text(json.dumps(tuned_budget, indent=1), encoding="utf-8")
    tuned = dict(load_tuned())
    fu = json.loads((ROOT / "data" / "sim_tuned_followup.json").read_text(encoding="utf-8"))
    tuned["global"] = {k: v["action"] for k, v in fu["global_nojit"].items()}
    tuned["budget"] = tuned_budget["budget"]
    out, frames = {}, []
    for b in BUDGETS:
        df = run_matrix(P, (*REFERENCE, *BUDGETED), SCENARIOS, EVAL_SEEDS, tuned, budget=b)
        df["within"] = df.power_w <= b
        df["feasible"] = (df.miss_frac <= 0.01) & df.within
        df["budget_w"] = b
        out[b] = df; frames.append(df)
    pd.concat(frames).to_csv(ROOT / "data" / "w45_sim_budget.csv", index=False)
    (ROOT / "data" / "w45_sim_budget.md").write_text("\n".join(report(out, tuned_budget)), encoding="utf-8")
    print("written data/w45_sim_budget.md")


if __name__ == "__main__":
    main()
