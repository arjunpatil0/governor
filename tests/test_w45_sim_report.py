"""Paired comparison and decision-rule helpers for the simulator study (analysis/w45_sim_report.py; rules in docs/W45_SIM_PROTOCOL.md)."""
import numpy as np
import pandas as pd
import pytest

from w45_sim_report import earns_place, holds_slo, paired_diff


def _df(n=30, shift=0.0, miss_b=0.0, seed=0):
    rng = np.random.default_rng(seed)
    base = rng.normal(10, 1, n)
    rows = []
    for i in range(n):
        rows.append(dict(controller="A", scenario="S1", seed=200 + i, miss_frac=0.0, bg_tok_s=base[i] + shift, power_w=50.0, objective=base[i] + shift))
        rows.append(dict(controller="B", scenario="S1", seed=200 + i, miss_frac=miss_b, bg_tok_s=base[i], power_w=50.0, objective=base[i]))
    return pd.DataFrame(rows)


def test_holds_slo_needs_mean_and_90_percent_of_seeds_within_1_percent():
    ok = pd.DataFrame(dict(miss_frac=[0.0] * 28 + [0.02, 0.02]))
    assert holds_slo(ok.miss_frac) and not holds_slo(pd.Series([0.0] * 26 + [0.02] * 4))
    assert not holds_slo(pd.Series([0.0] * 29 + [0.5]))


def test_paired_diff_detects_a_shift_and_reports_n():
    r = paired_diff(_df(shift=0.5), "A", "B", "S1", "objective", seed=1)
    assert r["n"] == 30 and r["median"] == pytest.approx(0.5, abs=1e-9) and r["lo"] > 0


def test_paired_diff_uses_only_seeds_where_both_hold_the_slo():
    df = _df(shift=0.5, miss_b=0.0)
    df.loc[(df.controller == "B") & (df.seed < 210), "miss_frac"] = 0.05
    r = paired_diff(df, "A", "B", "S1", "objective", seed=1)
    assert r["n"] == 20


def test_paired_diff_with_no_effect_has_a_ci_covering_zero():
    r = paired_diff(_df(shift=0.0), "A", "B", "S1", "objective", seed=1)
    assert r["lo"] <= 0 <= r["hi"]


def test_earns_place_needs_a_win_in_s1_and_s4_and_no_loss_elsewhere():
    win = dict(lo=0.2, hi=1.0, median=0.5, n=30)
    tie = dict(lo=-0.3, hi=0.3, median=0.0, n=30)
    loss = dict(lo=-1.0, hi=-0.2, median=-0.5, n=30)
    base = {"S0": tie, "S1": win, "S1d": tie, "S2": tie, "S3": tie, "S4": win}
    assert earns_place(base)
    assert not earns_place({**base, "S4": tie})
    assert not earns_place({**base, "S2": loss})


def test_pareto_front_keeps_non_dominated_points_with_more_tokens_and_less_power():
    from w45_sim_report import pareto_front
    pts = {"x": (50.0, 80.0), "y": (30.0, 45.0), "z": (30.0, 60.0), "w": (50.0, 80.0)}
    assert pareto_front(pts) == {"x", "y", "w"}          # z is dominated by y; ties are not dominated


def test_round3_reading_requires_s5_wins_and_non_inferiority_by_the_ci_lower_bound():
    from w45_sim_round3 import earns_place_r3, paired_ratio
    df = pd.DataFrame([dict(controller=c, scenario="S0", seed=300 + i, feasible=True, bg_tok_s=v) for i in range(30) for c, v in (("A", 96.0 + 0.01 * i), ("B", 100.0 + 0.01 * i))])
    r = paired_ratio(df, "A", "B", "S0", seed=1)
    assert r["n"] == 30 and 0.95 < r["median"] < 0.97 and r["lo"] > 0.95
    win = dict(n=30, lo=0.5, hi=1.0, median=0.7)
    ni_ok, ni_bad = dict(n=30, lo=0.96, hi=1.0, median=0.98), dict(n=30, lo=0.90, hi=0.94, median=0.92)
    base = dict(s5_wins={"c'B": win, "g'B": win, "eB": win}, ni={"S0": ni_ok, "S2": ni_ok})
    assert earns_place_r3(base)
    assert not earns_place_r3(dict(base, ni={"S0": ni_bad, "S2": ni_ok}))
    assert not earns_place_r3(dict(base, s5_wins={"c'B": win, "g'B": dict(win, lo=-0.1), "eB": win}))
