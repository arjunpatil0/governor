"""c'B switches pacing mode INSIDE a cell by a simple non-learned rule (reviewer + Arjun 2026-10-23, fairness: otherwise d'B could win S1/S1d just by switching):
unaligned when the recent measured frame time exceeds 6.57 ms, aligned otherwise, with hysteresis (+-0.3 ms) and a minimum dwell time. The frame-time estimate is the median of the last 30 frame
latencies while aligned (frames run alone) and their 10th percentile while unaligned (the low quantile is the frame alone; contended frames are longer), exactly what PIController already uses.
Instruction: "c'B must also switch mode within a cell, by a simple NON-learned rule ... with hysteresis (e.g. +-0.3 ms) and a minimum dwell time. Otherwise d'B could win S1/S1d just by switching. Test-first."
Synthetic observations; one run on the frozen simulator as a unit harness (not an evaluation)."""
import dataclasses
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from controllers.pi import SwitchingPIController  # noqa: E402
from sim.params import load_params  # noqa: E402
from sim.plant import Obs, Plant, summarise  # noqa: E402
from sim.scenarios import build  # noqa: E402

P = load_params()
PERIOD = 1000.0 / 60.0


def obs(t, lat_ms, clock=1800.0, n=6, power=50.0):
    return Obs(t_ms=float(t), lat_ms=np.full(n, float(lat_ms)), n_missed=0, n_arrived=n, tokens=2, power_w=power, clock_mhz=clock, period_ms=PERIOD, deadline_ms=PERIOD,
               tok_ms=np.array([10.1, 10.1]), overrun_ms=None)


def make():
    c = SwitchingPIController(P, power_budget_w=60.0)
    c.reset(dict(params=P, period_ms=PERIOD, deadline_ms=PERIOD))
    return c


def feed(c, lat, ticks, t0=0):
    a = None
    for i in range(ticks):
        a = c.act(obs(t0 + 100 * i, lat))
    return a


def test_starts_aligned_and_light_frames_keep_it_aligned():
    c = make()
    assert c.mode == "aligned"
    a = feed(c, 4.0, 120)
    assert a.pacing == "aligned" and c.mode == "aligned"


def test_heavy_frames_switch_to_unaligned_after_the_window_fills():
    c = make()
    a = feed(c, 8.5, 120)
    assert c.mode == "unaligned" and a.pacing == "unaligned"


def make_fixed(thr=6.57):
    c = SwitchingPIController(P, power_budget_w=60.0, threshold_ms=thr)            # fixed threshold: the hysteresis band is tested in isolation from the clock-scaled token estimate
    c.reset(dict(params=P, period_ms=PERIOD, deadline_ms=PERIOD))
    return c


def test_hysteresis_keeps_the_mode_inside_the_band():
    c = make_fixed()
    feed(c, 6.7, 200)                                   # between 6.57 and 6.57 + 0.3: stay aligned
    assert c.mode == "aligned"
    c2 = make_fixed()
    feed(c2, 6.95, 120)                                 # above 6.87: switch
    assert c2.mode == "unaligned"
    feed(c2, 6.4, 300, t0=100000)                       # between 6.27 and 6.57: stay unaligned
    assert c2.mode == "unaligned"
    feed(c2, 6.0, 120, t0=200000)                       # below 6.27: back to aligned
    assert c2.mode == "aligned"


def test_minimum_dwell_time_blocks_immediate_switching_back():
    c = make()
    for i in range(200):
        c.act(obs(100 * i, 9.0))
        if c.mode == "unaligned":
            break
    assert c.mode == "unaligned"
    switched_at = c.tick_of_switch
    for i in range(c.dwell_ticks - 2):                  # frames are suddenly light, but the dwell has not elapsed
        c.act(obs(100000 + 100 * i, 4.0))
        assert c.mode == "unaligned", i
    for i in range(c.dwell_ticks + c.window_frames):    # afterwards it comes back
        c.act(obs(200000 + 100 * i, 4.0))
    assert c.mode == "aligned" and c.tick_of_switch > switched_at + c.dwell_ticks - 2


def test_clock_is_carried_over_a_switch_and_actions_stay_in_the_action_space():
    c = make()
    last = None
    for i in range(300):
        a = c.act(obs(100 * i, 8.5 if i < 150 else 4.0))
        assert a.pacing in ("aligned", "unaligned") and 0.0 < a.duty <= 1.0 and a.guard_ms >= 0.0 and 900.0 <= a.clock <= P.UNLOCKED_MHZ
        last = a
    assert c.al.clock == c.un.clock == last.clock


def test_idle_phase_is_handled_and_does_not_switch():
    c = make()
    feed(c, 4.0, 40)
    mode = c.mode
    a = None
    for i in range(10):
        a = c.act(Obs(t_ms=5000.0 + 100 * i, lat_ms=np.empty(0), n_missed=0, n_arrived=0, tokens=3, power_w=30.0, clock_mhz=1800.0, period_ms=PERIOD, deadline_ms=PERIOD, tok_ms=np.array([10.0]), overrun_ms=None))
    assert c.mode == mode and a.duty == 1.0


@pytest.mark.parametrize("cost", [5.0, 10.0])
def test_runs_in_the_simulator_without_error_and_makes_tokens(cost):
    sc = build("S1", duration_ms=40000.0)
    base = sc.fg.cost_ms
    sc = dataclasses.replace(sc, fg=dataclasses.replace(sc.fg, cost_ms=lambda t, b=base, c=cost: b(t) * c / 7.0))
    s = summarise(Plant(P, sc, seed=1).run(SwitchingPIController(P, power_budget_w=60.0)))
    assert s["bg_tok_s"] > 0.5 and s["miss_frac"] <= 0.2


# ---------------------------------------------------------------- token-aware threshold (reviewer 2026-10-24): threshold = period - the CLEAN token duration, same hysteresis and dwell
def clean_at(c, tok_ms, observed_at=1800.0):
    """The clean token duration scaled from the clock it was observed at to the clock c is commanding (token time ~ 1 / tok_s(clock), the L table shape)."""
    return tok_ms * P.tok_s(observed_at) / P.tok_s(P.clamp_clock(c.clock))


def obs_tok(t, lat_ms, tok_ms, n=6, clock=1800.0):
    return Obs(t_ms=float(t), lat_ms=np.full(n, float(lat_ms)) if n else np.empty(0), n_missed=0, n_arrived=n, tokens=2, power_w=50.0, clock_mhz=clock, period_ms=PERIOD, deadline_ms=PERIOD,
               tok_ms=np.array([tok_ms, tok_ms]), overrun_ms=None)


def run_tok(c, lat, tok, ticks, t0=0):
    for i in range(ticks):
        c.act(obs_tok(t0 + 100 * i, lat, tok))


def test_threshold_equals_6_57_ms_for_the_3b_token_and_the_prior_is_used_without_tokens():
    c = make()
    run_tok(c, 4.0, 10.1, 5)
    assert abs(c.threshold() - (PERIOD - clean_at(c, 10.1))) < 1e-6
    c2 = make()
    assert abs(c2.threshold() - (PERIOD - 1000.0 / P.tok_s(P.UNLOCKED_MHZ))) < 1e-6                 # no token seen yet: the L-table prior


def test_a_short_token_workload_keeps_aligned_pacing_at_frames_that_the_fixed_rule_would_reject():
    c = make()
    run_tok(c, 8.5, 4.5, 200)                                  # 1B: token 4.5 ms -> threshold 12.2 ms: an 8.5 ms frame still fits a token
    assert c.mode == "aligned" and abs(c.threshold() - (PERIOD - clean_at(c, 4.5))) < 1e-6


def test_a_long_token_workload_is_unaligned_even_at_light_frames_from_the_startup_tokens():
    c = make()
    for i in range(3):                                         # startup tokens before any frame (the background runs alone): 8B-like 20 ms
        c.act(Obs(t_ms=100.0 * i, lat_ms=np.empty(0), n_missed=0, n_arrived=0, tokens=2, power_w=60.0, clock_mhz=1800.0, period_ms=PERIOD, deadline_ms=PERIOD, tok_ms=np.array([20.0, 20.0]), overrun_ms=None))
    assert c.threshold() <= 0.0
    run_tok(c, 4.0, 20.0, 120, t0=1000)
    assert c.mode == "unaligned"


def test_dilated_tokens_seen_while_unaligned_do_not_move_the_clean_estimate():
    c = make()
    run_tok(c, 4.0, 10.1, 10)
    run_tok(c, 9.0, 10.1, 120, t0=10000)                      # heavy frames: switch to unaligned
    assert c.mode == "unaligned"
    run_tok(c, 9.0, 25.0, 100, t0=30000)                      # unaligned tokens are dilated by overlap
    assert abs(c.threshold() - (PERIOD - clean_at(c, 10.1))) < 1e-6
    run_tok(c, 4.0, 10.1, 200, t0=60000)                      # frames light again (aligned tokens are clean again): the mode returns to aligned and stays there
    assert c.mode == "aligned" and abs(c.threshold() - (PERIOD - clean_at(c, 10.1))) < 1e-6


# ---------------------------------------------------------------- finding 3 (reviewer 2026-10-24): the clean token duration depends on the clock being commanded
def test_a_token_seen_at_1800_mhz_is_longer_at_a_lower_commanded_clock_and_the_threshold_drops():
    c = make()
    run_tok(c, 4.0, 10.1, 10)                                           # tokens observed at 1800 MHz (obs.clock_mhz default)
    c.al.clock = c.un.clock = 900.0                                     # the controller now commands 900 MHz
    t900 = c.clean_token_ms()
    assert abs(t900 - 10.1 * P.tok_s(1800.0) / P.tok_s(900.0)) < 1e-9 and t900 > 10.1
    assert abs(c.threshold() - (PERIOD - t900)) < 1e-9 and c.threshold() < PERIOD - 10.1


def test_tokens_observed_at_different_clocks_are_normalised_before_the_median():
    c = make()
    for i in range(10):
        c.act(obs_tok(100 * i, 4.0, 10.1 * P.tok_s(1800.0) / P.tok_s(1200.0), clock=1200.0))      # the same clean 3B token seen at 1200 MHz
    c.al.clock = c.un.clock = 1800.0
    assert abs(c.clean_token_ms() - 10.1) < 1e-6
