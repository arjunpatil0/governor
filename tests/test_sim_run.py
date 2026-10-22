"""Simulator study plumbing (sim/run.py, sim/tune.py) and the protocol feasibility gate (docs/W45_SIM_PROTOCOL.md) on the TUNING seeds."""
from pathlib import Path

import numpy as np
import pytest

from controllers.static import tune_static
from sim.params import load_params
from sim.run import EVAL_SEEDS, TUNING_SEEDS, run_matrix

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def P():
    return load_params(ROOT)


def test_seed_sets_are_disjoint_and_sized_as_in_the_protocol():
    assert len(TUNING_SEEDS) == 10 and len(EVAL_SEEDS) == 30 and not set(TUNING_SEEDS) & set(EVAL_SEEDS)


def test_run_matrix_returns_one_row_per_cell(P):
    df = run_matrix(P, ("a", "c'"), ("S0",), (100, 101), {}, workers=2)
    assert len(df) == 4 and {"controller", "scenario", "seed", "miss_frac", "bg_tok_s", "power_w"} <= set(df.columns)
    assert df[df.controller == "c'"].miss_frac.max() <= 0.01


def test_feasibility_gate_no_governor_misses_over_5_percent_in_s1_but_a_static_setting_holds_the_slo(P):
    df = run_matrix(P, ("a",), ("S1",), TUNING_SEEDS[:4], {}, workers=2)
    assert df.miss_frac.mean() > 0.05
    for pacing in ("unaligned", "aligned"):
        r = tune_static(P, "S1", pacing, TUNING_SEEDS[:2])
        assert r["feasible"] and r["miss_max_seen"] <= 0.01 and r["action"].pacing == pacing
