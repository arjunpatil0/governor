import json
import random

import pytest

from test_cell import FakeProbes, make_cfg
from tools.realgame import run as r

ARMS4 = ("UNGATED", "PRIO_IDLE", "DUTY50", "IGPU")


def test_preregistered_seed_default():
    assert r.DEFAULT_SEED == 89770043 and r.DEFAULT_ARMS == ARMS4 and r.DEFAULT_REPS == 5


def test_make_order_reproducible_and_shape():
    a, b = r.make_order(89770043, 5), r.make_order(89770043, 5)
    assert a == b and len(a) == 5
    for rep in a:
        assert rep[0] == "SOLO" and rep[-1] == "SOLO" and sorted(rep[1:-1]) == sorted(ARMS4) and len(rep) == 6
    assert r.make_order(1, 5) != r.make_order(2, 5)
    assert len({tuple(x[1:-1]) for x in a}) > 1                  # actually shuffled, not the same order every rep


def test_make_order_does_not_touch_global_random_state():
    random.seed(5)
    st = random.getstate()
    r.make_order(89770043, 5)
    assert random.getstate() == st


def test_make_order_pinned_for_preregistered_seed():
    assert r.make_order(89770043, 5) == PINNED


def test_make_order_default_args_and_custom_arms():
    assert r.make_order() == r.make_order(89770043, 5, ARMS4)
    o = r.make_order(3, 2, arms=("UNGATED", "PRIO_IDLE", "DUTY50"))
    assert all(len(x) == 5 for x in o)
    with pytest.raises(ValueError):
        r.make_order(3, 0)
    with pytest.raises(ValueError):
        r.make_order(3, 2, arms=("UNGATED", "UNGATED"))
    with pytest.raises(ValueError):
        r.make_order(3, 2, arms=("SOLO", "UNGATED"))


class Runner:
    def __init__(self, fail_at=None, interrupt_at=None):
        self.calls, self.fail_at, self.interrupt_at = [], fail_at or set(), interrupt_at

    def __call__(self, arm, rep, out_dir, cfg):
        key = (arm, rep, out_dir.parent.name if arm != "LLM_ALONE" else "x", out_dir.name)
        self.calls.append(key)
        if self.interrupt_at is not None and len(self.calls) == self.interrupt_at:
            raise KeyboardInterrupt
        if (arm, rep, len(self.calls)) in self.fail_at or any(f == (arm, rep, out_dir.parent.name) for f in self.fail_at):
            raise RuntimeError("synthetic cell failure")
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "result.json").write_text(json.dumps({"arm": arm, "rep": rep}))
        return {"arm": arm}


def sweep(tmp_path, runner, reps=2, seed=3, **kw):
    cfg = make_cfg(tmp_path)
    order = r.make_order(seed, reps)
    r.run_sweep(cfg, tmp_path / "run", order, runner, seed=seed, **kw)
    return order


def test_sweep_never_runs_llm_alone_and_runs_every_cell(tmp_path):
    run = Runner()
    sweep(tmp_path, run)
    assert all(c[0] != "LLM_ALONE" for c in run.calls) and len(run.calls) == 2 * 6
    assert not (tmp_path / "run" / "llm_alone").exists()
    meta = json.loads((tmp_path / "run" / "run_meta.json").read_text())
    assert meta["seed"] == 3 and meta["order"] == r.make_order(3, 2) and meta["reps"] == 2


def test_resume_skips_cells_with_result_json_and_reproduces_order(tmp_path):
    first = Runner(interrupt_at=5)
    with pytest.raises(KeyboardInterrupt):
        sweep(tmp_path, first)
    done = [p.parent.name for p in (tmp_path / "run").rglob("result.json")]
    assert len(done) == 4
    second = Runner()
    order = sweep(tmp_path, second)
    assert len(second.calls) == 6 + 6                          # the interrupted attempt is abandoned: rep 0 restarts as attempt 2 (item G)
    assert json.loads((tmp_path / "run" / "run_meta.json").read_text())["order"] == order
    assert len(list((tmp_path / "run").rglob("result.json"))) == 4 + 12
    third = Runner()
    sweep(tmp_path, third)
    assert third.calls == []


def test_resume_refuses_different_seed_or_reps(tmp_path):
    sweep(tmp_path, Runner())
    with pytest.raises(ValueError, match="run_meta"):
        sweep(tmp_path, Runner(), seed=4)
    with pytest.raises(ValueError, match="run_meta"):
        sweep(tmp_path, Runner(), reps=3)


def test_failed_cell_reruns_whole_rep_same_order_and_keeps_attempts(tmp_path):
    cfg = make_cfg(tmp_path)
    order = r.make_order(3, 2)
    third_arm = order[0][2]
    run = Runner(fail_at={(third_arm, 0, "attempt1")})
    r.run_sweep(cfg, tmp_path / "run", order, run, seed=3)
    rep0 = sorted(p.name for p in (tmp_path / "run" / "rep0").iterdir())
    assert rep0 == ["attempt1", "attempt2"]
    a1 = tmp_path / "run" / "rep0" / "attempt1"
    failed = [p for p in a1.rglob("FAILED.json")]
    assert len(failed) == 1 and "synthetic cell failure" in failed[0].read_text()
    assert (a1 / f"0_SOLO" / "result.json").exists()                       # attempt 1's finished cell is kept
    a2 = sorted(p.name for p in (tmp_path / "run" / "rep0" / "attempt2").iterdir() if p.is_dir())      # NOISE_OK.json is a file
    assert a2 == [f"{i}_{a}" for i, a in enumerate(order[0])]              # whole rep, same order
    assert r.final_attempts(tmp_path / "run", order) == {0: 2, 1: 1}


def test_failure_exhausts_attempts_and_raises(tmp_path):
    cfg = make_cfg(tmp_path)
    order = r.make_order(3, 1)
    run = Runner(fail_at={("SOLO", 0, f"attempt{n}") for n in (1, 2, 3)})
    with pytest.raises(RuntimeError, match="(?i)twice|attempts"):       # the identical error twice in a row is deterministic: stops after attempt 2
        r.run_sweep(cfg, tmp_path / "run", order, run, seed=3, max_attempts=3)
    assert len(list((tmp_path / "rep0" if False else tmp_path / "run" / "rep0").iterdir())) == 2


def test_rest_between_cells_with_rep_start_temperature(tmp_path):
    temps, rests = iter([55.0, 56.0, 57.0, 58.0, 59.0, 60.0, 61.0, 62.0, 63.0, 64.0, 65.0, 66.0, 67.0]), []

    def rest(read_temp, start_temp):
        rests.append((start_temp, read_temp()))
        return {"rest_s": 31.0, "reached": True, "start_temp": start_temp, "final_temp": 55.0}
    sweep(tmp_path, Runner(), reps=1, read_temp=lambda: next(temps), rest=rest)
    log = [json.loads(line) for line in (tmp_path / "run" / "rest_log.jsonl").read_text().splitlines()]
    assert len(rests) == len(log) == 5 and {x[0] for x in rests} == {55.0}
    assert all(e["rest_s"] == 31.0 and "rep" in e and "after" in e for e in log)


def test_dry_run_prints_order_and_runs_preflight_only(tmp_path, capsys):
    called = []
    code = r.main(["--dry-run", "--reps", "2", "--armoury-mode", "Turbo", "--llm-exe", "a", "--model", "b", "--prompt", "c", "--presentmon", "d",
                   "--game-process", "g.exe", "--n-prompt", "64", "--igpu-vk-index", "1", "--llama-dir", str(tmp_path / "llama.cpp"), "--repo-root", str(tmp_path)],
                  probes=FakeProbes(), runner=lambda *a: called.append(a))
    out = capsys.readouterr().out
    assert code == 0 and called == []
    assert "89770043" in out and "SOLO" in out and "rep 0" in out and "rep 1" in out and "LLM_ALONE" in out


def test_dry_run_preflight_refusal_exit_code(tmp_path, capsys):
    code = r.main(["--dry-run", "--armoury-mode", "Turbo", "--llm-exe", "a", "--model", "b", "--prompt", "c", "--presentmon", "d", "--game-process", "g.exe",
                   "--n-prompt", "64", "--igpu-vk-index", "1", "--llama-dir", str(tmp_path / "llama.cpp"), "--repo-root", str(tmp_path)], probes=FakeProbes(dirty=[" M x"]))
    assert code != 0 and "dirty" in capsys.readouterr().err


def test_main_requires_armoury_mode_flag(tmp_path, capsys):
    code = r.main(["--dry-run", "--llm-exe", "a", "--model", "b", "--prompt", "c", "--presentmon", "d", "--game-process", "g.exe", "--n-prompt", "64",
                   "--igpu-vk-index", "1", "--llama-dir", str(tmp_path / "llama.cpp"), "--repo-root", str(tmp_path)], probes=FakeProbes())
    assert code != 0 and "armoury" in capsys.readouterr().err


# regression pin of the shuffle for the preregistered seed (generated by this implementation, random.Random(89770043), reps=5, default arms)
PINNED = [['SOLO', 'PRIO_IDLE', 'UNGATED', 'IGPU', 'DUTY50', 'SOLO'], ['SOLO', 'IGPU', 'UNGATED', 'DUTY50', 'PRIO_IDLE', 'SOLO'], ['SOLO', 'UNGATED', 'PRIO_IDLE', 'IGPU', 'DUTY50', 'SOLO'], ['SOLO', 'DUTY50', 'PRIO_IDLE', 'UNGATED', 'IGPU', 'SOLO'], ['SOLO', 'DUTY50', 'PRIO_IDLE', 'UNGATED', 'IGPU', 'SOLO']]
