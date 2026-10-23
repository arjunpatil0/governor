"""Hybrid d'B (controllers/hybrid.py): idle branch = the eB rule (clock to the knee with a free background after IDLE_TICKS ticks without frames), active branch = the learned
ModelController (v2+v3, learned guard, power budget). Specified by docs/W45_PLAN.md addendum F and experiments/w5_governor.yaml (d'B).
Instruction (Arjun + reviewer, 2026-10-22): "d'B becomes a hybrid. The idle branch uses the eB rule (clock drop within the budget); the learned model (with the learned guard) handles active play."
Synthetic observations only, no plant and no GPU (the simulator is frozen: the hybrid is deliberately NOT run in it).
Updated 2026-10-23 (plan addendum O-1): the active branch now also owns an unaligned plan; these tests use light frames, where the aligned plan wins and the hybrid equals the aligned model (the
unaligned fallback is tested in tests/test_hybrid_dual.py)."""
from pathlib import Path

import numpy as np
import pytest

from controllers.common import IDLE_TICKS, knee_clock
from controllers.hybrid import HybridController
from controllers.model import ModelController
from controllers.static import IdleDropController
from sim.params import load_params
from sim.plant import Action, Obs

ROOT = Path(__file__).resolve().parents[1]
PERIOD = 1000.0 / 60.0
BUDGET = 60.0


@pytest.fixture(scope="module")
def P():
    return load_params(ROOT)


def ctx(P):
    return dict(params=P, period_ms=PERIOD, deadline_ms=PERIOD)


def active(t, clock=1800.0, power=55.0, overrun=None):
    lat = np.full(6, 4.0)                                              # light frames: the aligned plan admits tokens (7.0 ms leaves too little slack; addendum O-1 then switches to unaligned)
    return Obs(t_ms=float(t), lat_ms=lat, n_missed=0, n_arrived=6, tokens=3, power_w=power, clock_mhz=clock, period_ms=PERIOD, deadline_ms=PERIOD,
               tok_ms=np.array([10.1, 10.2, 10.0]), overrun_ms=None if overrun is None else np.array(overrun, float))


def idle(t, clock=1800.0, power=30.0, overrun=None):
    return Obs(t_ms=float(t), lat_ms=np.empty(0), n_missed=0, n_arrived=0, tokens=6, power_w=power, clock_mhz=clock, period_ms=PERIOD, deadline_ms=PERIOD,
               tok_ms=np.array([10.0] * 3), overrun_ms=None if overrun is None else np.array(overrun, float))


def make(P):
    h = HybridController(P, power_budget_w=BUDGET)
    h.reset(ctx(P))
    return h


def snap(m):
    return dict(pscale=m.pscale, pbias=m.pbias, pdelta=m.pdelta, guard_fb=m.guard_fb, c_hat=m.c_hat, tok_sd=m.tok_sd, tick=m.tick)


def test_name_and_reset_action(P):
    h = HybridController(P, power_budget_w=BUDGET)
    a = h.reset(ctx(P))
    assert h.name == "d'B" and isinstance(a, Action) and a.pacing == "aligned"


def test_active_ticks_are_exactly_the_learned_model(P):
    h, m = make(P), ModelController(P, "aligned", v2=True, v3=True, power_budget_w=BUDGET)
    m.reset(ctx(P))
    for i in range(30):
        o = active(100.0 + 100.0 * i, overrun=[0.5] if i % 7 == 3 else None)
        a_h, a_m = h.act(o), m.act(o)
        if h.mode == "aligned":                                            # while the aligned mode is executed the hybrid IS the aligned learned model
            assert a_h == a_m, i


def test_idle_branch_is_the_eB_rule(P):
    h = make(P)
    for i in range(20):
        h.act(active(100.0 + 100.0 * i))
    a = None
    for i in range(IDLE_TICKS):
        a = h.act(idle(3000.0 + 100.0 * i))
    ref = IdleDropController(P, Action(clock=1800.0, pacing="aligned", duty=0.5, guard_ms=1.0))
    ref.reset()
    for i in range(IDLE_TICKS):
        want = ref.act(idle(3000.0 + 100.0 * i))
    assert (a.clock, a.pacing, a.duty, a.guard_ms) == (float(knee_clock(P)), "aligned", 1.0, 0.0) == (want.clock, want.pacing, want.duty, want.guard_ms)


def test_idle_observations_do_not_touch_the_learned_state(P):
    h = make(P)
    for i in range(20):
        h.act(active(100.0 + 100.0 * i))
    for i in range(IDLE_TICKS):
        h.act(idle(3000.0 + 100.0 * i))
    before = snap(h.model)
    for i in range(20):
        h.act(idle(3600.0 + 100.0 * i, power=30.0, overrun=[3.0]))          # idle-phase power far below the plan and a fake overrun
    assert snap(h.model) == before


def test_resume_returns_the_model_action_and_skips_the_stale_power_calibration(P):
    h = make(P)
    for i in range(20):
        h.act(active(100.0 + 100.0 * i))
    for i in range(IDLE_TICKS + 5):
        h.act(idle(3000.0 + 100.0 * i))
    before = snap(h.model)
    a = h.act(active(5000.0, power=90.0))                                   # a big mismatch against the plan made before the idle phase
    assert not (a.clock == float(knee_clock(P)) and a.duty == 1.0 and a.guard_ms == 0.0)
    after = snap(h.model)
    assert after["pscale"] == before["pscale"] and after["pbias"] == before["pbias"], (before, after)


def test_learned_guard_works_inside_the_hybrid(P):
    g0, g1 = make(P), make(P)
    for i in range(25):
        g0.act(active(100.0 + 100.0 * i))
        a1 = g1.act(active(100.0 + 100.0 * i, overrun=[2.5]))
    g0.act(active(3000.0))
    g1.act(active(3000.0, overrun=[2.5]))
    assert g1.model.guard_fb > g0.model.guard_fb                            # the learned guard lives in the aligned instance (the executed mode may be unaligned on these synthetic observations)
