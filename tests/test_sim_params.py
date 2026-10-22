"""Simulator parameters (sim/params.py): every number is read from a committed result file; tests check the parse against the B and L files and the provenance registry."""
import re
from pathlib import Path

import pytest

from sim import params as sp
from w2_stats import find_knee

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def P():
    return sp.load_params(ROOT)


def _b_hb1_rows():
    txt = (ROOT / "data" / "w2_B_results.md").read_text(encoding="utf-8")
    rows = re.findall(r"^\s*fma_60hz\s+fma\s+(\d+)\s+([\d.]+)", txt, re.M)
    assert len(rows) == 3
    return {int(a): float(b) for a, b in rows}


def test_fg_time_ratio_matches_B_anchors_within_3_percent(P):
    for level, ratio in _b_hb1_rows().items():
        assert P.fg_ratio(level) == pytest.approx(ratio, rel=0.03)
    assert P.fg_ratio(1800) == pytest.approx(1.0)


def test_unlocked_fg_is_faster_than_1800_and_clock_above_range_is_rejected(P):
    assert P.fg_ratio(P.UNLOCKED_MHZ) == pytest.approx(0.732, abs=0.01)
    with pytest.raises(ValueError):
        P.fg_ratio(P.UNLOCKED_MHZ + 1)
    with pytest.raises(ValueError):
        P.fg_ratio(300)


def test_fg_ratio_monotone_in_clock(P):
    xs = [P.fg_ratio(f) for f in range(600, 2461, 60)]
    assert all(a >= b for a, b in zip(xs, xs[1:]))


def test_bg_tok_s_and_power_match_L_table_at_levels_and_interpolate(P):
    assert P.tok_s(1500) == pytest.approx(97.25)
    assert P.tok_s(P.UNLOCKED_MHZ) == pytest.approx(101.125)
    assert P.bg_power_w(1050) == pytest.approx(47.061375)
    assert P.tok_s(1050) < P.tok_s(1125) < P.tok_s(1200)


def test_fg_power_from_W1_fma_rows(P):
    assert P.fg_power_w(1800) == pytest.approx(44.5)
    assert P.fg_power_w(P.UNLOCKED_MHZ) == pytest.approx(79.9)


def test_q_s_from_G_and_share_divisor(P):
    assert P.q_ms == pytest.approx(0.374) and P.s_ms == pytest.approx(0.148)
    assert P.share_divisor_G == pytest.approx(2 + 2 * 0.148 / 0.374)


def test_plant_share_divisor_is_the_committed_A2_fit_and_stays_near_the_G_value(P):
    import json
    cal = json.loads((ROOT / "data" / "sim_calibration.json").read_text(encoding="utf-8"))
    assert P.share_divisor == pytest.approx(cal["share_divisor_fit"])
    assert min(cal["rmse_log_by_S"].values()) < 0.05
    assert abs(P.share_divisor / P.share_divisor_G - 1) < 0.15


def test_knee_from_L_table_is_1500(P):
    assert find_knee({k: v for k, v in P.rel_thr_L.items() if k != "unlocked"}) == 1500


def test_sa4_anchor_rows_parse(P):
    r = P.sa4["duty_fg4_d0.25"]
    assert r["lat_mean_ms"] == pytest.approx(6.098348) and r["overloaded"] is False
    assert P.sa4["duty_fg9_d0.5"]["overloaded"] is True


def test_idle_power_comes_from_a_quoted_source_that_exists(P):
    assert P.p_idle_w == pytest.approx(5.0)
    for name, (path, quote) in P.CONSTANT_SOURCES.items():
        assert quote in (ROOT / path).read_text(encoding="utf-8"), name


def test_clock_actuation_latency_is_the_audit_value(P):
    assert P.clock_latency_ms == pytest.approx(443.2346)
