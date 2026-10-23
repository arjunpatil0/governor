"""Grey-box cell-level predictor G (analysis/w5a_greybox.py) of the W5a model-selection protocol (docs/W5A_MODEL_SELECTION_PROTOCOL.md section 4, plan addendum L) and its design-based
adaptation rule (section 3). Analytic steady state of the plant of sim/plant.py: no simulation loop, vectorised, deterministic.
Instruction (Arjun, 2026-10-23): "write the grey-box cell-level predict function test-first, run the selection exactly as registered"."""
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "analysis"))
from sim.params import load_params  # noqa: E402
from w5a_greybox import Calib, calibrate, cell_inputs, grid70, predict, select_adaptation  # noqa: E402

P = load_params()
PERIOD = 1000.0 / 60.0


def row(f=1800, aligned=False, guard=0.5, duty=1.0, c=5.0, varying=False):
    return dict(f=np.array([float(f)]), aligned=np.array([aligned]), guard=np.array([guard]), duty=np.array([duty]), c=np.array([c]), varying=np.array([varying]))


def test_aligned_light_frame_admits_one_token_per_frame_and_never_misses():
    r = predict(P, Calib.prior(P), row(aligned=True, duty=1.0, c=5.0))
    assert r["miss"][0] == 0.0 and abs(r["tok_s"][0] - 60.0) < 1e-9                              # F = 0.745 * 5 = 3.7 ms leaves 12.9 ms; one 10.06 ms token; cap 60 per second
    assert abs(r["p99"][0] - 0.745 * 5.0) < 1e-9 and not r["overload"][0]


def test_aligned_heavy_frame_leaves_no_slack_and_an_overloaded_frame_misses_everything():
    heavy = predict(P, Calib.prior(P), row(aligned=True, c=14.0))
    assert heavy["tok_s"][0] == 0.0 and heavy["miss"][0] == 0.0                                   # F = 10.4 ms, slack 6.2 ms < 10.06 ms token
    over = predict(P, Calib.prior(P), row(f=900, aligned=True, c=14.0))                          # F = 20.9 ms > 16.67 ms
    assert over["miss"][0] == 1.0 and over["overload"][0] and np.isnan(over["p99"][0])


def test_aligned_duty_throttles_the_rate():
    full = predict(P, Calib.prior(P), row(aligned=True, c=5.0, duty=1.0))["tok_s"][0]
    quarter = predict(P, Calib.prior(P), row(aligned=True, c=5.0, duty=0.25))["tok_s"][0]
    assert quarter <= 1000.0 * 0.25 / (1000.0 / P.tok_s(1800.0)) + 1e-9 and quarter < full


def test_unaligned_full_duty_shares_the_gpu_and_dilates_the_token():
    r = predict(P, Calib.prior(P), row(aligned=False, duty=1.0, c=5.0))
    tau = 1000.0 / P.tok_s(1800.0)
    assert r["tok_s"][0] < 1000.0 / tau and r["tok_s"][0] > 1000.0 / (tau * P.share_divisor)    # between the full overlap and the clean rate
    assert r["miss"][0] == 0.0                                                                    # F*S = 9.3 ms still fits
    assert r["p99"][0] > 0.745 * 5.0                                                              # beta > 1%: a frame can be dilated


def test_unaligned_heavy_frame_with_a_busy_background_overloads():
    r = predict(P, Calib.prior(P), row(aligned=False, duty=1.0, c=11.0))                         # F_eff = 8.2 * 2.5 = 20 ms
    assert r["overload"][0] and r["miss"][0] == 1.0


def test_power_is_idle_plus_time_weighted_parts_and_rises_with_the_clock():
    lo = predict(P, Calib.prior(P), row(f=900, aligned=True, c=5.0))["power_w"][0]
    hi = predict(P, Calib.prior(P), row(f=1800, aligned=True, c=5.0))["power_w"][0]
    assert P.p_idle_w < lo < hi < 100.0


def test_varying_condition_averages_phases_and_takes_the_worst_p99():
    r = predict(P, Calib.prior(P), row(aligned=True, c=9.0, varying=True))
    phases = [predict(P, Calib.prior(P), row(aligned=True, c=9.0 * m)) for m in (1.0, 0.7, 1.3, 0.7, 1.0, 1.3)]
    assert abs(r["tok_s"][0] - np.mean([p["tok_s"][0] for p in phases])) < 1e-9
    assert abs(r["p99"][0] - max(p["p99"][0] for p in phases)) < 1e-9


def test_vectorised_rows_equal_row_by_row():
    f = np.array([900.0, 1200.0, 1800.0, 2460.0]); al = np.array([True, False, True, False])
    X = dict(f=f, aligned=al, guard=np.array([0.0, 0.5, 1.0, 0.5]), duty=np.array([0.5, 1.0, 0.25, 0.1]), c=np.array([5.0, 9.0, 7.0, 11.0]), varying=np.array([False, True, False, False]))
    r = predict(P, Calib.prior(P), X)
    for i in range(4):
        one = predict(P, Calib.prior(P), {k: v[i:i + 1] for k, v in X.items()})
        for k in ("miss", "tok_s", "power_w"):
            assert abs(r[k][i] - one[k][0]) < 1e-9


def cell(f, tok_ms, tok_s, fg_p50, power, aband=0, mode="unaligned", duty=1.0, c="c5"):
    return dict(clock=f, mode=mode, guard_ms=0.5, duty=duty, condition=c, tok_ms_p50=tok_ms, bg_tok_s=tok_s, fg_p50_ms=fg_p50, power_w=power, abandoned=aband, frames=1800 - aband)


def test_calibration_moves_token_time_fg_scale_and_power_towards_the_observations():
    base = predict(P, Calib.prior(P), row(f=1800, aligned=False, duty=1.0, c=5.0))
    slow = [cell(1800, 40.0, 25.0, 6.0, 60.0), cell(1350, 50.0, 20.0, 6.5, 55.0), cell(900, 60.0, 16.0, 7.0, 45.0)]       # a slower workload than the 3B prior, a slower fg, more power
    cal = calibrate(P, slow)
    after = predict(P, cal, row(f=1800, aligned=False, duty=1.0, c=5.0))
    assert after["tok_s"][0] < base["tok_s"][0]                                                   # slower tokens
    assert cal.alpha != Calib.prior(P).alpha
    assert after["power_w"][0] != base["power_w"][0]


def test_calibration_skips_quantities_a_cell_cannot_give():
    cal = calibrate(P, [cell(1800, float("nan"), 0.0, float("nan"), 50.0, aband=1500)])        # no tokens, overloaded: only power can be used
    pri = Calib.prior(P)
    assert cal.alpha == pri.alpha and abs(cal.tok_model.predict(1800.0) - pri.tok_model.predict(1800.0)) < 1e-12 and cal.delta != 0.0


def test_empty_adaptation_gives_the_prior():
    cal = calibrate(P, [])
    assert cal.alpha == Calib.prior(P).alpha and cal.delta == 0.0


# ---------------------------------------------------------------- design-based adaptation cells (protocol section 3)
def c(cid, session, order, mode, duty, clock):
    return dict(cell_id=cid, session=session, order=order, mode=mode, duty=duty, clock=clock, workload="w")


def test_adaptation_picks_unaligned_duty_half_or_more_at_distinct_clocks_in_list_order():
    cells = [c("a", 1, 0, "aligned", 1.0, 900), c("b", 1, 1, "unaligned", 0.25, 900), c("d", 1, 2, "unaligned", 0.5, 1200), c("e", 1, 3, "unaligned", 1.0, 1200),
             c("f", 2, 0, "unaligned", 1.0, 1500), c("g", 2, 1, "unaligned", 0.5, 900)]
    assert [x["cell_id"] for x in select_adaptation(cells, 3)] == ["d", "f", "g"]
    assert [x["cell_id"] for x in select_adaptation(cells, 1)] == ["d"]                           # K = 1 is a prefix of K = 3


def test_adaptation_fills_with_the_next_eligible_cells_when_clocks_run_out():
    cells = [c("d", 1, 2, "unaligned", 0.5, 1200), c("e", 1, 3, "unaligned", 1.0, 1200), c("f", 2, 0, "unaligned", 1.0, 1200)]
    assert [x["cell_id"] for x in select_adaptation(cells, 3)] == ["d", "e", "f"]


def test_adaptation_never_looks_at_outcomes():
    cells = [dict(c("d", 1, 2, "unaligned", 0.5, 1200), miss_frac=1.0, bg_tok_s=0.0)]
    assert select_adaptation(cells, 1)[0]["cell_id"] == "d"


def test_cell_inputs_maps_unlocked_and_condition_names():
    X = cell_inputs(P, [dict(clock="unlocked", mode="aligned", guard_ms=1.0, duty=0.5, condition="var9"), dict(clock=900, mode="unaligned", guard_ms=0.5, duty=1.0, condition="c14")])
    assert list(X["f"]) == [P.UNLOCKED_MHZ, 900.0] and list(X["aligned"]) == [True, False] and list(X["c"]) == [9.0, 14.0] and list(X["varying"]) == [True, False]


def test_prediction_for_70_settings_is_fast_enough_for_the_budget():
    X = grid70(9.0)
    cal = Calib.prior(P)
    predict(P, cal, X)
    t = []
    for _ in range(100):
        t0 = time.perf_counter(); predict(P, cal, X); t.append(time.perf_counter() - t0)
    assert len(X["f"]) == 70 and np.percentile(t, 99) < 5e-3                                      # loose unit-test bound; the registered 1 ms test is run in the selection
