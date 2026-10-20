"""Pre-registered W2 decision logic (analysis/w2_analysis.py) on synthetic inputs whose right answer is known by construction.
The yaml (experiments/w2_colocation.yaml) defines every rule tested here."""
import numpy as np
import pandas as pd
import pytest

from w2_analysis import classify_ha1, ha1, ha2, hb1, hb2, hc1, sa1_label

M = (0.25, 0.5, 1, 2, 4, 8)
C = (0.0, 0.5, 1.0)


def _cells(obs_fn, noise=0.01, blocks=10, seed=0):
    """18 background cells x blocks; pred = m(1+c^2)/2 (rho = 1); obs from obs_fn(pred, m, c) plus noise."""
    rng = np.random.default_rng(seed)
    rows = []
    for b in range(blocks):
        for m in M:
            for c in C:
                pred = m * (1 + c * c) / 2
                rows.append(dict(block=b, cell_id=f"m{m}_c{c}", m_ms=m, cv=c, pred_ms=pred, obs_ms=obs_fn(pred, m, c) + rng.normal(0, noise)))
    return pd.DataFrame(rows)


# ---- HA1 -------------------------------------------------------------------------------------------
def test_ha1_supported_when_wait_follows_prediction():
    r = ha1(_cells(lambda p, m, c: p))
    assert r["supported"] and r["equivalent"] and r["frac_within25"] >= 0.7


def test_constant_switch_cost_lands_in_the_intercept_but_fails_the_registered_25pct_rule():
    # Property of the REGISTERED rule, recorded so it is not a surprise: wait = pred + 0.3 ms keeps the slope ~1 and puts the cost in the
    # intercept (review finding 1), but cell medians of the small-pred cells are then >25% off, so criterion (ii) fails and HA1 is not supported.
    r = ha1(_cells(lambda p, m, c: p + 0.3))
    assert r["equivalent"] and r["intercept"] == pytest.approx(0.3, abs=0.05)
    assert r["frac_within25"] < 0.7 and not r["supported"]


def test_ha1_not_supported_and_classified_preempted_when_wait_is_far_below_prediction():
    cells = _cells(lambda p, m, c: 0.3 * p + 0.05)
    r = ha1(cells)
    assert not r["supported"]
    assert classify_ha1(cells, r) == "preempted_or_concurrent"


def test_ha1_classified_scheduler_capped_when_wait_plateaus_while_prediction_grows():
    cells = _cells(lambda p, m, c: p if m <= 1 else 1.5)
    r = ha1(cells)
    assert not r["supported"]
    assert classify_ha1(cells, r) == "scheduler_capped"


def test_ha1_classified_other_when_wait_is_double_the_prediction():
    cells = _cells(lambda p, m, c: 2.0 * p)                       # slope 2: fails equivalence, neither preempted nor capped
    assert not ha1(cells)["supported"]
    assert classify_ha1(cells, ha1(cells)) == "other"


def test_classify_returns_supported_when_ha1_holds():
    cells = _cells(lambda p, m, c: p)
    assert classify_ha1(cells, ha1(cells)) == "supported"


def test_ha1_needs_both_conditions():
    # +0.3 ms on the six smallest-m cells: slope stays ~1 (equivalent) but only 12 of 18 cells are within +/-25% (0.667 < 0.7)
    cells = _cells(lambda p, m, c: p + (0.3 if m <= 0.5 else 0.0), noise=0.005)
    r = ha1(cells)
    assert r["equivalent"] and r["frac_within25"] < 0.7 and not r["supported"]


# ---- HA2 -------------------------------------------------------------------------------------------
def test_ha2_supported_when_variance_raises_wait():
    r = ha2(_cells(lambda p, m, c: p, noise=0.005))                # model: wait grows with (1 + c^2)
    assert r["supported"] and r["n_sig"] == 6
    assert set(r["table"].columns) >= {"m_ms", "p", "p_holm", "significant"}


def test_ha2_not_supported_when_wait_ignores_variance():
    cells = _cells(lambda p, m, c: m / 2, noise=0.005)
    r = ha2(cells)
    assert not r["supported"] and r["n_sig"] < 4


# ---- HB1 / HB2 -------------------------------------------------------------------------------------
REL = {"fma": {900: 0.366, 1200: 0.488, 1500: 0.609, 1800: 0.732}, "mem": {900: 0.889, 1200: 0.993, 1500: 0.997, 1800: 0.998}}


def _frames(scale, blocks=10, noise=0.003, seed=1):
    rng = np.random.default_rng(seed)
    rows = []
    for b in range(blocks):
        for frame, kind in (("fma_60hz", "fma"), ("fma_120hz", "fma"), ("mem_60hz", "mem")):
            for lv in (900, 1200, 1500, 1800):
                svc = (8.86 if kind == "fma" else 8.9) * (REL[kind][1800] / REL[kind][lv]) * scale(kind, lv)
                rows.append(dict(block=b, frame=frame, kind=kind, level=lv, service_ms=svc * (1 + rng.normal(0, noise))))
    return pd.DataFrame(rows)


def test_hb1_uses_the_1800_reference_and_passes_when_w1_scaling_holds():
    r = hb1(_frames(lambda k, lv: 1.0), REL)
    assert r["supported"]
    row = r["table"].query("frame == 'fma_60hz' and level == 1200").iloc[0]
    assert row["pred"] == pytest.approx(0.732 / 0.488) and row["ok"]


def test_hb1_fails_when_service_slows_more_than_w1_predicts():
    r = hb1(_frames(lambda k, lv: 1.25 if (k == "fma" and lv == 1200) else 1.0), REL)
    assert not r["supported"]
    assert not r["table"].query("frame == 'fma_60hz' and level == 1200").iloc[0]["ok"]


def _misses(miss_fn, blocks=10, seed=4):
    rng = np.random.default_rng(seed)
    return pd.DataFrame([dict(block=b, level=lv, miss_frac=float(np.clip(miss_fn(lv) + rng.normal(0, 0.01), 0, 1)),
                              service_ms=8.86 / REL["fma"][lv]) for b in range(blocks) for lv in (900, 1200, 1500, 1800)])


def test_hb2_requires_significance_only_where_predicted_service_exceeds_budget():
    ratios = {900: 2.0, 1200: 1.5, 1500: 1.2}                     # measured service(1800) = 8.86/0.732 = 12.1 ms against a 16.67 ms budget
    df = _misses(lambda lv: {900: 1.0, 1200: 1.0, 1500: 0.0, 1800: 0.0}[lv])
    r = hb2(df, budget_ms=16.67, pred_ratio=ratios)
    assert r["must_be_significant"] == [900, 1200] and r["supported"]


def test_hb2_not_supported_if_a_predicted_miss_level_shows_no_rise():
    ratios = {900: 2.0, 1200: 1.5, 1500: 1.2}
    df = _misses(lambda lv: {900: 1.0, 1200: 0.0, 1500: 0.0, 1800: 0.0}[lv])
    assert not hb2(df, budget_ms=16.67, pred_ratio=ratios)["supported"]


# ---- HC1 -------------------------------------------------------------------------------------------
LEVELS = [600, 750, 900, 1050, 1200, 1350, 1500, 1800, "unlocked"]


def _decode(knee_int4, knee_fp16, blocks=10):
    rows = []
    for b in range(blocks):
        for variant, knee in (("int4", knee_int4), ("fp16", knee_fp16)):
            for lv in LEVELS:
                key = 10_000 if lv == "unlocked" else lv
                kk = knee[b] if hasattr(knee, "__getitem__") and not isinstance(knee, (int, float)) else knee
                rows.append(dict(block=b, variant=variant, graph=True, level=lv, rel_thr=1.0 if key >= kk else 0.5))
    return pd.DataFrame(rows)


def test_hc1_supported_when_int4_knee_is_higher_in_enough_blocks():
    r = hc1(_decode(1500, 1050))
    assert r["status"] == "supported" and r["n_nonzero"] == 10
    assert r["knee_table"].loc[0, "int4"] == 1500 and r["knee_table"].loc[0, "fp16"] == 1050


def test_hc1_inconclusive_with_fewer_than_six_nonzero_differences():
    knee_i = [1500] * 5 + [1200] * 5
    r = hc1(_decode(knee_i, 1200))
    assert r["n_nonzero"] == 5 and r["status"] == "inconclusive"


def test_hc1_not_supported_when_int4_knee_is_not_higher():
    r = hc1(_decode(1050, 1500))
    assert r["status"] == "not supported"


# ---- SA1 label -------------------------------------------------------------------------------------
def _phase(slope, n=400, blocks=10, noise=0.05, seed=2):
    rng = np.random.default_rng(seed)
    phase = rng.uniform(0, 4, n)
    return phase, 0.4 + slope * phase + rng.normal(0, noise, n), rng.integers(0, blocks, n)


@pytest.mark.parametrize("slope,label", [(0.0, "phase-independent"), (-1.0, "waits-out-the-slice"), (-0.5, "mixed")])
def test_sa1_label(slope, label):
    ph, lat, blk = _phase(slope)
    assert sa1_label(ph, lat, blk)["label"] == label
