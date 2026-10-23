"""Scoring and selection logic of the registered W5a model-selection protocol (analysis/w5a_select.py; docs/W5A_MODEL_SELECTION_PROTOCOL.md sections 2, 5, 6; plan addendum L):
the model's pick per stratum, REGRET and FALSE-FEASIBLE rate, asymmetric miss classification, interval coverage, the hard gates and the 10%-of-best rule with the simplicity order.
Instruction (Arjun, 2026-10-23): "write the grey-box cell-level predict function test-first, run the selection exactly as registered"."""
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "analysis"))
from w5a_select import classify, coverage, pick_and_score, select  # noqa: E402


def stratum(obs, pred, sig_p=1.0):
    """obs/pred rows: (tok_s, miss, power)."""
    o, p = np.array(obs, float), np.array(pred, float)
    return pick_and_score(o[:, 0], o[:, 1], o[:, 2], p[:, 0], p[:, 1], p[:, 2], sig_p)


def test_pick_is_the_predicted_best_feasible_and_regret_is_the_shortfall_to_the_observed_best():
    obs = [(50, 0.0, 50), (40, 0.0, 40), (80, 0.5, 70)]
    pred = [(45, 0.0, 50), (60, 0.0, 40), (90, 0.0, 70)]                              # row 3 is predicted miss-free but power 70 > 60: infeasible by prediction
    r = stratum(obs, pred)
    assert r["pick"] == 1 and r["best"] == 50 and abs(r["regret"] - 10.0) < 1e-9 and r["false_feasible"] is False


def test_an_observed_infeasible_pick_costs_the_full_best_and_counts_as_false_feasible():
    obs = [(50, 0.0, 50), (80, 0.3, 50)]
    pred = [(40, 0.0, 50), (80, 0.0, 50)]
    r = stratum(obs, pred)
    assert r["pick"] == 1 and r["false_feasible"] is True and r["regret"] == 50.0


def test_the_power_margin_uses_the_interval():
    obs = [(50, 0.0, 59), (30, 0.0, 40)]
    pred = [(50, 0.0, 59), (30, 0.0, 40)]
    assert stratum(obs, pred, sig_p=0.1)["pick"] == 0 and stratum(obs, pred, sig_p=2.0)["pick"] == 1      # 59 + 1.96 * 2 > 60


def test_no_pick_when_nothing_is_predicted_feasible_or_everything_predicts_fewer_than_one_token_per_second():
    obs = [(50, 0.0, 50)]
    assert stratum(obs, [(50, 0.5, 50)])["pick"] is None and stratum(obs, [(0.5, 0.0, 50)])["pick"] is None
    r = stratum(obs, [(50, 0.5, 50)])
    assert r["regret"] == 50.0 and r["false_feasible"] is None                          # a missed opportunity, not an unsafe pick


def test_stratum_without_an_observed_feasible_candidate_has_no_regret_but_a_pick_is_false_feasible():
    obs = [(50, 0.4, 50), (30, 0.0, 70)]
    r = stratum(obs, [(50, 0.0, 50), (10, 0.5, 50)])
    assert r["best"] == 0.0 and r["regret"] == 0.0 and r["false_feasible"] is True


def test_classification_reports_false_feasible_and_false_infeasible_separately():
    pred_ok = np.array([True, True, False, False, True])
    obs_ok = np.array([True, False, True, False, True])
    c = classify(pred_ok, obs_ok)
    assert c["false_feasible"] == 1 and c["false_infeasible"] == 1 and c["n"] == 5
    assert abs(c["false_feasible_of_predicted_feasible"] - 1 / 3) < 1e-9 and abs(c["false_infeasible_of_observed_feasible"] - 1 / 3) < 1e-9


def test_coverage_is_the_share_inside_the_interval():
    assert coverage(np.array([1.0, 2.0, 3.0, 4.0]), np.array([0.0, 0.0, 0.0, 0.0]), np.array([1.0, 2.0, 2.9, 5.0])) == 0.75


def metrics(name, ff=0.0, cov=0.94, lat=0.5e-3, p99=1.0, tok=1.0, pw=1.0, reg=0.0):
    return dict(name=name, false_feasible_rate=ff, coverage=dict(tok_s=cov, power_w=cov, p99=cov), latency_p99_s=lat, p99_err=p99, tok_mae=tok, power_mae=pw, regret_rel=reg)


ORDER = ["G", "HGB", "GP", "MLP"]


def test_selection_takes_the_simplest_candidate_within_ten_percent_of_the_best_that_passes_the_gates():
    ms = [metrics("G", p99=1.08, tok=1.05, pw=1.09, reg=0.08), metrics("HGB", p99=1.0, tok=1.0, pw=1.0, reg=0.0), metrics("GP", p99=1.0, tok=1.0, pw=1.0)]
    assert select(ms, ORDER)["selected"] == "G"                                       # 8% / 5% / 9% above the best and regret within +0.10


def test_a_worse_simple_model_is_skipped_for_a_better_one_and_gate_failures_are_excluded():
    ms = [metrics("G", p99=1.3), metrics("HGB", p99=1.05), metrics("MLP", p99=1.0, ff=0.08)]       # MLP is best but unsafe (false-feasible 8% > 5%)
    r = select(ms, ORDER)
    assert r["selected"] == "HGB" and "MLP" in r["failed_gates"] and r["failed_gates"]["MLP"] == ["G1 false-feasible 8.0% > 5%"]


def test_regret_uses_an_absolute_margin_and_blocks_a_simple_model():
    ms = [metrics("G", reg=0.25), metrics("HGB", reg=0.05)]
    assert select(ms, ORDER)["selected"] == "HGB"


def test_gate_failures_for_coverage_and_latency_are_named_and_nothing_is_selected_when_all_fail():
    ms = [metrics("G", cov=0.80), metrics("HGB", lat=2e-3)]
    r = select(ms, ORDER)
    assert r["selected"] is None and r["failed_gates"]["G"][0].startswith("G2") and r["failed_gates"]["HGB"][0].startswith("G3")
