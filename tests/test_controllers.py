"""Controller unit tests (controllers/*.py) on synthetic observations: none (a), static (b), PI + deadline-aware clock rule (c, c'), model-based (d, d').
Specified by docs/W45_PLAN.md (Phase 2 and the approved modifications) and docs/W45_SIM_PROTOCOL.md. Instruction: "start: simulator -> controllers vs simulator (test-first)"."""
from pathlib import Path

import numpy as np
import pytest

from controllers.common import ALLOWED_CLOCKS, knee_clock
from controllers.model import ModelController
from controllers.none import NoGovernor
from controllers.pi import PIController
from controllers.static import StaticController
from sim.params import load_params
from sim.plant import Action, Obs

ROOT = Path(__file__).resolve().parents[1]
PERIOD = 1000.0 / 60.0


@pytest.fixture(scope="module")
def P():
    return load_params(ROOT)


def ctx(P):
    return dict(params=P, period_ms=PERIOD, deadline_ms=PERIOD)


def obs(t, lat, clock=1800.0, n_arrived=None, n_missed=None):
    lat = np.asarray(lat, float)
    return Obs(t_ms=float(t), lat_ms=lat, n_missed=int((lat > PERIOD).sum()) if n_missed is None else n_missed, n_arrived=len(lat) if n_arrived is None else n_arrived,
               tokens=0, power_w=60.0, clock_mhz=clock, period_ms=PERIOD, deadline_ms=PERIOD)


def run_ticks(c, lat, n, clock=1800.0, t0=100.0, n_arrived=None):
    a = None
    for i in range(n):
        a = c.act(obs(t0 + 100.0 * i, lat, clock=clock, n_arrived=n_arrived))
    return a


# ---------------------------------------------------------------- common
def test_allowed_clocks_and_knee(P):
    assert ALLOWED_CLOCKS(P)[0] == 900 and ALLOWED_CLOCKS(P)[-1] == P.UNLOCKED_MHZ
    assert knee_clock(P) == 1500


# ---------------------------------------------------------------- (a) and (b)
def test_none_is_unlocked_unaligned_full_duty(P):
    c = NoGovernor(P)
    a = c.reset(ctx(P))
    assert a == Action(clock=P.UNLOCKED_MHZ, pacing="unaligned", duty=1.0) and c.act(obs(100, [5.0])) == a


def test_static_returns_its_fixed_action(P):
    fixed = Action(clock=1500, pacing="aligned", guard_ms=1.5)
    c = StaticController(fixed)
    assert c.reset(ctx(P)) == fixed and c.act(obs(100, [20.0])) == fixed


# ---------------------------------------------------------------- (c) PI, unaligned
def test_pi_lowers_duty_when_latency_is_above_target_and_raises_it_when_below(P):
    hi = PIController(P, "unaligned"); d0 = hi.reset(ctx(P)).duty
    assert run_ticks(hi, [15.0] * 6, 3).duty < d0                       # 15 ms > 0.8 x 16.7 ms target, but no miss
    lo = PIController(P, "unaligned"); d0 = lo.reset(ctx(P)).duty
    assert run_ticks(lo, [5.0] * 6, 10).duty > d0


def test_pi_backs_off_hard_on_a_miss_and_clamps_duty(P):
    c = PIController(P, "unaligned"); c.reset(ctx(P))
    run_ticks(c, [5.0] * 6, 15)
    d_before = c.duty
    a = c.act(obs(2000, [5.0] * 5 + [25.0]))
    assert a.duty <= 0.5 * d_before + 1e-9
    for i in range(40):
        a = c.act(obs(2100 + 100 * i, [30.0] * 6))
    assert a.duty == pytest.approx(c.dmin) and 0 < c.dmin < 0.1
    for i in range(400):
        a = c.act(obs(7000 + 100 * i, [2.0] * 6))
    assert a.duty <= 1.0


def test_pi_clock_rule_picks_lowest_clock_whose_predicted_frame_fits_the_margin(P):
    c = PIController(P, "unaligned"); a0 = c.reset(ctx(P))
    a = None
    for i in range(9):
        a = c.act(obs(100 + 100 * i, [7.0] * 6))
    assert a.clock == a0.clock                                          # clock decisions only every 10 ticks
    a = c.act(obs(1000, [7.0] * 6))
    assert a.clock == 1500                                              # 7.0 ms x ratio(1500) = 8.4 ms <= (0.6 - 0.05) x 16.7 ms; 1350 gives 9.3 ms


def test_pi_goes_to_the_knee_clock_with_free_background_when_the_fg_is_idle(P):
    c = PIController(P, "unaligned"); c.reset(ctx(P))
    a = run_ticks(c, [], 12, n_arrived=0)
    assert a.clock == knee_clock(P) and a.duty == 1.0


# ---------------------------------------------------------------- (c') PI, aligned
def test_pi_aligned_guard_grows_after_a_miss_and_stays_bounded(P):
    c = PIController(P, "aligned"); a0 = c.reset(ctx(P))
    assert a0.pacing == "aligned"
    a = c.act(obs(100, [5.0] * 5 + [25.0]))
    assert a.guard_ms > a0.guard_ms
    for i in range(100):
        a = c.act(obs(200 + 100 * i, [30.0] * 6))
    assert 0 <= a.guard_ms <= 8.0


def test_pi_aligned_clock_rule_keeps_one_token_fitting(P):
    light = PIController(P, "aligned"); light.reset(ctx(P))
    assert run_ticks(light, [3.5] * 6, 10).clock == 1350               # 3.5 x ratio + token + guard still fits 16.7 ms at 1350, not at 1200
    mid = PIController(P, "aligned"); mid.reset(ctx(P))
    assert run_ticks(mid, [4.9] * 6, 10).clock == 1800                 # a lower clock would push the token out of the slack


# ---------------------------------------------------------------- (d) model-based
def test_model_estimates_the_fg_cost_at_any_clock(P):
    for clock, lat in ((1800.0, 7.0), (1500.0, 7.0 * P.fg_ratio(1500))):
        m = ModelController(P, "aligned"); m.reset(ctx(P))
        run_ticks(m, [lat] * 6, 30, clock=clock)
        assert m.c_hat == pytest.approx(7.0, rel=0.05)


def test_model_plan_respects_its_own_safety_bound_and_reacts_to_a_heavier_fg(P):
    m = ModelController(P, "unaligned"); m.reset(ctx(P))
    run_ticks(m, [7.0] * 6, 30)
    p1 = dict(m.plan)
    assert p1["pred_q95_ms"] <= m.safety * PERIOD + 1e-9
    run_ticks(m, [14.0] * 6, 30, clock=p1["clock"], t0=5000.0)
    p2 = m.plan
    assert p2["pred_q95_ms"] <= m.safety * PERIOD + 1e-9 and (p2["clock"] > p1["clock"] or p2["duty"] < p1["duty"])


def test_model_learns_that_interference_is_worse_than_its_prior(P):
    m = ModelController(P, "unaligned"); m.reset(ctx(P))
    run_ticks(m, [7.0] * 6, 30)
    d0 = m.plan["duty"]
    for i in range(30):                                                 # observed p95 twice what the prior predicts at the commanded duty
        m.act(obs(5000 + 100 * i, [2.0 * m.plan["pred_q95_ms"]] * 6))
    assert m.plan["duty"] < d0 or m.plan["clock"] > 1500


def test_model_aligned_releases_a_token_when_it_fits_and_not_when_it_cannot(P):
    m = ModelController(P, "aligned"); m.reset(ctx(P))
    run_ticks(m, [4.9] * 6, 30)
    assert m.plan["n_tok"] == 1 and m.plan["guard_ms"] >= 0.3
    h = ModelController(P, "aligned"); h.reset(ctx(P))
    run_ticks(h, [11.0] * 6, 30)
    assert h.plan["n_tok"] == 0 and h.plan["pred_q95_ms"] <= h.safety * PERIOD + 1e-9


def test_model_goes_to_the_knee_clock_when_the_fg_is_idle(P):
    m = ModelController(P, "aligned"); m.reset(ctx(P))
    a = run_ticks(m, [], 12, n_arrived=0)
    assert a.clock == knee_clock(P) and a.pacing == "aligned"


# ---------------------------------------------------------------- follow-ups: scenario-agnostic static, idle-triggered clock drop
def test_idle_drop_controller_runs_a_fixed_aligned_setting_and_drops_to_the_knee_when_idle(P):
    from controllers.static import IdleDropController
    fixed = Action(clock=P.UNLOCKED_MHZ, pacing="aligned", guard_ms=0.0)
    c = IdleDropController(P, fixed)
    assert c.reset(ctx(P)) == fixed and run_ticks(c, [5.0] * 6, 10) == fixed
    a = run_ticks(c, [], 6, n_arrived=0)
    assert a.clock == knee_clock(P) and a.pacing == "aligned"
    assert run_ticks(c, [5.0] * 6, 1) == fixed                          # frames are back: the fixed setting returns at once


def test_global_static_holds_the_slo_in_every_listed_scenario(P):
    from controllers.static import tune_static_global
    r = tune_static_global(P, "aligned", (100,), ("S0", "S1"), duration_ms=15000.0, clocks=(1800.0, P.UNLOCKED_MHZ))
    assert r["feasible"] and r["miss_max_seen"] <= 0.01 and r["action"].pacing == "aligned"
