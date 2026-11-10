"""Amendments 14 (per-rep noise rerun), 15 (clock-state preflight), 17 (PresentMode recorded). All with fakes."""
import json

import pytest

import rg_synth

from test_cell import Clock, FakeProbes, FakeSampler, make_cfg, make_deps
from tools.realgame import cell as c
from tools.realgame import clockcheck as cc
from tools.realgame import run as r

GOOD = {"p99": 20.0, "hitch_share": 0.1}


class NoiseRunner:
    """Writes result.json with a frame block; the closing SOLO of the (rep, attempt) pairs in `bad` is noisy (p99 20 vs 25)."""

    def __init__(self, bad=()):
        self.bad, self.calls = set(bad), []

    def __call__(self, arm, rep, out_dir, cfg):
        attempt = int(out_dir.parent.name[len("attempt"):])
        self.calls.append((rep, attempt, out_dir.name))
        frame = dict(GOOD)
        if arm == "SOLO" and out_dir.name.startswith("5_") and (rep, attempt) in self.bad:
            frame = {"p99": 25.0, "hitch_share": 0.1}
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "result.json").write_text(json.dumps({"arm": arm, "rep": rep, "frame": frame}))


def sweep(tmp_path, runner, reps=5, **kw):
    order = r.make_order(3, reps)
    r.run_sweep(make_cfg(tmp_path), tmp_path / "run", order, runner, seed=3, noise_check=r.rep_noise_from_results, log=lambda *a: None, **kw)
    return order


def test_one_noisy_rep_reruns_and_sweep_completes(tmp_path):
    run = NoiseRunner(bad={(2, 1)})
    order = sweep(tmp_path, run)
    assert r.final_attempts(tmp_path / "run", order) == {0: 1, 1: 1, 2: 2, 3: 1, 4: 1}
    failed = json.loads((tmp_path / "run" / "rep2" / "attempt1" / "5_SOLO" / "FAILED.json").read_text())
    assert failed["reason"] == "noise" and "p99" in failed["error"]
    assert (tmp_path / "run" / "rep2" / "attempt1" / "5_SOLO" / "result.json").exists()      # every attempt kept
    assert sorted(p.name for p in (tmp_path / "run" / "rep2").iterdir()) == ["attempt1", "attempt2"]
    assert len(run.calls) == 5 * 6 + 6
    assert [x[2] for x in run.calls if x[:2] == (2, 2)] == [f"{i}_{a}" for i, a in enumerate(order[2])]      # same order on the rerun


def test_rep_failing_at_attempt1_and_passing_at_attempt2_still_counts(tmp_path):
    # reps 0 and 1 fail once each and pass on attempt 2; rep 2 fails once: three distinct reps -> stop even though each later passed
    run = NoiseRunner(bad={(0, 1), (1, 1), (2, 1)})
    with pytest.raises(r.NoiseStop, match="(?i)noise"):
        sweep(tmp_path, run)
    assert r.noise_failed_reps(tmp_path / "run") == {0, 1, 2}


def test_two_noisy_reps_do_not_stop(tmp_path):
    run = NoiseRunner(bad={(0, 1), (1, 1)})
    sweep(tmp_path, run)
    assert r.noise_failed_reps(tmp_path / "run") == {0, 1}


def test_same_rep_failing_twice_counts_once_but_respects_max_attempts(tmp_path):
    sweep(tmp_path, NoiseRunner(bad={(1, 1), (1, 2)}))
    assert r.noise_failed_reps(tmp_path / "run") == {1}
    with pytest.raises(RuntimeError, match="attempts"):
        sweep(tmp_path / "x", NoiseRunner(bad={(1, 1), (1, 2), (1, 3)}))


def test_noise_stop_persists_across_resume(tmp_path):
    with pytest.raises(r.NoiseStop):
        sweep(tmp_path, NoiseRunner(bad={(0, 1), (1, 1), (2, 1)}))
    with pytest.raises(r.NoiseStop):
        sweep(tmp_path, NoiseRunner())


def test_main_returns_nonzero_on_noise_stop(tmp_path, capsys, monkeypatch):
    def boom(*a, **k):
        raise r.NoiseStop("3 of 5 reps failed the noise check")
    monkeypatch.setattr(r, "run_sweep", boom)
    from test_review2 import main_args
    rg_synth.write_fresh_clock_check(tmp_path / "run")
    code = r.main(main_args(tmp_path, "--igpu-vk-index", "1", "--run-dir", str(tmp_path / "run")), probes=FakeProbes(), runner=lambda *a: None)
    assert code not in (0, None) and "noise" in capsys.readouterr().err.lower()


def test_main_wires_the_real_noise_check(tmp_path, monkeypatch):
    seen = {}
    monkeypatch.setattr(r, "run_sweep", lambda *a, **k: seen.update(k))
    from test_review2 import main_args
    rg_synth.write_fresh_clock_check(tmp_path / "run")
    assert r.main(main_args(tmp_path, "--igpu-vk-index", "1", "--run-dir", str(tmp_path / "run")), probes=FakeProbes(), runner=lambda *a: None) == 0
    assert seen["noise_check"] is r.rep_noise_from_results


# ================================================================= amendment 15: clock state
class FakeTimeSrc:
    def __init__(self):
        self.t = 0.0

    def now(self):
        return self.t

    def sleep(self, s):
        self.t += s


def probe(samples, **kw):
    it = iter(samples)
    ts = FakeTimeSrc()
    last = []

    def reader():
        last.append(next(it, last[-1] if last else None))
        return last[-1]
    return cc.probe_idle(reader, clock=ts.now, sleep=ts.sleep, **kw), ts


def s(sm, pstate="P0", util=0):
    return {"sm": sm, "pstate": pstate, "util": util}


def test_helper_pipe_present_refuses():
    assert cc.helper_present(list_pipes=lambda: ["governor_clock"], list_cmdlines=lambda: []) != []
    assert cc.PIPE_PATH == r"\\.\pipe\governor_clock"


def test_helper_process_present_refuses():
    got = cc.helper_present(list_pipes=lambda: [], list_cmdlines=lambda: ["C:\\py\\python.exe actuators\\clock_helper.py --serve"])
    assert got and "clock_helper" in got[0]


def test_helper_absent_passes():
    assert cc.helper_present(list_pipes=lambda: [], list_cmdlines=lambda: ["python.exe -m pytest", "explorer.exe", None, ""]) == []


def test_helper_lister_failure_is_best_effort_not_a_crash():
    def boom():
        raise OSError("access denied")
    assert cc.helper_present(list_pipes=lambda: [], list_cmdlines=boom) == []


def test_idle_probe_locked_when_sm_above_1000_in_p0_for_3s():
    res, ts = probe([s(1800)] * 100)
    assert res["status"] == "locked" and res["locked"] is True and ts.t >= 3.0 and res["n"] >= 5
    assert res["thresholds"]["idle_sm_mhz_above"] == 1000 and res["thresholds"]["probe_s"] == 3.0


@pytest.mark.parametrize("samples", [[s(210, "P8")] * 100, [s(1000)] * 100, [s(1800, "P8")] * 100, [s(1800)] * 5 + [s(900)] * 100])
def test_idle_probe_not_locked(samples):
    res, _ = probe(samples)
    assert res["status"] == "unlocked" and res["locked"] is False


def test_idle_probe_boundary_1001_is_locked_1000_is_not():
    assert probe([s(1001)] * 100)[0]["locked"] is True
    assert probe([s(1000)] * 100)[0]["locked"] is False


def test_idle_probe_inconclusive_if_gpu_not_idle_or_reader_fails():
    res, _ = probe([s(1800, util=35)] * 100)
    assert res["status"] == "inconclusive" and res["locked"] is False

    def broken():
        raise RuntimeError("no nvml")
    res = cc.probe_idle(broken, clock=FakeTimeSrc().now, sleep=lambda x: None)
    assert res["status"] == "inconclusive" and "no nvml" in res["error"]


def test_pstate_formats_normalised():
    assert probe([{"sm": 1800, "pstate": 0, "util": 0}] * 100)[0]["locked"] is True
    assert probe([{"sm": 1800, "pstate": " P0", "util": "0 %"}] * 100)[0]["locked"] is True


def test_constant_clock_check_boundaries():
    assert cc.constant_clock([1500] * 200)["constant"] is True
    assert cc.constant_clock([1500] * 199)["constant"] is False          # fewer than 200 samples: no verdict
    assert cc.constant_clock([1500] * 199 + [1515])["constant"] is False
    assert cc.constant_clock([])["constant"] is False
    got = cc.constant_clock([1500] * 300)
    assert got["n"] == 300 and got["distinct"] == 1 and got["min_samples"] == 200


class ClockProbes(FakeProbes):
    def __init__(self, helper=(), idle=None, **kw):
        super().__init__(**kw)
        self.helper, self.idle, self.idle_calls = list(helper), idle, 0

    def admin_helper_present(self):
        return self.helper

    def clock_idle_probe(self):
        self.idle_calls += 1
        return self.idle or {"status": "unlocked", "locked": False, "n": 12}


def test_preflight_refuses_when_admin_helper_present(tmp_path):
    with pytest.raises(c.PreflightError, match="(?i)clock helper"):
        c.preflight(make_cfg(tmp_path), ClockProbes(helper=["pipe exists"]))


def test_preflight_refuses_when_idle_probe_says_locked_game_absent(tmp_path):
    with pytest.raises(c.PreflightError, match="(?i)locked"):
        c.preflight(make_cfg(tmp_path), ClockProbes(game=False, idle={"status": "locked", "locked": True, "n": 12}), need_game=False, game_absent=True)
    with pytest.raises(c.PreflightError, match="(?i)cannot confirm"):
        c.preflight(make_cfg(tmp_path), ClockProbes(game=False, idle={"status": "inconclusive", "locked": False, "error": "gpu busy"}), need_game=False, game_absent=True)


def test_preflight_idle_probe_only_runs_when_game_absent(tmp_path):
    p = ClockProbes(game=True, idle={"status": "locked", "locked": True})
    assert c.preflight(make_cfg(tmp_path), p) is None and p.idle_calls == 0          # game running: the idle heuristic does not apply
    p = ClockProbes(game=False)
    assert c.preflight(make_cfg(tmp_path), p, need_game=False, game_absent=True) is None and p.idle_calls == 1


def test_run_cell_refuses_with_helper_present_and_writes_no_result(tmp_path):
    clock = Clock()
    cfg = make_cfg(tmp_path)
    d, _ = make_deps(cfg, clock)
    d.probes = ClockProbes(helper=["process: clock_helper.py"])
    with pytest.raises(RuntimeError, match="(?i)clock helper"):
        c.run_cell("SOLO", 0, tmp_path / "cell", cfg, d)
    assert not (tmp_path / "cell" / "result.json").exists()


def test_run_cell_refuses_when_idle_probe_locked_llm_alone(tmp_path):
    clock = Clock()
    cfg = make_cfg(tmp_path)
    d, _ = make_deps(cfg, clock)
    d.probes = ClockProbes(game=False, idle={"status": "locked", "locked": True})
    with pytest.raises(RuntimeError, match="(?i)locked"):
        c.run_cell("LLM_ALONE", 0, tmp_path / "cell", cfg, d)


def test_meta_records_clock_state_probe_thresholds_and_elevation(tmp_path):
    clock = Clock()
    cfg = make_cfg(tmp_path)
    d, _ = make_deps(cfg, clock)
    d.probes = ClockProbes(game=False, idle={"status": "unlocked", "locked": False, "n": 12})
    c.run_cell("LLM_ALONE", 0, tmp_path / "cell", cfg, d)
    meta = json.loads((tmp_path / "cell" / "meta.json").read_text())
    cs = meta["clock_state"]
    assert cs["idle_probe"]["status"] == "unlocked" and cs["helper_present"] == []
    assert cs["heuristic"] == {"idle_sm_mhz_above": 1000, "pstate": "P0", "probe_s": 3.0, "idle_util_pct": 0, "constant_min_samples": 200}
    assert cs["loaded_constant_check"]["constant"] is False and meta["elevated"] is False


def test_meta_idle_probe_skipped_with_game_present(tmp_path):
    clock = Clock()
    cfg = make_cfg(tmp_path)
    d, _ = make_deps(cfg, clock)
    d.probes = ClockProbes(game=True)
    c.run_cell("SOLO", 0, tmp_path / "cell", cfg, d)
    assert "skipped" in json.loads((tmp_path / "cell" / "meta.json").read_text())["clock_state"]["idle_probe"]


class ConstSampler(FakeSampler):
    def __init__(self, clock, sm_value, dt=0.01):
        super().__init__(clock)
        n = 4000
        self.t = [1000.0 + i * dt for i in range(n)]
        self.sm = [sm_value(i) for i in range(n)]
        self.throttle, self.temp = [0] * n, [60] * n


def cell_deps(tmp_path, sampler_factory=None, **probe_kw):
    clock = Clock()
    cfg = make_cfg(tmp_path)
    d, _ = make_deps(cfg, clock)
    d.probes = ClockProbes(**probe_kw)
    if sampler_factory:
        d.make_sampler = lambda nv: sampler_factory(clock)
    return cfg, d


def test_loaded_cell_with_constant_sm_clock_fails_and_is_recorded(tmp_path):
    cfg, d = cell_deps(tmp_path, lambda clock: ConstSampler(clock, lambda i: 1500))          # 600 samples in the 6 s window, one distinct value
    with pytest.raises(RuntimeError, match="(?i)constant.*locked"):
        c.run_cell("SOLO", 0, tmp_path / "cell", cfg, d)
    assert not (tmp_path / "cell" / "result.json").exists()
    assert json.loads((tmp_path / "cell" / "meta.json").read_text())["clock_state"]["loaded_constant_check"]["constant"] is True


def test_loaded_cell_with_varying_sm_clock_passes(tmp_path):
    cfg, d = cell_deps(tmp_path, lambda clock: ConstSampler(clock, lambda i: 1500 + (i % 3) * 15))
    c.run_cell("SOLO", 0, tmp_path / "cell", cfg, d)
    assert (tmp_path / "cell" / "result.json").exists()


def test_few_constant_samples_do_not_fail(tmp_path):
    cfg, d = cell_deps(tmp_path, lambda clock: ConstSampler(clock, lambda i: 1500, dt=0.05))    # 120 samples in the window (< 200)
    c.run_cell("SOLO", 0, tmp_path / "cell", cfg, d)
    assert (tmp_path / "cell" / "result.json").exists()


def test_constant_clock_failure_reruns_the_rep(tmp_path):
    def runner(arm, rep, out_dir, cfg):
        if arm == "UNGATED" and out_dir.parent.name == "attempt1":
            raise RuntimeError("SM clock constant over 600 samples: looks locked")
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "result.json").write_text("{}")
    order = r.make_order(3, 1)
    r.run_sweep(make_cfg(tmp_path), tmp_path / "run", order, runner, seed=3, log=lambda *a: None)
    assert r.final_attempts(tmp_path / "run", order) == {0: 2}


def test_check_clocks_mode(tmp_path, capsys):
    from test_review2 import main_args
    argv = main_args(tmp_path, "--check-clocks")
    assert r.main(argv, probes=ClockProbes(game=False)) == 0
    assert "unlocked" in capsys.readouterr().out
    assert r.main(argv, probes=ClockProbes(game=False, idle={"status": "locked", "locked": True})) == 2
    assert "locked" in capsys.readouterr().err
    assert r.main(argv, probes=ClockProbes(game=False, helper=["pipe"])) == 2
    capsys.readouterr()
    assert r.main(argv, probes=ClockProbes(game=True)) == 2          # the idle probe needs the game absent
    assert "absent" in capsys.readouterr().err


def test_check_clocks_needs_no_presentmon_or_nprompt(tmp_path):
    assert r.main(["--check-clocks", "--game-process", "g.exe"], probes=ClockProbes(game=False)) == 0


# ================================================================= amendment 17: PresentMode
def test_present_modes_recorded_in_result_json(tmp_path):
    cfg, d = cell_deps(tmp_path, game=True)
    res = c.run_cell("SOLO", 0, tmp_path / "cell", cfg, d)
    assert res["present_modes"] == ["Flip"]          # the FakeCapture rows carry PresentMode 'Flip'
    assert json.loads((tmp_path / "cell" / "result.json").read_text())["present_modes"] == ["Flip"]


def test_present_modes_none_without_capture(tmp_path):
    cfg, d = cell_deps(tmp_path, game=False)
    assert c.run_cell("LLM_ALONE", 0, tmp_path / "cell", cfg, d)["present_modes"] is None
