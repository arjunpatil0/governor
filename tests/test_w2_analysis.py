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


# ---- glue: results.csv rows -> inputs of the decision functions
import json

from w2_analysis import a_cells, b_service_tables, c_rel_thr


def _row(block, cell_id, **kw):
    spec = kw.pop("spec", {})
    return dict(block=block, cell_id=cell_id, spec=json.dumps(spec), **kw)


def test_a_cells_subtracts_the_blocks_own_baseline_and_keeps_only_main_grid_cells():
    bgspec = lambda m, c, duty=1.0: dict(bg=dict(kind="fma", m_ms=m, cv=c, duty=duty), fg=dict(priority="normal"))
    df = pd.DataFrame([
        _row(0, "baseline", spec=dict(bg=None, fg=dict(priority="normal")), lat_mean_ms=0.2, predicted_wait_ms=float("nan")),
        _row(0, "bg_fma_m2_c0.0", spec=bgspec(2, 0.0), lat_mean_ms=1.2, predicted_wait_ms=1.0),
        _row(1, "baseline", spec=dict(bg=None, fg=dict(priority="normal")), lat_mean_ms=0.3, predicted_wait_ms=float("nan")),
        _row(1, "bg_fma_m2_c0.0", spec=bgspec(2, 0.0), lat_mean_ms=1.1, predicted_wait_ms=1.0),
        _row(0, "sa3_high_m2_c0.0", spec=dict(bg=dict(kind="fma", m_ms=2, cv=0.0, duty=1.0), fg=dict(priority="high")), lat_mean_ms=0.5, predicted_wait_ms=1.0),
    ])
    out = a_cells(df)
    assert {"block", "cell_id", "m_ms", "cv", "obs_ms", "pred_ms"} <= set(out.columns)
    assert len(out) == 2 and set(out.cell_id) == {"bg_fma_m2_c0.0"}
    assert out.sort_values("block").obs_ms.tolist() == pytest.approx([1.0, 0.8])


def test_b_service_tables_split_background_and_drop_unlocked_for_hb1():
    spec = lambda bg: dict(fg=dict(frame="fma_60hz", kind="fma"), bg=bg)
    df = pd.DataFrame([
        _row(0, "fma_60hz_nobg_1800", sm_mhz=1800, spec=spec(None), fg_gpu_p50_ms=12.1, miss_frac=0.0),
        _row(0, "fma_60hz_nobg_unlocked", sm_mhz="unlocked", spec=spec(None), fg_gpu_p50_ms=8.9, miss_frac=0.0),
        _row(0, "fma_60hz_membg_1800", sm_mhz=1800, spec=spec(dict(kind="mem")), fg_gpu_p50_ms=15.0, miss_frac=0.4),
    ])
    t = b_service_tables(df)
    assert set(t["hb1"].columns) >= {"block", "frame", "kind", "level", "service_ms"}
    assert len(t["hb1"]) == 1 and t["hb1"].iloc[0].level == 1800          # background off, locked levels only
    assert len(t["hb2_nobg"]) == 1 and len(t["hb2_membg"]) == 1


def test_c_rel_thr_is_relative_to_the_blocks_unlocked_cell_of_the_same_config():
    spec = lambda v, g: dict(decode=dict(variant=v, graph=g))
    df = pd.DataFrame([
        _row(0, "int4_graph_1200", sm_mhz=1200, spec=spec("int4", True), tok_s=90.0),
        _row(0, "int4_graph_unlocked", sm_mhz="unlocked", spec=spec("int4", True), tok_s=100.0),
        _row(0, "fp16_graph_1200", sm_mhz=1200, spec=spec("fp16", True), tok_s=40.0),
        _row(0, "fp16_graph_unlocked", sm_mhz="unlocked", spec=spec("fp16", True), tok_s=80.0),
    ])
    df["energy_j"], df["tokens"] = 400.0, 360                         # every real C row has these columns
    out = c_rel_thr(df).set_index(["variant", "level"]).rel_thr
    assert out[("int4", 1200)] == pytest.approx(0.9) and out[("fp16", 1200)] == pytest.approx(0.5) and out[("int4", "unlocked")] == pytest.approx(1.0)


def test_rel_w1_is_parsed_from_the_committed_w1_results_file():
    from w2_analysis import load_rel_w1
    rel = load_rel_w1()
    assert rel["fma"][1200] == pytest.approx(0.488) and rel["fma"][1800] == pytest.approx(0.732)
    assert rel["mem"][900] == pytest.approx(0.889) and rel["mem"][1500] == pytest.approx(0.997)


# ---- B report labelling (review 2026-10-21_w2_B_review findings 1, 4, 6) -------------------------------------
def _b_df(ref_miss):
    rows = []
    for b in range(10):
        for lv in (900, 1200, 1500, 1800):
            rows.append(dict(block=b, level=lv, miss_frac=ref_miss if lv == 1800 else 1.0, service_ms=10.0))
    return pd.DataFrame(rows)


def test_hb2_flags_reference_at_ceiling():
    assert hb2(_b_df(1.0), 16.7, {900: 2.0})["reference_at_ceiling"] is True
    assert hb2(_b_df(0.0), 16.7, {900: 2.0})["reference_at_ceiling"] is False


def test_b_per_cell_shows_completed_fraction_next_to_percentiles():
    from w2_analysis import b_per_cell
    df = pd.DataFrame(dict(cell_id=["x"] * 3, frac_completed=[0.2, 0.4, 0.3], lat_p50_ms=[1., 2., 3.], lat_p99_ms=[2., 3., 4.],
                           fg_gpu_p50_ms=[1., 1., 1.], miss_frac=[1., 1., 1.], power_counter_w=[5., 5., 5.], sm_clock_med=[900.] * 3))
    t = b_per_cell(df)
    assert list(t.columns[:2]) == ["cell_id", "frac_completed"] and t.frac_completed.iloc[0] == pytest.approx(0.3)


def test_deadline_aware_picks_lowest_power_level_with_zero_misses():
    from w2_analysis import deadline_aware
    df = pd.DataFrame([dict(cell_id=f"f_nobg_{lv}", miss_frac=m, power_counter_w=w, lat_p99_ms=p)
                       for lv, m, w, p in [("unlocked", 0, 56., 9.), (1800, 0, 38., 12.), (1500, 0, 32., 15.), (1200, 1, 26., 600.)]])
    t = deadline_aware(df, "f_nobg")
    assert t.attrs["best_level"] == "1500" and t.set_index("level").power_saved_vs_unlocked["1500"] == pytest.approx(1 - 32 / 56)
