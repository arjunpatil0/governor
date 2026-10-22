"""W5a cell list (experiments/w5a/w5a_design.py) against the registration in experiments/w5_governor.yaml (committed 2026-10-23): 18 strata = 3 known workloads x 6 absolute fg conditions
({5, 7, 9, 11, 14} ms nominal + varying on base 9 ms); factors per stratum: 7 clocks x 10 pacing configurations; 280 cells; every stratum x clock pair at least once (126 cells), the rest a
seeded balanced draw; 3 sessions of equal size with the cells randomised across sessions; the held-out workload never appears. Same seed = same list.
Instruction (Arjun, 2026-10-23): "give me the W5a session-1 commands" (the registered W5a list must exist and be frozen first)."""
import sys
from collections import Counter
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "experiments" / "w5a"))
from w5a_design import CLOCKS, CONDITIONS, PACING, build_list, cond_cost_fn  # noqa: E402

WORKLOADS = ("llama32_1b", "llama32_3b", "phi35_mini")


@pytest.fixture(scope="module")
def cells():
    return build_list(WORKLOADS, seed=20261023, n_total=280, n_sessions=3)


def test_registered_factor_levels():
    assert CLOCKS == (900, 1050, 1200, 1350, 1500, 1800, "unlocked")
    assert len(PACING) == 10 and sum(1 for p in PACING if p["mode"] == "aligned") == 6 and sum(1 for p in PACING if p["mode"] == "unaligned") == 4
    assert {(p["guard_ms"], p["duty"]) for p in PACING if p["mode"] == "aligned"} == {(g, d) for g in (0.0, 1.0) for d in (0.25, 0.5, 1.0)}
    assert {p["duty"] for p in PACING if p["mode"] == "unaligned"} == {0.1, 0.25, 0.5, 1.0}
    assert [c["name"] for c in CONDITIONS] == ["c5", "c7", "c9", "c11", "c14", "var9"]


def test_280_cells_18_strata_every_stratum_clock_pair_present(cells):
    assert len(cells) == 280
    assert len({c["cell_id"] for c in cells}) == 280
    strata = Counter((c["workload"], c["condition"]) for c in cells)
    assert len(strata) == 18 and min(strata.values()) >= 7 and max(strata.values()) <= 17
    pairs = {(c["workload"], c["condition"], c["clock"]) for c in cells}
    assert len(pairs) == 18 * 7


def test_no_duplicate_settings_inside_a_stratum_and_marginals_are_balanced(cells):
    keys = [(c["workload"], c["condition"], c["clock"], c["pacing_id"]) for c in cells]
    assert len(set(keys)) == len(keys)
    per_pacing = Counter(c["pacing_id"] for c in cells)
    per_clock = Counter(str(c["clock"]) for c in cells)
    assert max(per_pacing.values()) - min(per_pacing.values()) <= 6 and len(per_pacing) == 10
    assert max(per_clock.values()) - min(per_clock.values()) <= 3 and len(per_clock) == 7


def test_sessions_are_equal_and_every_stratum_is_spread_over_them(cells):
    sess = Counter(c["session"] for c in cells)
    assert sorted(sess) == [1, 2, 3] and max(sess.values()) - min(sess.values()) <= 1
    for stratum in {(c["workload"], c["condition"]) for c in cells}:
        got = {c["session"] for c in cells if (c["workload"], c["condition"]) == stratum}
        assert len(got) >= 2


def test_order_within_a_session_is_a_permutation_and_reproducible(cells):
    again = build_list(WORKLOADS, seed=20261023, n_total=280, n_sessions=3)
    assert [c["cell_id"] for c in cells] == [c["cell_id"] for c in again]
    other = build_list(WORKLOADS, seed=1, n_total=280, n_sessions=3)
    assert [c["cell_id"] for c in cells] != [c["cell_id"] for c in other]
    for s in (1, 2, 3):
        orders = sorted(c["order"] for c in cells if c["session"] == s)
        assert orders == list(range(len(orders)))


def test_the_held_out_workload_never_appears(cells):
    assert all("8b" not in c["workload"] for c in cells)
    with pytest.raises(ValueError):
        build_list(("llama32_1b", "llama32_3b", "llama31_8b"), seed=1)


def test_condition_cost_functions_match_the_registration():
    f = cond_cost_fn("c7")
    assert f(0.0) == 7.0 and f(59000.0) == 7.0
    v = cond_cost_fn("var9")
    steps = [v(t) for t in (0, 10000, 20000, 30000, 40000, 50000)]
    assert steps == pytest.approx([9.0, 6.3, 11.7, 6.3, 9.0, 11.7])


def test_the_yaml_registration_matches_the_generator():
    y = yaml.safe_load((ROOT / "experiments" / "w5_governor.yaml").read_text(encoding="utf-8"))
    design = y["stages"]["W5a_data_collection"]["design"]
    for token in ("{5, 7, 9, 11, 14}", "280 cells", "9 ms", "THREE sessions"):
        assert token in design
