"""W2 design expansion (experiments/w2_colocation/design.py): cell lists must match the counts registered in w2_colocation.yaml."""
from pathlib import Path

import pytest
import yaml

from design import (build_cells, cell_seed, clock_flags, frame_units_from_pilot, order_block)

ROOT = Path(__file__).resolve().parents[1]
CFG = yaml.safe_load((ROOT / "experiments" / "w2_colocation.yaml").read_text(encoding="utf-8"))


# B has 6 more cells than the yaml's 30: the descriptive 1050 MHz level added by experiments/w2_colocation_addendum_B_levels_2026-10-21.md
@pytest.mark.parametrize("part,key,extra", [("A", "experiment_A", 0), ("B", "experiment_B", 6), ("C", "experiment_C", 0)])
def test_cells_per_block_match_registration(part, key, extra):
    cells = build_cells(CFG, part)
    assert len(cells) == CFG[key]["cells_per_block"] + extra
    assert len({c["cell_id"] for c in cells}) == len(cells)          # ids unique within a block


def test_secondary_cell_count_matches_registration():
    cells = build_cells(CFG, "A2")
    assert len(cells) == 19                                          # 4 (SA3) + 9 (SA4) + 6 (duty sweep), yaml secondary_cells_per_block
    assert len({c["cell_id"] for c in cells}) == len(cells)


def test_A_has_one_baseline_and_full_factorial():
    cells = build_cells(CFG, "A")
    base = [c for c in cells if c["bg"] is None]
    assert len(base) == 1 and base[0]["fg"]["size_ms"] == 0.1
    bg = [c for c in cells if c["bg"]]
    assert {(c["bg"]["m_ms"], c["bg"]["cv"]) for c in bg} == {(m, v) for m in (0.25, 0.5, 1, 2, 4, 8) for v in (0.0, 0.5, 1.0)}
    assert all(c["sm_mhz"] == 1800 and c["mem_mhz"] == 8001 for c in cells)
    assert all(c["fg"]["rate_hz"] == 200 and c["fg"]["n"] == 2000 and c["fg"]["arrivals"] == "poisson" for c in cells)
    assert all(c["bg"]["duty"] == 1.0 and c["bg"]["kind"] == "fma" for c in bg)
    assert all(c["fg"]["priority"] == "normal" for c in cells)


def test_secondary_contains_priority_control_and_duty_sweep():
    cells = build_cells(CFG, "A2")
    high = [c for c in cells if c["fg"]["priority"] == "high"]
    assert len(high) == 4 and all(c["fg"]["size_ms"] == 0.1 for c in high)
    assert {(c["bg"]["m_ms"], c["bg"]["cv"]) for c in high} == {(2, 0.0), (2, 1.0), (8, 0.0), (8, 1.0)}
    duty = [c for c in cells if c["bg"] and c["bg"]["duty"] < 1.0]
    assert sorted((c["fg"]["size_ms"], c["bg"]["duty"]) for c in duty) == sorted((s, d) for s in (4, 9) for d in (0.25, 0.5, 0.75))
    assert sum(1 for c in cells if c["bg"] is None) == 3          # fg-alone baselines for 1, 4 and 9 ms


def test_B_cross_and_units_from_pilot():
    cells = build_cells(CFG, "B")
    assert {c["sm_mhz"] for c in cells} == {900, 1050, 1200, 1500, 1800, "unlocked"}     # 1050 = addendum, descriptive only
    assert {c["fg"]["frame"] for c in cells} == {"fma_60hz", "fma_120hz", "mem_60hz"}
    assert {(c["bg"] or {}).get("kind") for c in cells} == {None, "mem"}
    assert all(c["mem_mhz"] == 8001 and c["fg"]["arrivals"] == "periodic" for c in cells)


def test_C_cross():
    cells = build_cells(CFG, "C")
    assert {c["decode"]["variant"] for c in cells} == {"int4", "fp16"}
    assert {c["decode"]["graph"] for c in cells} == {True, False}
    assert {c["sm_mhz"] for c in cells} == {600, 750, 900, 1050, 1200, 1350, 1500, 1800, "unlocked"}


def test_unknown_part_fails_loudly():
    with pytest.raises(ValueError):
        build_cells(CFG, "Z")


def test_order_is_seeded_complete_and_differs_between_blocks():
    cells = build_cells(CFG, "A")
    o0 = [c["cell_id"] for c in order_block(cells, 20261021, 0)]
    assert sorted(o0) == sorted(c["cell_id"] for c in cells)
    assert o0 == [c["cell_id"] for c in order_block(cells, 20261021, 0)]
    assert o0 != [c["cell_id"] for c in order_block(cells, 20261021, 1)]


def test_cell_seed_is_stable_and_distinct():
    assert cell_seed(20261021, 3, 7) == cell_seed(20261021, 3, 7)
    seeds = {cell_seed(20261021, b, i) for b in range(10) for i in range(40)}
    assert len(seeds) == 400


# ---- clock validity: any sample leaving the target during the window is flagged (decision 1, journal 0012)
def test_clock_flags_clean_window():
    assert clock_flags([1800, 1795, 1805], [8001, 8001], 1800, 8001) == []


def test_clock_flags_any_sample_outside_tolerance():
    assert clock_flags([1800, 1800, 1700], [8001], 1800, 8001) == ["sm_clock_left_target:1700"]
    assert clock_flags([1800], [8001, 405], 1800, 8001) == ["mem_clock_left_target:405"]


def test_clock_flags_unlocked_cell_skips_sm_check():
    assert clock_flags([210, 2400], [8001], None, 8001) == []


def test_clock_flags_empty_samples_is_a_flag():
    assert clock_flags([], [], 1800, 8001) == ["no_clock_samples"]


def test_frame_units_read_from_pilot_file():
    u = frame_units_from_pilot(ROOT / "data" / "pilot" / "w2" / "20261020T222839Z" / "pilot.json")
    assert u == {"fma_60hz": 185633, "fma_120hz": 92586, "mem_60hz": 15803}


def test_1050_is_descriptive_and_outside_the_tested_families():
    from w2_analysis import HB_TEST_LEVELS, interp_service_ratio, load_rel_w1
    assert HB_TEST_LEVELS == (900, 1200, 1500)                          # HB1/HB2 families unchanged by the addendum
    r = interp_service_ratio(load_rel_w1(), "fma", 1050)                # W1 has no 1050 level: linear interpolation 900..1200
    assert r == pytest.approx(0.732 / (0.366 + 0.5 * (0.488 - 0.366)), rel=1e-3)


@pytest.mark.parametrize("part", ["A", "A2", "B", "C"])
def test_frame_units_loaded_for_every_part_whose_cells_use_a_frame(part):
    """Incident (journal 0021): A2 has a 9 ms frame cell but run.py loaded frame units only for B -> TypeError after 3 cells."""
    from design import frame_units_for_part
    pilot = ROOT / "data" / "pilot" / "w2" / "20261020T222839Z" / "pilot.json"
    units = frame_units_for_part(part, build_cells(CFG, part), pilot)
    uses_frame = any(c.get("fg") and c["fg"].get("frame") for c in build_cells(CFG, part))
    if uses_frame:
        for c in build_cells(CFG, part):
            if c.get("fg") and c["fg"].get("frame"):
                assert units[c["fg"]["frame"]] > 0
    else:
        assert units is None
