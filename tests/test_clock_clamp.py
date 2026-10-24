"""Live SM clock readings outside the measured model range must not crash the governor (trial 2026-10-23: the unlocked GPU reads 2475 MHz, the model tables end at W1's unlocked median 2460).
Params.clamp_clock clamps to [lowest measured clock, unlocked] and Governor.step clamps the live clock before it builds the Obs and LOGS every clamp (the clamp is visible, not silent).
Reviewer 2026-10-23 note 1: "clamp clock inputs to the measured range (unlocked = top of the range), log when clamping happens, and add a test with a 2475 reading."""
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from controllers.hybrid import HybridController  # noqa: E402
from controllers.pi import PIController  # noqa: E402
from controllers.runtime import Governor  # noqa: E402
from sim.params import load_params  # noqa: E402
from telemetry.obs_builder import ObsBuilder  # noqa: E402

P = load_params()


class Ring:
    def __init__(self, rows, cols):
        self.rows, self.cols = rows, cols

    def read_new(self):
        r, self.rows = self.rows, np.empty((0, self.cols))
        return r, 0


class Act:
    def __init__(self):
        self.applied = []

    def apply(self, a):
        self.applied.append(a)


def frames(t0, n=6, lat_ms=7.0):
    t = t0 + np.arange(n) / 60.0
    return np.column_stack([t, t, t + lat_ms / 1000.0])


def test_clamp_clock_limits_to_the_measured_range():
    assert P.clamp_clock(2475.0) == P.UNLOCKED_MHZ == 2460.0
    assert P.clamp_clock(210.0) == 600.0 and P.clamp_clock(1500.0) == 1500.0


@pytest.mark.parametrize("raw", [2475.0, 2460.0, 1800.0, 210.0])
@pytest.mark.parametrize("make", [lambda: PIController(P, "aligned", power_budget_w=60.0), lambda: PIController(P, "unaligned"), lambda: HybridController(P, 60.0)])
def test_every_controller_survives_any_live_clock_reading(raw, make):
    ctl, act = make(), Act()
    gov = Governor(ctl, ObsBuilder(1000 / 60, 1000 / 60), act, Ring(np.empty((0, 3)), 3), Ring(np.empty((0, 2)), 2), 1000 / 60, 1000 / 60, params=P)
    gov.start(0.0)
    for k in range(1, 40):
        gov.frames.rows = frames(k * 0.1)
        gov.tokens.rows = np.array([[k * 0.1, 10.0]])
        gov.step(k * 100.0, 5.0 * k, raw)
    assert len(act.applied) == 40
    assert gov.last_obs.clock_mhz == P.clamp_clock(raw)


def test_clamping_is_logged():
    gov = Governor(PIController(P, "unaligned"), ObsBuilder(1000 / 60, 1000 / 60), Act(), Ring(np.empty((0, 3)), 3), Ring(np.empty((0, 2)), 2), 1000 / 60, 1000 / 60, params=P)
    gov.start(0.0)
    gov.step(100.0, 1.0, 1800.0)
    assert gov.clamped == []
    gov.step(200.0, 2.0, 2475.0)
    gov.step(300.0, 3.0, 210.0)
    assert [(c[1], c[2]) for c in gov.clamped] == [(2475.0, 2460.0), (210.0, 600.0)]


def test_a_power_override_replaces_the_energy_derived_power_of_the_obs():
    gov = Governor(PIController(P, "unaligned"), ObsBuilder(1000 / 60, 1000 / 60), Act(), Ring(np.empty((0, 3)), 3), Ring(np.empty((0, 2)), 2), 1000 / 60, 1000 / 60, params=P)
    gov.start(0.0)
    gov.step(100.0, 10.0, 1800.0)
    gov.step(200.0, 14.2, 1800.0)                                       # 4.2 J in 0.1 s = 42 W from the energy counter
    assert abs(gov.last_obs.power_w - 42.0) < 1e-6
    gov.step(300.0, 18.4, 1800.0, power_w=33.0)
    assert gov.last_obs.power_w == 33.0
