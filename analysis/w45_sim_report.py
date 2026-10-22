"""Evaluation report for the W4-5 simulator study (SIMULATION ONLY; rules in docs/W45_SIM_PROTOCOL.md).
Runs the frozen controllers (data/sim_tuned.json) on the held-out evaluation seeds and writes data/w45_sim_results.md and data/w45_sim_eval.csv.
Run: python analysis/w45_sim_report.py"""
import json
import subprocess
import zlib
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from controllers.static import LAMBDA  # noqa: E402
from sim.params import load_params  # noqa: E402
from sim.plant import ASSUMPTIONS  # noqa: E402
from sim.run import CONTROLLERS, EVAL_SEEDS, TUNED_PATH, load_tuned, run_matrix  # noqa: E402
from sim.scenarios import C0_MS, SCENARIOS, SIGMA  # noqa: E402

SLO = 0.01
PAIRS = (("d", "c"), ("d'", "c'"), ("c'", "c"), ("d'", "d"), ("b'", "b"), ("c'", "b'"), ("d'", "b'"), ("c", "b"), ("d", "b"))


def holds_slo(miss):
    miss = pd.Series(miss).astype(float)
    return bool(miss.mean() <= SLO and (miss <= SLO).mean() >= 0.9)


def paired_diff(df, a, b, scenario, metric, seed=0, n_boot=2000, ci=0.90):
    """Median of (a - b) over evaluation seeds on which BOTH controllers meet the SLO in that run; percentile bootstrap CI of the median."""
    x = df[(df.scenario == scenario) & (df.controller == a)].set_index("seed")
    y = df[(df.scenario == scenario) & (df.controller == b)].set_index("seed")
    seeds = [s for s in x.index.intersection(y.index) if x.loc[s, "miss_frac"] <= SLO and y.loc[s, "miss_frac"] <= SLO]
    if not seeds:
        return dict(n=0, median=np.nan, lo=np.nan, hi=np.nan)
    d = (x.loc[seeds, metric] - y.loc[seeds, metric]).to_numpy()
    rng = np.random.default_rng(seed)
    meds = np.median(rng.choice(d, size=(n_boot, len(d)), replace=True), axis=1)
    return dict(n=len(d), median=float(np.median(d)), lo=float(np.percentile(meds, 100 * (1 - ci) / 2)), hi=float(np.percentile(meds, 100 * (1 + ci) / 2)))


def earns_place(by_scenario):
    """Protocol rule 3 on the objective difference (learned minus feedback): a win (CI above 0) in S1 and S4, and no loss (CI entirely below 0) in S0, S2, S3."""
    win = all(by_scenario[s]["n"] > 0 and by_scenario[s]["lo"] > 0 for s in ("S1", "S4"))
    no_loss = all(not (by_scenario[s]["n"] > 0 and by_scenario[s]["hi"] < 0) for s in ("S0", "S2", "S3"))
    return bool(win and no_loss)


def _fmt(df, nd=2):
    return "```\n" + df.round(nd).to_string() + "\n```"


def build_report(df, tuned):
    df = df.copy()
    df["objective"] = df.bg_tok_s - LAMBDA * df.power_w
    L = ["# W4-5 simulator study: controllers vs the plant (SIMULATION ONLY, held-out evaluation seeds)", "",
         f"Protocol: docs/W45_SIM_PROTOCOL.md (written before any controller ran). Evaluation seeds {EVAL_SEEDS[0]}-{EVAL_SEEDS[-1]} ({len(EVAL_SEEDS)}); tuning seeds 100-109; "
         f"controller constants frozen in data/sim_tuned.json. Foreground: 60 Hz periodic, deadline 16.667 ms, base cost {C0_MS} ms at 1800 MHz, jitter sigma {SIGMA} (assumption).",
         "Plant parameters come from committed results (sim/params.py); the time-slice share divisor is fitted to the A2 SA4 anchors (data/sim_calibration.json). "
         "These numbers are NOT hardware results; the plant is validated only by the hardware smoke and W5.", "",
         "Unmeasured assumptions in the plant:"] + [f"- {a}" for a in ASSUMPTIONS] + [""]
    slo = df.groupby(["scenario", "controller"]).miss_frac.agg(mean_miss="mean", pct_runs_ok=lambda s: 100 * (s <= SLO).mean()).reset_index()
    slo["holds_slo"] = [holds_slo(df[(df.scenario == r.scenario) & (df.controller == r.controller)].miss_frac) for r in slo.itertuples()]
    L += ["## 1. SLO (fg deadline-miss fraction <= 1%)", "", "`holds_slo`: mean miss <= 1% and >= 90% of seeds with miss <= 1% (protocol rule 1).", ""]
    for scn in SCENARIOS:
        t = slo[slo.scenario == scn].set_index("controller").loc[[c for c in CONTROLLERS if c in set(slo.controller)], ["mean_miss", "pct_runs_ok", "holds_slo"]]
        L += [f"### {scn}", _fmt(t, 4), ""]
    perf = df.groupby(["scenario", "controller"])[["bg_tok_s", "power_w", "objective", "j_per_token", "clock_changes"]].median().reset_index()
    L += ["## 2. Performance (median over all evaluation seeds; compare only where the SLO holds)", ""]
    for scn in SCENARIOS:
        t = perf[perf.scenario == scn].set_index("controller").loc[[c for c in CONTROLLERS if c in set(perf.controller)]].drop(columns="scenario")
        t["holds_slo"] = slo[slo.scenario == scn].set_index("controller").holds_slo
        L += [f"### {scn}", _fmt(t, 2), ""]
    L += ["## 3. Paired comparisons (median of A - B over seeds where both meet the SLO; 90% bootstrap CI)", ""]
    verdicts = {}
    for a, b in PAIRS:
        if a not in set(df.controller) or b not in set(df.controller):
            continue
        rows = []
        for scn in SCENARIOS:
            for m in ("objective", "bg_tok_s", "power_w"):
                r = paired_diff(df, a, b, scn, m, seed=zlib.crc32(f"{a}|{b}|{scn}|{m}".encode()))
                rows.append(dict(scenario=scn, metric=m, **r))
        t = pd.DataFrame(rows)
        L += [f"### {a} minus {b}", _fmt(t.set_index(["scenario", "metric"]), 3), ""]
        verdicts[(a, b)] = {r.scenario: dict(n=r.n, median=r.median, lo=r.lo, hi=r.hi) for r in t[t.metric == "objective"].itertuples()}
    L += ["## 4. Does the learned part earn its place? (protocol rule 3, objective = tok/s - 0.5 W)", ""]
    for a, b in (("d", "c"), ("d'", "c'")):
        if (a, b) in verdicts:
            ok = earns_place(verdicts[(a, b)])
            L.append(f"- {a} vs {b}: **{'EARNS ITS PLACE' if ok else 'DOES NOT EARN ITS PLACE'}** under the pre-registered rule (a win with CI above 0 in S1 and S4, no loss in S0/S2/S3).")
    L += ["", "## 5. Frozen controller constants", "", "```", json.dumps(tuned.get("params", {}), indent=1), "```", "",
          "Best-static settings are in data/sim_tuned.json (per scenario, tuned on the tuning seeds). Static settings are per-scenario oracles; the dynamic controllers use one parameter set for all scenarios."]
    return L


def main():
    P = load_params(ROOT)
    tuned = load_tuned()
    assert tuned, "run sim/tune.py and commit data/sim_tuned.json before the evaluation"
    git = subprocess.run(["git", "status", "--porcelain", str(TUNED_PATH)], capture_output=True, text=True, cwd=ROOT).stdout.strip()
    assert not git, "data/sim_tuned.json must be committed before the evaluation runs (protocol: parameters frozen first)"
    df = run_matrix(P, CONTROLLERS, SCENARIOS, EVAL_SEEDS, tuned)
    df.to_csv(ROOT / "data" / "w45_sim_eval.csv", index=False)
    L = build_report(df, tuned)
    (ROOT / "data" / "w45_sim_results.md").write_text("\n".join(L), encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    main()
