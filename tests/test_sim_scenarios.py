"""Scenario builders (sim/scenarios.py) fixed by docs/W45_SIM_PROTOCOL.md, and the plant's interaction option (scenario S4)."""
from pathlib import Path

import numpy as np
import pytest

from sim.params import load_params
from sim.plant import Action, BgSpec, Plant, summarise
from sim.scenarios import C0_MS, SCENARIOS, build

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def P():
    return load_params(ROOT)


def test_protocol_constants():
    assert C0_MS == 7.0 and set(SCENARIOS) == {"S0", "S1", "S1d", "S2", "S3", "S4"}


def test_all_scenarios_are_60s_with_5s_warmup_and_a_60hz_fg_with_the_llama_bg():
    for name in SCENARIOS:
        sc = build(name)
        assert sc.duration_ms == 60000.0 and sc.warmup_ms == 5000.0
        assert sc.fg.arrivals == "periodic" and sc.fg.period_ms == pytest.approx(1000 / 60) and sc.fg.deadline_ms == pytest.approx(1000 / 60)
        assert sc.bg is not None and sc.bg.kind == "llama"


def test_s0_is_steady():
    sc = build("S0")
    assert all(sc.fg.cost_ms(t) == pytest.approx(7.0) for t in (0, 20000, 59999))


def test_s1_steps_pm_30_percent_every_10_s():
    sc = build("S1")
    got = [sc.fg.cost_ms(t) / 7.0 for t in (1000, 11000, 21000, 31000, 41000, 51000)]
    assert got == pytest.approx([1.0, 0.7, 1.3, 0.7, 1.0, 1.3])


def test_s1d_ramps_linearly_from_0p7_to_1p3():
    sc = build("S1d")
    assert sc.fg.cost_ms(0) / 7.0 == pytest.approx(0.7) and sc.fg.cost_ms(30000) / 7.0 == pytest.approx(1.0) and sc.fg.cost_ms(60000) / 7.0 == pytest.approx(1.3)


def test_s2_fg_is_idle_20_to_30_and_50_to_60_s():
    a = build("S2").fg.active
    assert [a(t) for t in (1000, 19999, 20000, 29999, 30000, 49999, 50000, 59999)] == [True, True, False, False, True, True, False, False]


def test_s3_caps_the_clock_at_1500_from_30_s():
    assert build("S3").clock_cap == [(30000.0, 1500.0)]


def test_s4_is_s1_with_interaction_half():
    s1, s4 = build("S1"), build("S4")
    assert s4.interaction == pytest.approx(0.5) and s1.interaction == 0.0 and s4.fg.cost_ms(21000) == s1.fg.cost_ms(21000)


def test_interaction_slows_the_fg_under_contention_at_low_clock_only(P):
    def lat(inter, clk):
        sc = build("S0"); sc.interaction = inter; sc.duration_ms = 15000.0
        return summarise(Plant(P, sc, seed=1).run(Action(clock=clk, pacing="unaligned", duty=1.0)))["lat_mean_ms"]
    assert lat(0.5, 1200) > lat(0.0, 1200) * 1.1
    assert lat(0.5, 1800) == pytest.approx(lat(0.0, 1800), rel=1e-6)


def test_s5_is_s1_with_an_unseen_background_workload_and_is_not_part_of_the_frozen_scenario_set():
    from sim.scenarios import EXTRA_SCENARIOS
    s1, s5 = build("S1"), build("S5")
    assert "S5" in EXTRA_SCENARIOS and "S5" not in SCENARIOS
    assert s5.bg.profile == "fp16" and s1.bg.profile is None and s5.fg.cost_ms(21000) == s1.fg.cost_ms(21000) and s5.interaction == 0.0
