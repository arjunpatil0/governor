"""W5b evaluation runner (experiments/w5b/eval_lib.py, evaluate.py, freeze.py; plan addendum O-6 section 5, O-5): block composition, seeded order, scene time origin, session limit, frozen constants,
partial-block handling, results table compatible with analysis/w5_analysis.py, sampled power source only.
Instruction (Arjun, 2026-10-24): "build the evaluation runner (sampled source, O-5)"."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "experiments" / "w5b")); sys.path.insert(0, str(ROOT / "experiments" / "w5a"))
import eval_lib as el  # noqa: E402
import evaluate  # noqa: E402
import executors as ex  # noqa: E402
import freeze  # noqa: E402
from sim.params import load_params  # noqa: E402

P = load_params()
G60 = dict(sid="1800_a_g0_d1", clock=1800, mode="aligned", guard_ms=0.0, duty=1.0)
G35 = dict(sid="1500_a_g0_d1", clock=1500, mode="aligned", guard_ms=0.0, duty=1.0)
CONST = dict(c0=7, g_b={"60": G60, "35": G35}, c_b=dict(target=0.35, ki=0.15, guard0=0.5, gmin=0.3), d_b=dict(margin=0.3), power_source="sampled")


def test_a_primary_block_has_25_cells_and_blocks_4_to_8_add_the_20_cell_35_w_family():
    b9 = el.block_cells(9, CONST)
    assert len(b9) == 25 and len({c["id"] for c in b9}) == 25 and all(c["budget_w"] == 60.0 and not c["exploratory"] for c in b9)
    assert sorted(c["scene"] for c in b9 if c["controller"] == "a") == ["S0", "S1", "S1d", "S2", "S5"]
    b4 = el.block_cells(4, CONST)
    exp = [c for c in b4 if c["exploratory"]]
    assert len(b4) == 45 and len(exp) == 20 and all(c["budget_w"] == 35.0 and c["controller"] != "a" for c in exp)
    assert {(c["scene"], c["controller"]) for c in exp} == {(s, k) for s in el.SCENES for k in ("g'B", "eB", "c'B", "d'B")}


def test_cell_specs_carry_workload_setting_constants_and_the_scene_time_origin():
    cells = {c["id"]: c for c in el.block_cells(4, CONST)}
    s5 = [c for c in cells.values() if c["scene"] == "S5"]
    assert all(c["workload"] == "llama31_8b" for c in s5) and all(c["workload"] == "llama32_3b" for c in cells.values() if c["scene"] != "S5")
    g60 = next(c for c in cells.values() if c["controller"] == "g'B" and c["budget_w"] == 60.0 and c["scene"] == "S0")
    g35 = next(c for c in cells.values() if c["controller"] == "g'B" and c["budget_w"] == 35.0 and c["scene"] == "S0")
    e60 = next(c for c in cells.values() if c["controller"] == "eB" and c["budget_w"] == 60.0 and c["scene"] == "S2")
    assert g60["kind"] == "static" and g60["setting"] == G60 and g35["setting"] == G35 and e60["kind"] == "eB" and e60["setting"] == G60
    cb = next(c for c in cells.values() if c["controller"] == "c'B")
    db = next(c for c in cells.values() if c["controller"] == "d'B")
    assert cb["kind"] == "cB" and cb["params"] == dict(target=0.35, ki=0.15) and db["kind"] == "dB" and db["params"] == dict(margin=0.3)
    assert all(c["c0"] == 7 and c["origin_ms"] == 5000.0 for c in cells.values())
    assert next(c for c in cells.values() if c["controller"] == "a")["kind"] == "arm_a"


def test_the_order_is_seeded_per_block_and_differs_between_blocks():
    a = [c["id"] for c in el.block_cells(5, CONST)]
    assert a == [c["id"] for c in el.block_cells(5, CONST)]
    b = [c["id"] for c in el.block_cells(6, CONST)]
    assert [x.split("_", 1)[1] for x in a] != [x.split("_", 1)[1] for x in b] and sorted(x.split("_", 1)[1] for x in a) == sorted(x.split("_", 1)[1] for x in b)


def test_a_missing_35_w_g_b_drops_only_those_exploratory_cells_and_d_b_hgb_is_not_built():
    const = dict(CONST, g_b={"60": G60, "35": None})
    b4 = el.block_cells(4, const)
    assert len(b4) == 45 - 10 and not any(c["controller"] in ("g'B", "eB") and c["budget_w"] == 35.0 for c in b4)
    with pytest.raises(NotImplementedError):
        el.block_cells(4, CONST, hgb=True)


def test_a_session_is_limited_to_three_hours_at_100_s_per_cell_and_only_evaluation_blocks_are_accepted():
    assert el.session_estimate_s([4, 5], CONST) == 90 * 100.0 and el.check_session([4, 5], CONST) is None
    assert "3 h" in el.check_session([4, 5, 6], CONST) and el.check_session([9, 10, 11, 12], CONST) is None and el.check_session([9, 10, 11, 12, 13], CONST) is not None
    assert "evaluation blocks" in el.check_session([3], CONST) and "evaluation blocks" in el.check_session([14], CONST, allow_rerun_numbers=False)


def test_scene_time_starts_at_the_measured_window_so_the_warm_up_runs_at_the_scene_origin():
    s2 = ex.fg_spec("S2", 7.0, origin_ms=5000.0)
    assert s2.active(1000.0) and s2.active(5000.0 + 19000.0) and not s2.active(5000.0 + 25000.0) and s2.active(5000.0 + 35000.0) and not s2.active(5000.0 + 55000.0)
    s1d = ex.fg_spec("S1d", 7.0, origin_ms=5000.0)
    assert abs(s1d.cost_ms(0.0) - 7.0 * 0.7) < 1e-9 and abs(s1d.cost_ms(5000.0 + 30000.0) - 7.0 * 1.0) < 1e-9 and abs(s1d.cost_ms(5000.0 + 60000.0) - 7.0 * 1.3) < 1e-9
    s1 = ex.fg_spec("S1", 7.0, origin_ms=5000.0)
    assert abs(s1.cost_ms(5000.0 + 5000.0) - 7.0) < 1e-9 and abs(s1.cost_ms(5000.0 + 15000.0) - 7.0 * 0.7) < 1e-9 and abs(s1.cost_ms(2000.0) - 7.0) < 1e-9
    assert abs(ex.fg_spec("S1", 7.0).cost_ms(5000.0) - 7.0) < 1e-9 and abs(ex.fg_spec("S1", 7.0).cost_ms(15000.0) - 7.0 * 0.7) < 1e-9          # origin 0 = the tuning behaviour, unchanged


def test_eb_is_the_g_b_action_with_the_idle_drop_to_the_knee():
    k, c = ex.build_controller(P, dict(kind="eB", setting=G60, budget_w=60.0))
    assert k == "ctl" and type(c).__name__ == "IdleDropController" and c.a.clock == 1800.0 and c.a.pacing == "aligned"


def test_constants_are_frozen_from_the_decisions_and_the_runner_refuses_a_wrong_hash(tmp_path):
    t = tmp_path / "tuning.json"; t.write_text(json.dumps(dict(c0=7, g_b={"60": dict(setting=G60, feasible_cells=3), "35": dict(setting=G35, feasible_cells=1)})))
    b = tmp_path / "t3b.json"; b.write_text(json.dumps(dict(d_b=dict(margin=0.3, rule_met=True))))
    c = tmp_path / "t3c.json"; c.write_text(json.dumps(dict(c_b=dict(params=dict(target=0.35, ki=0.15, guard0=0.5, gmin=0.3), rule_met=False, at_grid_edge=False))))
    out = tmp_path / "constants.json"
    const = freeze.build_constants(t, b, c, out)
    assert const["c0"] == 7 and const["g_b"]["60"] == G60 and const["g_b"]["35"] == G35 and const["d_b"]["margin"] == 0.3 and const["c_b"]["target"] == 0.35
    assert len(const["sources"]) == 3 and all(k.endswith("/" + n) for k, n in zip(sorted(const["sources"]), ("t3b.json", "t3c.json", "tuning.json")))
    assert const["power_source"] == "sampled" and const["rules"]["c_b_rule_met"] is False and json.loads(out.read_text())["c0"] == 7
    sha = freeze.sha256_file(out)
    assert evaluate.load_constants(out, sha)["c0"] == 7
    with pytest.raises(SystemExit):
        evaluate.load_constants(out, "0" * 64)


def test_the_hardware_evaluation_executor_is_built_with_the_sampled_power_source_only():
    src = (ROOT / "experiments" / "w5b" / "evaluate.py").read_text(encoding="utf-8")
    assert 'HwExecutor(power_source="sampled")' in src and '"energy"' not in src


def test_an_incomplete_block_is_discarded_whole_and_the_block_number_is_not_reused(tmp_path):
    (tmp_path / "block04" / "cells" / "x").mkdir(parents=True)
    (tmp_path / "block04" / "cells" / "x" / "cell.json").write_text("{}")
    msg = evaluate.prepare_block(tmp_path, 4, 4)
    assert msg and "discarded" in msg and not (tmp_path / "block04").exists() and any((tmp_path / "discarded").iterdir())
    assert evaluate.prepare_block(tmp_path, 4, 14) is None                                       # rerun under the next block number with block 4's seed list: allowed
    (tmp_path / "block05").mkdir(); (tmp_path / "block05" / "block.json").write_text("{}")
    assert "already complete" in evaluate.prepare_block(tmp_path, 5, 5)


def test_a_simulated_block_runs_end_to_end_and_the_results_table_feeds_the_registered_analysis(tmp_path):
    import pandas as pd
    from analysis.w5_analysis import hw1_table
    s = evaluate.run_blocks(tmp_path, [4], CONST, ex.SimExecutor(), log=lambda *a: None)
    assert s["blocks_done"] == [4] and (tmp_path / "block04" / "block.json").exists()
    df = pd.read_csv(tmp_path / "results.csv")
    assert list(df.columns[:7]) == ["block", "scene", "controller", "budget_w", "bg_tok_s", "miss_frac", "power_w"] and len(df) == 45
    t = hw1_table(df, 60.0)
    assert set(t.index.get_level_values(0)) >= set(el.SCENES) and "d'B" in set(t.index.get_level_values(1))


def test_the_supervised_trial_runs_six_cells_one_per_new_hardware_path_outside_any_block(tmp_path):
    cells = evaluate.trial_cells(CONST)
    assert len(cells) == 6 and {(c["scene"], c["controller"], c["budget_w"]) for c in cells} == {("S5", "d'B", 60.0), ("S2", "eB", 60.0), ("S1d", "c'B", 60.0), ("S0", "g'B", 60.0), ("S5", "a", 60.0), ("S1", "d'B", 35.0)}
    assert any(c["workload"] == "llama31_8b" for c in cells)
    s = evaluate.run_trial(tmp_path, CONST, ex.SimExecutor(), log=lambda *a: None)
    assert s["cells"] == 6 and not list(tmp_path.glob("block*/block.json")) and (tmp_path / "trial" / "cells").exists()
