"""Scoring and selection logic of the redesigned W5a re-run (analysis/w5a_select2.py; docs/W5A_SELECTION_REDESIGN.md = plan addendum N): cross-conformal quantile, exact binomial CI,
the pick from (p_feas, p_act, ln tok/s, power) with the conformal power margin, regret only on strata with a feasible candidate, gates G1a/G1b/G2/G3 and the selection rule with the fixed fallback.
Instruction (Arjun, 2026-10-23): "Option A with the five conditions. Write and commit addendum N BEFORE the re-run"."""
import math
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "analysis"))
from w5a_select2 import clopper_pearson, conformal_q, pick2, regret_summary, select2  # noqa: E402


def test_conformal_q_is_the_ceil_n_plus_1_times_095_th_smallest_score():
    s = np.arange(1.0, 101.0)
    assert conformal_q(s) == 96.0                                              # ceil(101 * 0.95) = 96
    assert conformal_q(np.array([3.0, 1.0, 2.0])) == 3.0                       # rank 4 > n = 3: the largest
    assert math.isnan(conformal_q(np.array([])))


def test_clopper_pearson_matches_known_values():
    lo, hi = clopper_pearson(0, 10)
    assert lo == 0.0 and abs(hi - 0.3085) < 1e-3
    lo, hi = clopper_pearson(5, 10)
    assert abs(lo - 0.1871) < 1e-3 and abs(hi - 0.8129) < 1e-3
    assert math.isnan(clopper_pearson(0, 0)[0])


def stratum(obs, pred, q_power=1.0):
    o, p = np.array(obs, float), np.array(pred, float)          # obs: tok_s, feasible(0/1), power ; pred: p_feas, p_act, tok_s, power
    return pick2(o[:, 0], o[:, 1].astype(bool), o[:, 2], p[:, 0], p[:, 1], p[:, 2], p[:, 3], q_power)


def test_pick_needs_probability_activity_throughput_and_the_power_margin():
    obs = [(50, 1, 50), (40, 1, 40), (80, 0, 50)]
    pred = [(0.9, 0.9, 45, 50), (0.9, 0.9, 60, 40), (0.5, 0.9, 90, 50)]        # row 3: p_feas 0.5 < 0.8
    r = stratum(obs, pred)
    assert r["pick"] == 1 and r["best"] == 50 and abs(r["regret"] - 10.0) < 1e-9 and r["false_feasible"] is False
    assert stratum(obs, [(0.9, 0.9, 45, 59.5), (0.9, 0.9, 60, 59.5), (0.5, 0.9, 90, 50)], q_power=1.0)["pick"] is None      # 59.5 + 1.0 > 60 everywhere
    assert stratum(obs, [(0.9, 0.4, 45, 50), (0.9, 0.9, 0.5, 40), (0.5, 0.9, 90, 50)])["pick"] is None                       # inactive / below 1 tok/s


def test_unsafe_pick_costs_the_full_best_and_no_pick_is_not_false_feasible():
    obs = [(50, 1, 50), (80, 0, 50)]
    r = stratum(obs, [(0.9, 0.9, 40, 50), (0.95, 0.9, 80, 50)])
    assert r["pick"] == 1 and r["false_feasible"] is True and r["regret"] == 50.0
    r = stratum(obs, [(0.1, 0.9, 40, 50), (0.1, 0.9, 80, 50)])
    assert r["pick"] is None and r["false_feasible"] is None and r["regret"] == 50.0


def test_regret_is_summarised_only_over_strata_with_a_feasible_candidate():
    rs = [dict(best=50.0, regret=10.0, pick=1, false_feasible=False), dict(best=0.0, regret=0.0, pick=0, false_feasible=True), dict(best=30.0, regret=30.0, pick=None, false_feasible=None)]
    s = regret_summary(rs)
    assert s["strata_total"] == 3 and s["strata_with_feasible"] == 2 and abs(s["regret_rel"] - 40 / 80) < 1e-9
    assert s["picks"] == 2 and s["false_feasible_picks"] == 1 and abs(s["false_feasible_pick_rate"] - 0.5) < 1e-9 and len(s["false_feasible_pick_ci95"]) == 2


def m(name, ff_cell=0.0, ff_pick=0.0, cov=0.94, lat=5e-3, mu=0.3, pw=2.0, fi=0.2, reg=0.2):
    return dict(name=name, false_feasible_cell_rate=ff_cell, false_feasible_pick_rate=ff_pick, coverage=dict(mu=cov, power_w=cov), latency_p99_s=lat, mu_mae=mu, power_mae=pw, false_infeasible_rate=fi, regret_rel=reg)


ORDER = ["G", "HGB", "GP", "MLP"]


def test_gates_use_the_ten_ms_bound_and_name_each_failure():
    r = select2([m("G", ff_cell=0.08), m("HGB", ff_pick=0.2), m("GP", cov=0.8), m("MLP", lat=0.02)], ORDER)
    f = r["failed_gates"]
    assert r["selected"] is None and f["G"][0].startswith("G1a") and f["HGB"][0].startswith("G1b") and f["GP"][0].startswith("G2") and f["MLP"][0].startswith("G3")
    assert select2([m("G", lat=9.9e-3)], ORDER)["selected"] == "G"


def test_selection_rule_simplest_within_ten_percent_with_absolute_margins():
    ms = [m("G", mu=0.32, pw=2.1, fi=0.25, reg=0.28), m("HGB", mu=0.30, pw=2.0, fi=0.2, reg=0.2), m("MLP", mu=0.30, pw=2.0)]
    assert select2(ms, ORDER)["selected"] == "G"                                # 6.7% / 5% above best; false-infeasible +0.05; regret +0.08
    ms[0] = m("G", mu=0.40)
    assert select2(ms, ORDER)["selected"] == "HGB"


def test_the_fixed_fallback_is_reported_when_nothing_passes():
    r = select2([m("G", ff_cell=0.5)], ORDER)
    assert r["selected"] is None and "grey-box ModelController" in r["fallback"] and "did not discriminate" in r["fallback"]
