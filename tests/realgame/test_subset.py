"""Smaller sweep: --arms subset, noise-stop scaling with the number of reps, --check-clocks with the game running."""
import json

import pytest

import rg_synth
from test_amend import ClockProbes, NoiseRunner
from test_cell import FakeProbes, make_cfg
from test_review2 import main_args
from tools.realgame import analyze as a
from tools.realgame import run as r

ARMS3 = ("UNGATED", "PRIO_IDLE", "IGPU")


# ------------------------------------------------------------------ --arms parsing
def test_arms_default_is_all_four():
    assert r._parser().parse_args(["--game-process", "g.exe"]).arms == r.DEFAULT_ARMS


def test_arms_parsed_in_given_order():
    assert r._parser().parse_args(["--game-process", "g.exe", "--arms", "UNGATED,PRIO_IDLE,IGPU"]).arms == ARMS3


@pytest.mark.parametrize("bad", ["UNGATED,BOGUS", "UNGATED,UNGATED", "SOLO,UNGATED", "", "UNGATED,,IGPU"])
def test_arms_rejects_unknown_duplicate_empty(bad, capsys):
    with pytest.raises(SystemExit) as e:
        r._parser().parse_args(["--game-process", "g.exe", "--arms", bad])
    assert e.value.code == 2


def test_dry_run_prints_arms_and_order_from_same_seed(tmp_path, capsys):
    code = r.main(main_args(tmp_path, "--dry-run", "--reps", "3", "--arms", ",".join(ARMS3)), probes=FakeProbes())
    out = capsys.readouterr().out
    assert code == 0 and f"arms {list(ARMS3)}" in out and "DUTY50" not in out
    for rep, o in enumerate(r.make_order(r.DEFAULT_SEED, 3, ARMS3)):
        assert f"rep {rep}: " + " ".join(o) in out


def test_dry_run_without_igpu_needs_no_vk(tmp_path, capsys):
    # IGPU requirements (Vulkan exe) apply only when IGPU is in --arms
    argv = main_args(tmp_path, "--dry-run", "--arms", "UNGATED,PRIO_IDLE", "--llm-exe-vk", str(tmp_path / "missing_vk.exe"))
    assert r.main(argv, probes=FakeProbes()) == 0
    assert "llm_exe_vk" not in capsys.readouterr().out


# ------------------------------------------------------------------ rehearsal
def test_rehearse_runs_only_selected_arms(tmp_path):
    from test_rehearse import BadPm, fake_runner, rehearse_argv
    calls = []
    code = r.main(rehearse_argv(tmp_path, "--arms", "PRIO_IDLE,UNGATED"), probes=BadPm(game=False), runner=fake_runner(calls=calls))
    assert code == 0 and sorted(x[0] for x in calls) == ["PRIO_IDLE", "UNGATED"]
    doc = json.loads((tmp_path / "run" / "rehearsal.json").read_text())
    assert set(doc["arms"]) == {"PRIO_IDLE", "UNGATED"} and "llm_exe_vk" not in doc["exe_sha256"]


def test_sweep_gate_only_needs_selected_arms_and_no_vk_binding(tmp_path):
    from test_rehearse import sweep_main
    doc = dict(arms=("UNGATED", "PRIO_IDLE"), exe_sha256={"llm_exe": "sha-a"})
    code, seen = sweep_main(tmp_path, "--arms", "UNGATED,PRIO_IDLE", rehearsal=doc)
    assert code == 0 and seen


def test_sweep_gate_still_requires_igpu_when_selected(tmp_path, capsys):
    from test_rehearse import sweep_main
    code, seen = sweep_main(tmp_path, "--arms", ",".join(ARMS3), rehearsal=dict(arms=("UNGATED", "PRIO_IDLE")))
    assert code == 2 and seen == [] and "IGPU" in capsys.readouterr().err


def test_sweep_passes_order_for_the_arm_list(tmp_path):
    from test_rehearse import sweep_main
    code, seen = sweep_main(tmp_path, "--arms", ",".join(ARMS3))
    assert code == 0
    assert seen[0][2] == r.make_order(r.DEFAULT_SEED, 1, ARMS3)


def test_run_sweep_records_arms_in_meta(tmp_path):
    order = r.make_order(3, 3, ARMS3)
    r.run_sweep(make_cfg(tmp_path), tmp_path / "run", order, NoiseRunner(), seed=3, log=lambda *a: None)
    assert sorted(json.loads((tmp_path / "run" / "run_meta.json").read_text())["arms"]) == sorted(ARMS3)


# ------------------------------------------------------------------ analyze without DUTY50
def test_analyze_three_reps_without_duty50(tmp_path):
    root, out = tmp_path / "run", tmp_path / "out"
    order = rg_synth.build_tree(root, reps=3, arms=ARMS3)
    assert all("DUTY50" not in o for o in order)
    summ = a.run_analysis(root, out, plots=True)
    assert summ["run_meta"]["arms"] == list(ARMS3)
    assert set(summ["decision"]["arms"]) == {"UNGATED", "PRIO_IDLE", "IGPU"}
    assert summ["decision"]["igpu_tested"] is True and summ["decision"]["branch"]
    assert "DUTY50" not in json.dumps(summ["decision"])
    assert {c["arm"] for c in summ["cells"]} == {"SOLO", *ARMS3}
    md = (out / "summary.md").read_text()
    assert "DUTY50" not in md and "IGPU" in md and "not tested" not in md
    assert (out / "p99_by_arm.png").exists()


# ------------------------------------------------------------------ noise-stop scaling
@pytest.mark.parametrize("reps,limit", [(1, 1), (2, 1), (3, 1), (4, 2), (5, 2), (6, 3)])
def test_noise_stop_limit_function(reps, limit):
    assert r.noise_stop_limit(reps) == limit


class NoiseRunnerN(NoiseRunner):
    """NoiseRunner whose closing SOLO is at position n_arms + 1 (the base class assumes four arms)."""

    def __init__(self, bad=(), n_arms=3):
        super().__init__(bad)
        self.close = f"{n_arms + 1}_"

    def __call__(self, arm, rep, out_dir, cfg):
        attempt = int(out_dir.parent.name[len("attempt"):])
        self.calls.append((rep, attempt, out_dir.name))
        frame = {"p99": 25.0 if arm == "SOLO" and out_dir.name.startswith(self.close) and (rep, attempt) in self.bad else 20.0, "hitch_share": 0.1}
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "result.json").write_text(json.dumps({"arm": arm, "rep": rep, "frame": frame}))


def sweep(tmp_path, runner, reps, arms=r.DEFAULT_ARMS):
    order = r.make_order(3, reps, arms)
    r.run_sweep(make_cfg(tmp_path), tmp_path / "run", order, runner, seed=3, noise_check=r.rep_noise_from_results, log=lambda *a: None)


def test_three_reps_second_distinct_failing_rep_stops(tmp_path):
    sweep(tmp_path / "ok", NoiseRunnerN(bad={(0, 1)}), 3, ARMS3)          # one failing rep: continues
    assert r.noise_failed_reps(tmp_path / "ok" / "run") == {0}
    with pytest.raises(r.NoiseStop, match=r"more than 1 of 3 reps failed the noise check") as e:
        sweep(tmp_path, NoiseRunnerN(bad={(0, 1), (2, 1)}), 3, ARMS3)
    assert "[0, 2]" in str(e.value)


def test_three_reps_same_rep_failing_twice_does_not_stop(tmp_path):
    sweep(tmp_path, NoiseRunnerN(bad={(1, 1), (1, 2)}), 3, ARMS3)
    assert r.noise_failed_reps(tmp_path / "run") == {1}


def test_five_reps_unchanged_third_stops(tmp_path):
    sweep(tmp_path / "ok", NoiseRunner(bad={(0, 1), (1, 1)}), 5)
    with pytest.raises(r.NoiseStop, match=r"more than 2 of 5 reps failed the noise check"):
        sweep(tmp_path, NoiseRunner(bad={(0, 1), (1, 1), (2, 1)}), 5)


# ------------------------------------------------------------------ --check-clocks with the game running
@pytest.mark.parametrize("game", [True, False])
def test_check_clocks_works_with_game_running(tmp_path, game, capsys):
    argv = main_args(tmp_path, "--check-clocks", "--run-dir", str(tmp_path / "run"))
    assert r.main(argv, probes=ClockProbes(game=game)) == 0
    doc = json.loads((tmp_path / "run" / "clock_check.json").read_text())
    assert doc["status"] == "passed" and doc["game_running"] is game
    assert "absent" not in capsys.readouterr().err


def test_check_clocks_refused_still_records_game_running(tmp_path):
    argv = main_args(tmp_path, "--check-clocks", "--run-dir", str(tmp_path / "run"))
    assert r.main(argv, probes=ClockProbes(game=True, helper=["pipe"])) == 2
    doc = json.loads((tmp_path / "run" / "clock_check.json").read_text())
    assert doc["status"] == "refused" and doc["game_running"] is True


def test_llm_alone_still_needs_game_absent(tmp_path):
    rg_synth.write_fresh_clock_check(tmp_path / "run", rehearsal=False)
    code = r.main(main_args(tmp_path, "--llm-alone", "--run-dir", str(tmp_path / "run")), probes=ClockProbes(game=True), runner=lambda *a, **k: None)
    assert code == 2
