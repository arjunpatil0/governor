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


def test_hysteresis_keeps_the_mode_inside_the_band():
    c = make()
    feed(c, 6.7, 200)                                   # between 6.57 and 6.57 + 0.3: stay aligned
    assert c.mode == "aligned"
    c2 = make()
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
