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
    c = tmp_path / "t3c.json"; c.write_text(json.dumps(dict(c_b=dict(params=dict(target=0.35, ki=0.15, guard0=0.5, gmin=0.3), rule_met=True, at_grid_edge=False), headroom=dict(w=2.692), d_b_headroom=dict(rule_holds=True, mean_miss=0.004))))
    out = tmp_path / "constants.json"
    const = freeze.build_constants(t, b, c, out)
    assert const["c0"] == 7 and const["g_b"]["60"] == G60 and const["g_b"]["35"] == G35 and const["d_b"]["margin"] == 0.3 and const["c_b"]["target"] == 0.35
    assert len(const["sources"]) == 3 and all(k.endswith("/" + n) for k, n in zip(sorted(const["sources"]), ("t3b.json", "t3c.json", "tuning.json")))
    assert const["power_source"] == "sampled" and const["rules"]["c_b_rule_met"] is True and const["c_b_selection"] == "registered (rule met)" and json.loads(out.read_text())["c0"] == 7
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


def test_evaluation_cells_of_c_b_and_d_b_carry_the_steering_budget_parameter_from_the_frozen_headroom():
    const = dict(CONST, headroom=dict(w=2.692))
    cells = el.block_cells(4, const)
    cb60 = next(c for c in cells if c["controller"] == "c'B" and c["budget_w"] == 60.0)
    db35 = next(c for c in cells if c["controller"] == "d'B" and c["budget_w"] == 35.0)
    assert abs(cb60["steer_budget_w"] - (60.0 - 2.692) / 0.97) < 1e-9 and abs(db35["steer_budget_w"] - (35.0 - 2.692) / 0.97) < 1e-9
    assert all("steer_budget_w" not in c for c in cells if c["controller"] in ("g'B", "eB", "a"))
    assert all("steer_budget_w" not in c for c in el.block_cells(4, CONST) if c["controller"] in ("c'B", "d'B"))        # constants without a headroom: the plain budget


def test_freeze_carries_the_headroom_and_the_confirmation_and_refuses_a_t3c_without_it(tmp_path):
    t = tmp_path / "tuning.json"; t.write_text(json.dumps(dict(c0=7, g_b={"60": dict(setting=G60, feasible_cells=3), "35": None})))
    b = tmp_path / "t3b.json"; b.write_text(json.dumps(dict(d_b=dict(margin=0.3, rule_met=True))))
    c = tmp_path / "t3c.json"
    c.write_text(json.dumps(dict(c_b=dict(params=dict(target=0.35, ki=0.15, guard0=0.5, gmin=0.3), rule_met=True, at_grid_edge=False), headroom=dict(w=2.692, sensor_p95_w=1.05, spread_p95_w=1.642),
                                 d_b_headroom=dict(rule_holds=False, mean_miss=0.02))))
    const = freeze.build_constants(t, b, c, tmp_path / "constants.json")
    assert const["headroom"]["w"] == 2.692 and const["rules"]["d_b_headroom_rule_holds"] is False and const["g_b"]["35"] is None
    c2 = tmp_path / "t3c_old.json"; c2.write_text(json.dumps(dict(c_b=dict(params=dict(target=0.35, ki=0.15), rule_met=True))))
    with pytest.raises(SystemExit):
        freeze.build_constants(t, b, c2, tmp_path / "x.json")


def test_the_trial_check_is_mechanical(tmp_path):
    def cell(name, **m):
        d = tmp_path / "trial" / "cells" / name
        d.mkdir(parents=True)
        base = dict(miss=0.0, tok_s=20.0, power_w=40.0, power_sampled_w=40.5, gov_reads=0, power_source="sampled", exec_mode="EXEC_MODE cuda offloaded=33/33 n_layer=32 governed=1")
        base.update(m)
        (d / "cell.json").write_text(json.dumps(dict(id=name, spec=dict(id=name, workload="llama31_8b" if "S5" in name else "llama32_3b", kind="dB" if "d" in name else "static"), metrics=base, executor="hw")))
    cell("ev04_S5_dB_60"); cell("ev04_S2_eB_60", gov_reads=0); cell("ev04_S0_gB_60", power_source=None, gov_reads=None)
    ok = evaluate.check_trial(tmp_path)
    assert ok["ok"] is True and ok["problems"] == []
    (tmp_path / "trial" / "cells" / "ev04_S2_eB_60" / "cell.json").unlink()
    cell_bad = tmp_path / "trial" / "cells" / "ev04_S2_eB_60"
    (cell_bad / "cell.json").write_text(json.dumps(dict(id="ev04_S2_eB_60", spec=dict(id="x", workload="llama32_3b", kind="eB"), metrics=dict(miss=0.0, tok_s=1.0, power_w=90.0, power_sampled_w=40.0, gov_reads=300, power_source="energy",
                                                                                                                      exec_mode="EXEC_MODE cuda offloaded=10/33 n_layer=32 governed=1"), executor="hw")))
    bad = evaluate.check_trial(tmp_path)
    p = " | ".join(bad["problems"])
    assert bad["ok"] is False and "read the energy counter" in p and "differ" in p and "offload" in p and "sampled" in p
    assert evaluate.check_trial(tmp_path / "nowhere")["ok"] is False


# ---------------------------------------------------------------- the unattended chain (docs/W5B_T3C_SITTING.md, scripts/w5b_t3c_chain.ps1)
CHAIN = ROOT / "scripts" / "w5b_t3c_chain.ps1"


def test_the_chain_script_parses_orders_the_steps_guards_each_one_and_never_starts_a_block():
    import re
    import shutil
    import subprocess
    src = CHAIN.read_text(encoding="utf-8")
    order = [src.index(k) for k in ("powercfg /change standby-timeout-ac 0", "tune.py --out data/w5b/t3c --plan t3c", "morning.py --out data/w5b/t3c --strict", "freeze.py", "evaluate.py --trial", "evaluate.py --check-trial")]
    assert order == sorted(order)
    for line in src.splitlines():
        if "evaluate.py" in line and not line.lstrip().startswith("#"):
            assert "--trial" in line or "--check-trial" in line, line                      # no evaluation block can be started from here
    assert src.count("Stop-Chain") >= 5 and "$LASTEXITCODE" in src and "NOT started" in src and "--power-source sampled" in src and "Start-Transcript" in src
    assert not re.search(r"evaluate\.py --blocks", src)
    ps = shutil.which("powershell")
    if ps:
        cmd = f"$e = $null; [void][System.Management.Automation.Language.Parser]::ParseFile('{CHAIN}', [ref]$null, [ref]$e); if ($e.Count) {{ $e | ForEach-Object {{ $_.Message }}; exit 1 }}"
        r = subprocess.run([ps, "-NoProfile", "-Command", cmd], capture_output=True, text=True, timeout=60)
        assert r.returncode == 0, r.stdout + r.stderr


def test_the_chain_summary_prints_the_decisions_the_hash_and_the_trial_checks(tmp_path):
    import chain_summary as cs
    (tmp_path / "t3c").mkdir()
    (tmp_path / "t3c" / "decisions.json").write_text(json.dumps(dict(c_b=dict(params=dict(target=0.35, ki=0.15), rule_met=True, at_grid_edge=False, mean_miss=0.008, mean_tok_s=21.0, mean_power_w=41.0),
                                                                    headroom=dict(w=2.692, sensor_p95_w=1.05, spread_p95_w=1.642), d_b_headroom=dict(rule_holds=True, mean_miss=0.006, mean_tok_s=25.0, mean_power_w=57.0, margin=0.3))))
    (tmp_path / "constants.json").write_text(json.dumps(dict(c0=7, g_b={"60": G60, "35": G35}, c_b=dict(target=0.35, ki=0.15), d_b=dict(margin=0.3), headroom=dict(w=2.692), rules={})))
    (tmp_path / "constants.sha256").write_text("ab" * 32)
    lines = cs.summary(tmp_path / "t3c" / "decisions.json", tmp_path / "constants.json", tmp_path / "constants.sha256", tmp_path / "none")
    text = "\n".join(lines)
    assert "target 0.35" in text and "2.69" in text and "rule_holds" in text.replace(" ", "_") or "still holds" in text
    assert "ab" * 32 in text and "trial" in text.lower()
