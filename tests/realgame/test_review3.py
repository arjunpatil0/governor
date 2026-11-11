"""Opus review of afae194: clock-check gate (1), pipe listing without connecting (2), NOISE_OK marker (3), present_modes in analysis (4)."""
import json
import time

import pytest

import rg_synth
from test_amend import ClockProbes, NoiseRunner
from test_review2 import main_args
from tools.realgame import analyze as a
from tools.realgame import clockcheck as cc
from tools.realgame import run as r

LOG = lambda *x: None


# ============================================================ 1. clock_check.json gate
def check_args(tmp_path, *extra):
    return main_args(tmp_path, "--check-clocks", "--run-dir", str(tmp_path / "run"), *extra)


def sweep_args(tmp_path, *extra):
    return main_args(tmp_path, "--run-dir", str(tmp_path / "run"), "--reps", "1", "--drop-igpu", "synthetic", *extra)


def write_check(tmp_path, status="passed", age_s=10.0, **kw):
    run = tmp_path / "run"
    run.mkdir(parents=True, exist_ok=True)
    doc = {"status": status, "timestamp": time.time() - age_s, "helper_present": [], "max_sm_mhz": 2100, "info": {"idle_sm_mhz": [210]}, "thresholds": {"max_sm_mhz_above": 1980}, **kw}
    (run / "clock_check.json").write_text(json.dumps(doc))
    return doc


def run_main(argv, runner=None):
    calls = []
    runner = runner or NoiseRunner()
    code = r.main(argv, probes=ClockProbes(game=True), runner=lambda *x: (calls.append(x), runner(*x))[1])
    return code, calls


def test_check_clocks_writes_passed_file(tmp_path):
    assert r.main(check_args(tmp_path), probes=ClockProbes(game=False)) == 0
    doc = json.loads((tmp_path / "run" / "clock_check.json").read_text())
    assert doc["status"] == "passed" and doc["helper_present"] == []
    assert abs(doc["timestamp"] - time.time()) < 60
    assert doc["max_sm_mhz"] == 2100 and doc["thresholds"]["max_sm_mhz_above"] == cc.PASS_SM_MHZ_ABOVE and "timestamp_iso" in doc
    assert doc["info"]["power_limit_w"] == 95.0 and doc["problems"] == []


def test_check_clocks_writes_refused_file(tmp_path, capsys):
    assert r.main(check_args(tmp_path), probes=ClockProbes(game=False, helper=["pipe"])) == 2
    doc = json.loads((tmp_path / "run" / "clock_check.json").read_text())
    assert doc["status"] == "refused" and doc["helper_present"] == ["pipe"]


def test_check_clocks_refused_overwrites_earlier_passed_file(tmp_path):
    write_check(tmp_path)
    assert r.main(check_args(tmp_path), probes=ClockProbes(game=False, load={"max_sm_mhz": 1500, "load_error": None, "power_limit_max_w": 95.0, "info": {}})) == 2
    assert json.loads((tmp_path / "run" / "clock_check.json").read_text())["status"] == "refused"


def test_sweep_refuses_without_clock_check(tmp_path, capsys):
    code, calls = run_main(sweep_args(tmp_path))
    assert code == 2 and calls == [] and "clock_check.json" in capsys.readouterr().err


def test_sweep_refuses_refused_clock_check(tmp_path, capsys):
    write_check(tmp_path, status="refused")
    code, calls = run_main(sweep_args(tmp_path))
    assert code == 2 and calls == [] and "refused" in capsys.readouterr().err


def test_sweep_refuses_stale_clock_check(tmp_path, capsys):
    write_check(tmp_path, age_s=21600 + 60)
    code, calls = run_main(sweep_args(tmp_path))
    assert code == 2 and calls == [] and "older" in capsys.readouterr().err


def test_max_clock_check_age_is_configurable(tmp_path):
    write_check(tmp_path, age_s=600)
    assert run_main(sweep_args(tmp_path, "--max-clock-check-age-s", "300"))[0] == 2
    assert run_main(sweep_args(tmp_path, "--max-clock-check-age-s", "900"))[0] == 0


def test_sweep_refuses_unreadable_or_timestampless_clock_check(tmp_path):
    (tmp_path / "run").mkdir()
    (tmp_path / "run" / "clock_check.json").write_text("{not json")
    assert run_main(sweep_args(tmp_path))[0] == 2
    (tmp_path / "run" / "clock_check.json").write_text(json.dumps({"status": "passed"}))
    assert run_main(sweep_args(tmp_path))[0] == 2


def test_sweep_proceeds_with_fresh_passed_clock_check_and_copies_it_to_run_meta(tmp_path):
    doc = write_check(tmp_path)
    code, calls = run_main(sweep_args(tmp_path))
    assert code == 0 and calls
    assert json.loads((tmp_path / "run" / "run_meta.json").read_text())["clock_check"] == doc


def test_llm_alone_also_needs_a_clock_check(tmp_path, capsys):
    calls = []
    code = r.main(main_args(tmp_path, "--llm-alone", "--run-dir", str(tmp_path / "run"), "--drop-igpu", "synthetic"), probes=ClockProbes(game=False), runner=lambda *x: calls.append(x))
    assert code == 2 and calls == [] and "clock_check.json" in capsys.readouterr().err


def test_llm_alone_with_fresh_check_proceeds_and_records_meta(tmp_path):
    doc = write_check(tmp_path)
    calls = []
    runner = lambda arm, rep, out, cfg: (calls.append(arm), out.mkdir(parents=True, exist_ok=True), (out / "result.json").write_text("{}"))
    assert r.main(main_args(tmp_path, "--llm-alone", "--run-dir", str(tmp_path / "run"), "--drop-igpu", "synthetic"), probes=ClockProbes(game=False), runner=runner) == 0
    assert calls == ["LLM_ALONE"]
    assert json.loads((tmp_path / "run" / "run_meta.json").read_text())["clock_check"] == doc


def test_dry_run_needs_no_clock_check(tmp_path):
    assert r.main(main_args(tmp_path, "--dry-run", "--igpu-vk-index", "1"), probes=ClockProbes(game=True)) == 0


# ============================================================ 2. pipe detection without connecting
def test_pipe_listed_means_present():
    got = cc.helper_present(list_pipes=lambda: ["foo", "governor_clock"], list_cmdlines=lambda: [])
    assert got and "governor_clock" in got[0]


def test_pipe_not_listed_means_absent():
    assert cc.helper_present(list_pipes=lambda: ["foo", "bar"], list_cmdlines=lambda: []) == []


def test_pipe_listing_error_counts_as_present_and_records_error():
    def boom():
        raise OSError("listing denied")
    got = cc.helper_present(list_pipes=boom, list_cmdlines=lambda: [])
    assert got and "listing denied" in got[0]


def test_process_scan_still_applies_with_pipe_lister():
    got = cc.helper_present(list_pipes=lambda: [], list_cmdlines=lambda: ["python actuators\\clock_helper.py"])
    assert got and "clock_helper" in got[0]


def test_default_lister_lists_the_namespace_and_never_touches_the_pipe_as_a_client(monkeypatch):
    import os
    seen = []

    def fake_listdir(p):
        seen.append(p)
        return ["governor_clock"]

    def no_exists(p):
        raise AssertionError("must not touch the pipe as a client")
    monkeypatch.setattr(os, "listdir", fake_listdir)
    monkeypatch.setattr(os.path, "exists", no_exists)
    assert cc.helper_present(list_cmdlines=lambda: []) != []
    assert seen == ["\\\\.\\pipe\\"]


# ============================================================ 3. NOISE_OK marker
def noise_ok(*args):
    return True, []


def order1():
    return r.make_order(3, 1)


def marker(run, rep=0, attempt=1):
    return run / f"rep{rep}" / f"attempt{attempt}" / "NOISE_OK.json"


def test_passing_noise_check_writes_marker_and_attempt_complete(tmp_path):
    run, order = tmp_path / "run", order1()
    r.run_sweep(None, run, order, NoiseRunner(), seed=3, log=LOG, noise_check=r.rep_noise_from_results)
    assert marker(run).exists()
    assert r.final_attempts(run, order) == {0: 1}


def test_all_results_without_marker_is_not_complete(tmp_path):
    run, order = tmp_path / "run", order1()
    r.run_sweep(None, run, order, NoiseRunner(), seed=3, log=LOG, noise_check=noise_ok)
    marker(run).unlink()
    assert r._attempt_state(run, 0, 1, order[0]) != "complete"
    with pytest.raises(ValueError, match="NOISE_OK"):
        r.final_attempts(run, order)


def test_resume_rechecks_unmarked_attempt_and_writes_marker_on_pass(tmp_path):
    run, order = tmp_path / "run", order1()
    r.run_sweep(None, run, order, NoiseRunner(), seed=3, log=LOG, noise_check=noise_ok)
    marker(run).unlink()
    checks, runner = [], NoiseRunner()
    r.run_sweep(None, run, order, runner, seed=3, log=LOG, noise_check=lambda *x: (checks.append(x), (True, []))[1])
    assert len(checks) == 1 and runner.calls == [] and marker(run).exists()
    assert r.final_attempts(run, order) == {0: 1}


def test_resume_recheck_failure_is_a_noise_failure_and_reruns(tmp_path):
    run, order = tmp_path / "run", order1()
    r.run_sweep(None, run, order, NoiseRunner(), seed=3, log=LOG, noise_check=noise_ok)
    marker(run).unlink()
    runner = NoiseRunner()
    r.run_sweep(None, run, order, runner, seed=3, log=LOG, noise_check=lambda run_dir, rep, attempt, o: (False, ["p99 drift"]) if attempt == 1 else (True, []))
    last = run / "rep0" / "attempt1" / f"{len(order[0]) - 1}_SOLO" / "FAILED.json"
    assert json.loads(last.read_text())["reason"] == "noise" and not marker(run).exists()
    assert r.noise_failed_reps(run) == {0}
    assert marker(run, 0, 2).exists() and len(runner.calls) == len(order[0])
    assert r.final_attempts(run, order) == {0: 2}


def test_resume_recheck_failure_beyond_limit_stops_sweep(tmp_path):
    run, order = tmp_path / "run", r.make_order(3, 4)
    r.run_sweep(None, run, order, NoiseRunner(), seed=3, log=LOG, noise_check=noise_ok)
    for rep in range(3):
        marker(run, rep).unlink()
    with pytest.raises(r.NoiseStop):
        r.run_sweep(None, run, order, NoiseRunner(), seed=3, log=LOG, noise_check=lambda run_dir, rep, attempt, o: (False, ["noisy"]) if attempt == 1 else (True, []))


def test_noise_check_exception_propagates_without_marker(tmp_path):
    run, order = tmp_path / "run", order1()

    def boom(*a):
        raise RuntimeError("noise check crashed")
    with pytest.raises(RuntimeError, match="crashed"):
        r.run_sweep(None, run, order, NoiseRunner(), seed=3, log=LOG, noise_check=boom)
    assert not marker(run).exists()
    assert r._attempt_state(run, 0, 1, order[0]) != "complete"
    with pytest.raises(RuntimeError, match="crashed"):                 # and again on resume: re-checked, still raises
        r.run_sweep(None, run, order, NoiseRunner(), seed=3, log=LOG, noise_check=boom)
    assert not marker(run).exists()


def test_interrupt_in_noise_check_then_resume_checks_without_rerunning(tmp_path):
    run, order = tmp_path / "run", order1()

    def interrupt(*a):
        raise KeyboardInterrupt
    with pytest.raises(KeyboardInterrupt):
        r.run_sweep(None, run, order, NoiseRunner(), seed=3, log=LOG, noise_check=interrupt)
    runner = NoiseRunner()
    r.run_sweep(None, run, order, runner, seed=3, log=LOG, noise_check=noise_ok)
    assert runner.calls == [] and marker(run).exists()


def test_failed_attempt_is_not_rechecked_on_resume(tmp_path):
    run, order = tmp_path / "run", order1()
    r.run_sweep(None, run, order, NoiseRunner(bad={(0, 1)}), seed=3, log=LOG, noise_check=r.rep_noise_from_results)
    checks = []
    r.run_sweep(None, run, order, NoiseRunner(), seed=3, log=LOG, noise_check=lambda *x: (checks.append(x), (True, []))[1])
    assert checks == [] and r.final_attempts(run, order) == {0: 2}


def test_analyze_refuses_attempt_without_marker(tmp_path):
    root = tmp_path / "run"
    rg_synth.build_tree(root)
    next(root.glob("rep1/attempt1/NOISE_OK.json")).unlink()
    with pytest.raises(ValueError, match="NOISE_OK"):
        a.analyze(root)


# ============================================================ 4. present_modes in the analysis
def test_cell_summary_has_present_modes(tmp_path):
    root = tmp_path / "run"
    rg_synth.build_tree(root)
    assert a.cell_summary(r.cell_dir(root, 1, 1, 0, "SOLO"))["present_modes"] == ["Flip"]
    assert a.cell_summary(r.llm_alone_dir(root))["present_modes"] is None


def test_summary_md_prints_present_modes_per_arm(tmp_path):
    root = tmp_path / "run"
    rg_synth.build_tree(root)
    a.run_analysis(root, tmp_path / "out", plots=False)
    md = (tmp_path / "out" / "summary.md").read_text()
    assert "Present modes" in md and "UNGATED: Flip" in md and "SOLO: Flip" in md
