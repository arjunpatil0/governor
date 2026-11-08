"""The pausable-decode plant (sim/plant_pausable.py, v2 sprint 1): with one group and no overhead it is the original plant, and with groups a token that does not fit the slack as a whole is filled
into the gaps group by group. Simulation only, no GPU.
Instruction (Arjun, 2026-11-08): "Feed the measured group durations and boundary overhead into the existing simulator, replacing 'a token fits or produces nothing' with 'groups fill whatever slack exists'." """
import dataclasses

import numpy as np
import pytest

from sim.params import load_params
from sim.plant import Action, Plant, _Static, summarise
from sim.plant_pausable import PausablePlant
from sim.scenarios import build

P = load_params(".")


def scene(cost_ms=None, name="S0", dur=15000.0):
    sc = build(name, duration_ms=dur)
    if cost_ms is not None:
        sc.fg = dataclasses.replace(sc.fg, cost_ms=lambda t, c=cost_ms: c)
    return sc


def run(cls, sc, mode="aligned", clock=1800.0, **kw):
    return cls(P, sc, seed=1, **kw).run(_Static(Action(clock=clock, pacing=mode, duty=1.0, guard_ms=0.5)))


@pytest.mark.parametrize("mode,clock", [("aligned", 1800.0), ("unaligned", 2460.0)])
def test_one_group_without_overhead_is_the_original_plant(mode, clock):
    a, b = run(Plant, scene(name="S1"), mode, clock), run(PausablePlant, scene(name="S1"), mode, clock)
    assert np.array_equal(a.tok_t_ms, b.tok_t_ms) and np.allclose(np.nan_to_num(a.lat_ms), np.nan_to_num(b.lat_ms)) and a.energy_j == pytest.approx(b.energy_j)


def test_groups_fill_slack_that_a_whole_token_cannot_use():
    sc = lambda: scene(cost_ms=8.0)                                  # an 8 ms frame leaves 8.7 ms: a 10.1 ms token never fits whole
    whole = summarise(run(PausablePlant, sc()))
    four = summarise(run(PausablePlant, sc(), fracs=(0.25,) * 4))
    assert whole["bg_tok_s"] == 0.0
    assert four["bg_tok_s"] > 20.0 and four["miss_frac"] == 0.0     # 4 groups of 2.5 ms fit the gap, and the frames stay on time


def test_boundary_overhead_costs_tokens_but_not_frames():
    sc = lambda: scene(cost_ms=4.0)
    free = summarise(run(PausablePlant, sc(), fracs=(1 / 14,) * 14, boundary_ms=0.0))
    paid = summarise(run(PausablePlant, sc(), fracs=(1 / 14,) * 14, boundary_ms=0.5))
    assert paid["bg_tok_s"] < free["bg_tok_s"] and paid["miss_frac"] == 0.0 and free["miss_frac"] == 0.0
    with pytest.raises(AssertionError):
        PausablePlant(P, sc(), fracs=(0.5, 0.4))                      # fractions must sum to 1
