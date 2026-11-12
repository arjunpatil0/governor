"""Hardening after the first owner run: device selection by description (RG_DEVICE_MATCH), CellRefused fail-fast, --rehearse, the rehearsal gate, per-invocation attempt budget,
--stop-after-reps, progress lines and STATUS.txt. All with fakes (no GPU, no PresentMon)."""
import json
import re
import time
from pathlib import Path

import pytest

import rg_synth
from test_cell import Clock, FakeLlm, FakeProbes, FakeSampler, make_cfg, make_deps
from test_review2 import BadPm, main_args
from tools.realgame import cell as c
from tools.realgame import run as r
from tools.realgame.gpu_priority import CLASSES, PriorityError

ROOT = Path(__file__).resolve().parents[2]
CPP = ROOT / "workloads" / "background" / "llama_realgame_bench.cpp"
RTX = "NVIDIA GeForce RTX 4070 Laptop GPU"
RADEON = "AMD Radeon(TM) 780M Graphics"


def varying_sampler(clock):
    sm = FakeSampler(clock)
    sm.limit = [95.0] * len(sm.t)
    sm.sm = [1500 if i % 2 else 1600 for i in range(len(sm.t))]
    return sm


def deps_for(tmp_path, cfg=None, game=True, **kw):
    clock = Clock()
    cfg = cfg or make_cfg(tmp_path)
    d, box = make_deps(cfg, clock, **kw)
    d.make_sampler = lambda nv: varying_sampler(clock)
    d.probes = FakeProbes(game=game)
    return cfg, d, clock


def with_device(d, clock, device, extra_lines=()):
    def spawn(cmd, env, p):
        line = f"EXEC_MODE {env['RG_BACKEND']} device={device} offloaded=29/29 n_layer=28 duty={env['RG_DUTY']}"
        llm = FakeLlm(clock, p, line)
        llm.lines += list(extra_lines)
        return llm
    d.spawn_llm = spawn


# ================================================================= 1. driver source
def test_driver_reads_device_match_and_uses_a_device_list():
    src = CPP.read_text(encoding="utf-8")
    for needle in ("RG_DEVICE_MATCH", "ggml_backend_dev_count", "ggml_backend_dev_description", "mp.devices", "LLAMA_SPLIT_MODE_NONE", "mp.main_gpu = 0", "\"Vulkan\"", "tolower"):
        assert needle in src, needle
    assert "FATAL" in src and "available" in src                        # a clear FATAL naming the available descriptions
    # EXEC_MODE prints the device actually used
    assert "if (chosen) devname = ggml_backend_dev_description(chosen)" in src


# ================================================================= 2. cell: device checks and env
def test_cell_refused_is_a_runtime_error():
    assert issubclass(c.CellRefused, RuntimeError)


def test_config_defaults_and_vk_index_ignored(tmp_path):
    cfg = make_cfg(tmp_path)
    assert cfg.igpu_device_match == "780M" and cfg.cuda_device_match == "RTX"


@pytest.mark.parametrize("arm", ["UNGATED", "PRIO_IDLE", "DUTY50", "SOLO", "LLM_ALONE"])
def test_cuda_arms_get_rtx_match_never_inherited(tmp_path, monkeypatch, arm):
    monkeypatch.setenv("RG_DEVICE_MATCH", "inherited-junk")
    monkeypatch.setenv("GGML_VK_VISIBLE_DEVICES", "0")
    seen = []
    cfg, d, clock = deps_for(tmp_path, game=(arm != "LLM_ALONE"))
    orig = d.spawn_llm
    d.spawn_llm = lambda cmd, env, p: (seen.append(dict(env)), orig(cmd, env, p))[1]
    c.run_cell(arm, 0, tmp_path / "o", cfg, d)
    if arm == "SOLO":
        assert seen == []
    else:
        assert seen[0]["RG_DEVICE_MATCH"] == "RTX" and "GGML_VK_VISIBLE_DEVICES" not in seen[0]


def test_igpu_gets_its_match_and_not_the_vk_index(tmp_path, monkeypatch):
    monkeypatch.setenv("GGML_VK_VISIBLE_DEVICES", "0")
    seen = []
    cfg, d, clock = deps_for(tmp_path)
    orig = d.spawn_llm
    d.spawn_llm = lambda cmd, env, p: (seen.append(dict(env)), orig(cmd, env, p))[1]
    c.run_cell("IGPU", 0, tmp_path / "o", cfg, d)
    assert seen[0]["RG_DEVICE_MATCH"] == "780M" and "GGML_VK_VISIBLE_DEVICES" not in seen[0]
    assert json.loads((tmp_path / "o" / "meta.json").read_text())["igpu_device_match"] == "780M"


def test_igpu_wrong_device_is_cell_refused(tmp_path):
    cfg, d, clock = deps_for(tmp_path)
    # the very failure of the owner run: the vulkan driver reported the RTX
    d.spawn_llm = lambda cmd, env, p: FakeLlm(clock, p, f"EXEC_MODE vulkan device={RTX} offloaded=29/29 n_layer=28 duty=0")
    with pytest.raises(c.CellRefused, match="780M"):
        c.run_cell("IGPU", 0, tmp_path / "o", cfg, d)


@pytest.mark.parametrize("device,ok", [(RTX, True), ("NVIDIA Something", True), ("Some RTX 5090", True), (RADEON, False), ("FAKE", False)])
def test_cuda_arm_device_must_contain_rtx_or_nvidia(tmp_path, device, ok):
    cfg, d, clock = deps_for(tmp_path)
    with_device(d, clock, device)
    if ok:
        c.run_cell("UNGATED", 0, tmp_path / "o", cfg, d)
    else:
        with pytest.raises(c.CellRefused, match="RTX"):
            c.run_cell("UNGATED", 0, tmp_path / "o", cfg, d)
        assert not (tmp_path / "o" / "result.json").exists()


def test_driver_fatal_device_match_is_cell_refused(tmp_path):
    cfg, d, clock = deps_for(tmp_path)

    class Dead(FakeLlm):
        def wait_for(self, prefix, timeout):
            raise RuntimeError("LLM driver: FATAL RG_DEVICE_MATCH '780M' matches no vulkan device; available: 'NVIDIA GeForce RTX 4070 Laptop GPU'")
    d.spawn_llm = lambda cmd, env, p: Dead(clock, p)
    with pytest.raises(c.CellRefused, match="RG_DEVICE_MATCH"):
        c.run_cell("IGPU", 0, tmp_path / "o", cfg, d)


def test_other_driver_failures_are_not_refusals(tmp_path):
    cfg, d, clock = deps_for(tmp_path)

    class Dead(FakeLlm):
        def wait_for(self, prefix, timeout):
            raise RuntimeError("LLM driver exited (rc=1) before 'READY'")
    d.spawn_llm = lambda cmd, env, p: Dead(clock, p)
    with pytest.raises(RuntimeError) as ei:
        c.run_cell("UNGATED", 0, tmp_path / "o", cfg, d)
    assert not isinstance(ei.value, c.CellRefused)


def test_power_static_change_is_cell_refused(tmp_path):
    cfg, d, clock = deps_for(tmp_path, cfg=make_cfg(tmp_path, power_static_ref={"default_power_limit_w": 99.0, "min_power_limit_w": 5.0, "max_power_limit_w": 140.0}))
    with pytest.raises(c.CellRefused, match="(?i)power"):
        c.run_cell("UNGATED", 0, tmp_path / "o", cfg, d)


def test_dll_dir_missing_is_cell_refused(tmp_path):
    cfg, d, clock = deps_for(tmp_path)
    d.probes = FakeProbes(missing=[str(c.llm_dll_dir(cfg, "cuda"))])
    with pytest.raises(c.CellRefused, match="(?i)dll"):
        c.run_cell("UNGATED", 0, tmp_path / "o", cfg, d)


def test_game_not_running_is_cell_refused(tmp_path):
    cfg, d, clock = deps_for(tmp_path, game=False)
    with pytest.raises(c.CellRefused, match="game process"):
        c.run_cell("UNGATED", 0, tmp_path / "o", cfg, d)


def test_pm_hash_mismatch_is_cell_refused(tmp_path):
    cfg, d, clock = deps_for(tmp_path)
    d.probes = BadPm()
    with pytest.raises(c.CellRefused, match="(?i)sha256"):
        c.run_cell("UNGATED", 0, tmp_path / "o", cfg, d)


def test_igpu_without_vk_exe_is_cell_refused(tmp_path):
    cfg, d, clock = deps_for(tmp_path, cfg=make_cfg(tmp_path, llm_exe_vk=None))
    with pytest.raises(c.CellRefused, match="(?i)igpu"):
        c.run_cell("IGPU", 0, tmp_path / "o", cfg, d)


def test_prio_call_failing_is_cell_refused_wrong_class_is_not(tmp_path):
    def broken(pid, cls):
        raise PriorityError("Set failed", set_status=-1073741790, readback=None)
    cfg, d, clock = deps_for(tmp_path, prio=broken)
    with pytest.raises(c.CellRefused, match="Set failed"):
        c.run_cell("PRIO_IDLE", 0, tmp_path / "a", cfg, d)

    def nonzero(pid, cls):
        raise PriorityError("Set failed", set_status=5, readback=0)
    cfg, d, clock = deps_for(tmp_path, prio=nonzero)
    with pytest.raises(c.CellRefused):
        c.run_cell("PRIO_IDLE", 0, tmp_path / "b", cfg, d)

    def wrong(pid, cls):
        raise PriorityError("read-back 2 != requested 0", set_status=0, readback=2)
    cfg, d, clock = deps_for(tmp_path, prio=wrong)
    res = c.run_cell("PRIO_IDLE", 0, tmp_path / "c", cfg, d)               # wrong class voids, the cell completes
    assert res["prio_valid"] is False


def test_prio_end_readback_call_failing_is_cell_refused(tmp_path):
    def broken(pid):
        raise PriorityError("Get failed", set_status=None, readback=None)
    cfg, d, clock = deps_for(tmp_path, get_prio=broken)
    with pytest.raises(c.CellRefused, match="Get failed"):
        c.run_cell("PRIO_IDLE", 0, tmp_path / "o", cfg, d)


# ================================================================= 3. rehearsal flag of run_cell
def test_run_cell_rehearsal_skips_capture_frames_pdh_and_pm_hash(tmp_path):
    order = []
    cfg, d, clock = deps_for(tmp_path, game=False, order=order)
    d.probes = BadPm(game=False)
    d.shared_mem = lambda pid: (_ for _ in ()).throw(AssertionError("PDH must not be read in a rehearsal"))
    res = c.run_cell("UNGATED", 0, tmp_path / "o", cfg, d, warmup_s=5.0, window_s=8.0, rehearsal=True, capture=False)
    assert not any(x[0] == "capture" for x in order) and not (tmp_path / "o" / "frames.csv").exists()
    assert d.probes.version_calls == 0
    assert res["rehearsal"] is True and res["frame"] is None and res["shared_gpu_mem_bytes"] is None and res["game_pid"] is None
    assert res["n_tokens"] > 0 and res["tok_s"] > 0 and res["warmup_s"] == 5.0 and res["window_s"] == 8.0
    assert json.loads((tmp_path / "o" / "meta.json").read_text())["rehearsal"] is True
    assert json.loads((tmp_path / "o" / "result.json").read_text())["rehearsal"] is True
    assert "power_rejected" in res and res["exec_mode"].startswith("EXEC_MODE cuda")


def test_run_cell_rehearsal_keeps_priority_readbacks_and_duty(tmp_path):
    cfg, d, clock = deps_for(tmp_path, game=False)
    res = c.run_cell("PRIO_IDLE", 0, tmp_path / "p", cfg, d, warmup_s=5.0, window_s=8.0, rehearsal=True)
    assert res["prio_readbacks"] == [0, 0] and res["prio_valid"] is True
    res = c.run_cell("DUTY50", 0, tmp_path / "d", cfg, d, warmup_s=5.0, window_s=8.0, rehearsal=True)
    assert res["duty_achieved"] == pytest.approx(0.49)


def test_run_cell_rehearsal_still_refuses_power_static_change(tmp_path):
    cfg, d, clock = deps_for(tmp_path, cfg=make_cfg(tmp_path, power_static_ref={"default_power_limit_w": 99.0, "min_power_limit_w": 5.0, "max_power_limit_w": 140.0}), game=False)
    with pytest.raises(c.CellRefused):
        c.run_cell("UNGATED", 0, tmp_path / "o", cfg, d, rehearsal=True)


def test_normal_run_cell_is_not_marked_rehearsal(tmp_path):
    cfg, d, clock = deps_for(tmp_path)
    res = c.run_cell("UNGATED", 0, tmp_path / "o", cfg, d)
    assert not res.get("rehearsal") and res["frame"] is not None


# ================================================================= 3b. run.py rehearsal
def fake_runner(results=None, errors=None, calls=None):
    results, errors = results or {}, errors or {}

    def runner(arm, rep, out_dir, cfg, **kw):
        if calls is not None:
            calls.append((arm, rep, Path(out_dir), kw))
        if arm in errors:
            raise errors[arm]
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        res = {"arm": arm, "rehearsal": True, "exec_mode": f"EXEC_MODE x device={RADEON if arm == 'IGPU' else RTX} offloaded=1/1", "n_tokens": 100, "tok_s": 20.0, "power_rejected": 0,
               "prio_readbacks": [0, 0] if arm == "PRIO_IDLE" else [], "prio_valid": True if arm == "PRIO_IDLE" else None, "duty_achieved": 0.49 if arm == "DUTY50" else None}
        res.update(results.get(arm, {}))
        (out_dir / "result.json").write_text(json.dumps(res))
        return res
    return runner


def rehearse(tmp_path, runner, arms=r.DEFAULT_ARMS, **kw):
    lines = []
    ok, doc = r.run_rehearsal(make_cfg(tmp_path), tmp_path / "run", arms, runner, log=lines.append, exe_sha256={"llm_exe": "aa"}, **kw)
    return ok, doc, lines


def test_rehearsal_constants():
    assert r.REHEARSE_WARM_S == 5.0 and r.REHEARSE_WINDOW_S == 8.0 and r.DEFAULT_MAX_REHEARSAL_AGE_S == 21600


def test_rehearsal_all_pass_writes_json_and_dirs_and_passes_short_window(tmp_path):
    calls = []
    ok, doc, lines = rehearse(tmp_path, fake_runner(calls=calls))
    assert ok is True
    assert [x[0] for x in calls] == list(r.DEFAULT_ARMS) and all(x[3] == {"warmup_s": 5.0, "window_s": 8.0, "rehearsal": True} for x in calls)
    assert all(x[2] == tmp_path / "run" / "rehearsal" / x[0] for x in calls)
    for a in r.DEFAULT_ARMS:
        assert any(re.match(rf"REHEARSAL {a}: PASS", ln) for ln in lines), (a, lines)
    j = json.loads((tmp_path / "run" / "rehearsal.json").read_text())
    assert j["rehearsal"] is True and set(j["arms"]) == set(r.DEFAULT_ARMS) and all(v["status"] == "PASS" for v in j["arms"].values())
    assert j["exe_sha256"] == {"llm_exe": "aa"} and isinstance(j["timestamp"], float) and j["timestamp_iso"]
    assert any("0.49" in ln for ln in lines if "DUTY50" in ln)                                  # duty value printed (information)
    assert not list((tmp_path / "run").glob("rep*")) and not (tmp_path / "run" / "run_meta.json").exists()


@pytest.mark.parametrize("arm,patch,needle", [
    ("UNGATED", {"exec_mode": f"EXEC_MODE cuda device={RADEON} offloaded=1/1"}, "device"),
    ("IGPU", {"exec_mode": f"EXEC_MODE vulkan device={RTX} offloaded=1/1"}, "device"),
    ("UNGATED", {"n_tokens": 0}, "tokens"),
    ("UNGATED", {"n_tokens": None}, "tokens"),
    ("PRIO_IDLE", {"prio_readbacks": [0, 2]}, "read-back"),
    ("PRIO_IDLE", {"prio_readbacks": [2, 0]}, "read-back"),
    ("PRIO_IDLE", {"prio_readbacks": [0]}, "read-back"),
    ("DUTY50", {"duty_achieved": None}, "DUTY_ACHIEVED"),
    ("UNGATED", {"power_rejected": None}, "power_rejected"),
])
def test_rehearsal_fail_reasons(tmp_path, arm, patch, needle):
    ok, doc, lines = rehearse(tmp_path, fake_runner(results={arm: patch}))
    assert ok is False and doc["arms"][arm]["status"] == "FAIL" and any(needle in x for x in doc["arms"][arm]["reasons"])
    assert any(ln.startswith(f"REHEARSAL {arm}: FAIL (") and needle in ln for ln in lines)
    assert all(doc["arms"][a]["status"] == "PASS" for a in r.DEFAULT_ARMS if a != arm)


def test_rehearsal_exception_is_fail_with_reason_and_continues(tmp_path):
    ok, doc, lines = rehearse(tmp_path, fake_runner(errors={"PRIO_IDLE": c.CellRefused("priority call failed"), "DUTY50": RuntimeError("1 context reset row(s) fall inside the window")}))
    assert ok is False
    assert doc["arms"]["PRIO_IDLE"]["status"] == "FAIL" and "priority call failed" in doc["arms"]["PRIO_IDLE"]["reasons"][0]
    assert doc["arms"]["DUTY50"]["status"] == "FAIL" and "context reset" in doc["arms"]["DUTY50"]["reasons"][0]
    assert doc["arms"]["UNGATED"]["status"] == "PASS" and doc["arms"]["IGPU"]["status"] == "PASS"


def test_rehearsal_drop_igpu_runs_three_arms(tmp_path):
    calls = []
    ok, doc, _ = rehearse(tmp_path, fake_runner(calls=calls), arms=("UNGATED", "PRIO_IDLE", "DUTY50"))
    assert ok and [x[0] for x in calls] == ["UNGATED", "PRIO_IDLE", "DUTY50"] and "IGPU" not in doc["arms"]


def test_rehearsal_replaces_stale_arm_directory(tmp_path):
    stale = tmp_path / "run" / "rehearsal" / "UNGATED"
    stale.mkdir(parents=True)
    (stale / "result.json").write_text(json.dumps({"stale": True}))
    rehearse(tmp_path, fake_runner(errors={"UNGATED": RuntimeError("boom")}))
    assert not (stale / "result.json").exists()


# ---- main --rehearse end to end through the real run_cell with fakes
def rehearse_argv(tmp_path, *extra):
    return main_args(tmp_path, "--rehearse", "--run-dir", str(tmp_path / "run"), *extra)


def main_deps(tmp_path):
    cfg, d, clock = deps_for(tmp_path, game=False)
    d.probes = BadPm(game=False)
    d.shared_mem = lambda pid: (_ for _ in ()).throw(AssertionError("PDH"))
    d.make_capture = lambda *a: (_ for _ in ()).throw(AssertionError("capture"))
    return d


def test_main_rehearse_runs_every_llm_arm_without_game_and_presentmon(tmp_path, capsys):
    d = main_deps(tmp_path)
    code = r.main(rehearse_argv(tmp_path), probes=BadPm(game=False), deps=d)
    out = capsys.readouterr().out
    assert code == 0
    for a in r.DEFAULT_ARMS:
        assert f"REHEARSAL {a}: PASS" in out
        assert (tmp_path / "run" / "rehearsal" / a / "result.json").exists()
    j = json.loads((tmp_path / "run" / "rehearsal.json").read_text())
    assert j["exe_sha256"]["llm_exe"] and j["exe_sha256"]["llm_exe_vk"]
    assert not list((tmp_path / "run").glob("rep*"))


def test_main_rehearse_exit_nonzero_when_an_arm_fails(tmp_path, capsys):
    d = main_deps(tmp_path)
    clock = Clock()
    code = r.main(rehearse_argv(tmp_path), probes=BadPm(game=False), deps=d, runner=fake_runner(errors={"IGPU": c.CellRefused("device mismatch")}))
    assert code != 0 and "REHEARSAL IGPU: FAIL" in capsys.readouterr().out


def test_main_rehearse_drop_igpu(tmp_path, capsys):
    calls = []
    code = r.main(rehearse_argv(tmp_path, "--drop-igpu", "no vulkan"), probes=BadPm(game=False), runner=fake_runner(calls=calls))
    assert code == 0 and [x[0] for x in calls] == ["UNGATED", "PRIO_IDLE", "DUTY50"]


def test_main_rehearse_needs_no_presentmon_arg_but_still_preflights(tmp_path, capsys):
    argv = [x for x in rehearse_argv(tmp_path) if x not in ("--presentmon", "d")]
    assert r.main(argv, probes=FakeProbes(game=False, dirty=[" M x"]), runner=fake_runner()) == 2          # same preflight (git tree dirty)
    assert "dirty" in capsys.readouterr().err
    assert r.main(argv, probes=FakeProbes(game=False), runner=fake_runner()) == 0


def test_main_rehearse_cannot_combine_and_needs_run_dir(tmp_path):
    with pytest.raises(SystemExit):
        r.main(main_args(tmp_path, "--rehearse", "--smoke", "SOLO", "--run-dir", str(tmp_path / "run")), probes=FakeProbes())
    with pytest.raises(SystemExit):
        r.main(main_args(tmp_path, "--rehearse", "--llm-alone", "--run-dir", str(tmp_path / "run")), probes=FakeProbes())
    assert r.main(main_args(tmp_path, "--rehearse"), probes=FakeProbes(game=False), runner=fake_runner()) == 2


# ================================================================= 3c. the rehearsal gate
def sweep_main(tmp_path, *extra, probes=None, clock_check=True, rehearsal=True, calls=None):
    rg_synth.write_fresh_clock_check(tmp_path / "run", rehearsal=False)
    if rehearsal:
        rg_synth.write_fresh_rehearsal(tmp_path / "run", **(rehearsal if isinstance(rehearsal, dict) else {}))
    seen = []
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(r, "run_sweep", lambda *a, **k: seen.append(a) or "complete")
        return r.main(main_args(tmp_path, "--run-dir", str(tmp_path / "run"), "--reps", "1", *extra), probes=probes or FakeProbes(), runner=lambda *a, **k: None), seen


def test_sweep_refuses_without_rehearsal_json(tmp_path, capsys):
    code, seen = sweep_main(tmp_path, rehearsal=False)
    assert code == 2 and seen == [] and "rehearsal" in capsys.readouterr().err.lower()


def test_sweep_refuses_stale_rehearsal(tmp_path, capsys):
    code, seen = sweep_main(tmp_path, rehearsal=dict(timestamp=time.time() - 7 * 3600))
    err = capsys.readouterr().err.lower()
    assert code == 2 and seen == [] and "older" in err
    code, seen = sweep_main(tmp_path, "--max-rehearsal-age-s", str(8 * 3600), rehearsal=dict(timestamp=time.time() - 7 * 3600))
    assert code == 0 and seen


def test_sweep_refuses_when_an_arm_failed_or_is_missing(tmp_path, capsys):
    code, seen = sweep_main(tmp_path, rehearsal=dict(status="FAIL"))
    assert code == 2 and seen == [] and "FAIL" in capsys.readouterr().err
    code, seen = sweep_main(tmp_path, rehearsal=dict(arms=("UNGATED", "PRIO_IDLE", "DUTY50")))          # IGPU missing
    err = capsys.readouterr().err
    assert code == 2 and seen == [] and "IGPU" in err


def test_sweep_drop_igpu_is_exempt_from_the_igpu_rehearsal(tmp_path):
    code, seen = sweep_main(tmp_path, "--drop-igpu", "no vulkan", rehearsal=dict(arms=("UNGATED", "PRIO_IDLE", "DUTY50")))
    assert code == 0 and seen


def test_sweep_refuses_unreadable_rehearsal(tmp_path, capsys):
    rg_synth.write_fresh_clock_check(tmp_path / "run", rehearsal=False)
    (tmp_path / "run" / "rehearsal.json").write_text("{not json")
    assert r.main(main_args(tmp_path, "--run-dir", str(tmp_path / "run"), "--reps", "1"), probes=FakeProbes(), runner=lambda *a, **k: None) == 2


def test_load_rehearsal_pure(tmp_path):
    rg_synth.write_fresh_rehearsal(tmp_path, arms=("UNGATED",))
    doc, why = r.load_rehearsal(tmp_path, ("UNGATED",), 100.0)
    assert doc and why is None
    doc, why = r.load_rehearsal(tmp_path, ("UNGATED",), 100.0, now=time.time() + 1000)
    assert doc is None and "older" in why


@pytest.mark.parametrize("extra,probes", [(("--llm-alone",), dict(game=False)), (("--dry-run",), dict()), (("--smoke", "SOLO"), dict())])
def test_rehearsal_not_required_for_other_modes(tmp_path, extra, probes):
    rg_synth.write_fresh_clock_check(tmp_path / "run", rehearsal=False)
    code = r.main(main_args(tmp_path, "--run-dir", str(tmp_path / "run"), *extra), probes=FakeProbes(**probes), runner=lambda *a, **k: None)
    assert code == 0


def test_check_clocks_does_not_need_rehearsal(tmp_path):
    from test_amend import ClockProbes
    assert r.main(main_args(tmp_path, "--check-clocks", "--run-dir", str(tmp_path / "run")), probes=ClockProbes(game=False)) == 0


# ================================================================= 4. fail fast in run_sweep
class Boom:
    """Fails with the given exception at (rep, attempt, pos) keys; otherwise writes result.json."""

    def __init__(self, errors=None):
        self.errors, self.calls = errors or {}, []

    def __call__(self, arm, rep, out_dir, cfg, **kw):
        attempt = int(out_dir.parent.name[len("attempt"):])
        pos = int(out_dir.name.split("_", 1)[0])
        self.calls.append((rep, attempt, pos, arm))
        key = (rep, attempt, pos)
        for k in (key, (rep, "*", pos)):
            if k in self.errors:
                e = self.errors[k]
                raise e(arm, attempt) if callable(e) else e
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "result.json").write_text(json.dumps({"arm": arm, "rep": rep, "frame": {"p99": 20.0, "hitch_share": 0.1}}))


def run_sw(tmp_path, runner, reps=2, seed=3, **kw):
    lines = []
    order = r.make_order(seed, reps)
    try:
        res = r.run_sweep(make_cfg(tmp_path), tmp_path / "run", order, runner, seed=seed, log=lines.append, **kw)
    except Exception as e:                                          # noqa: BLE001
        return e, lines, order
    return res, lines, order


def test_cell_refused_stops_immediately_with_banner_and_failed_json(tmp_path):
    run = Boom({(0, 1, 2): c.CellRefused("IGPU cell refused: device mismatch")})
    e, lines, order = run_sw(tmp_path, run, rerun_cmd="python -m tools.realgame.run --run-dir X")
    assert isinstance(e, r.SweepStop) and e.exit_code == 4
    assert len(run.calls) == 3 and not (tmp_path / "run" / "rep0" / "attempt2").exists()
    f = json.loads((tmp_path / "run" / "rep0" / "attempt1" / f"2_{order[0][2]}" / "FAILED.json").read_text())
    assert f["reason"] == "refused" and "device mismatch" in f["error"]
    banner = "\n".join(lines)
    assert "\a" in banner and "device mismatch" in banner and f"2_{order[0][2]}" in banner and "python -m tools.realgame.run --run-dir X" in banner
    assert banner.count("\n") >= 4                                  # multi-line
    st = (tmp_path / "run" / "STATUS.txt").read_text()
    assert "device mismatch" in st and "rep 0" in st and "attempt 1" in st


def test_preflight_error_from_a_cell_is_also_a_refusal(tmp_path):
    run = Boom({(0, 1, 0): c.PreflightError(["PresentMon sha256 mismatch"])})
    e, lines, _ = run_sw(tmp_path, run)
    assert isinstance(e, r.SweepStop) and len(run.calls) == 1


def test_other_error_reruns_the_rep(tmp_path):
    run = Boom({(0, 1, 2): RuntimeError("PresentMon gap")})
    e, lines, order = run_sw(tmp_path, run)
    assert e is None or e == "complete"
    assert (tmp_path / "run" / "rep0" / "attempt2").exists()


def test_same_error_twice_in_a_row_for_same_cell_stops(tmp_path):
    run = Boom({(0, "*", 3): RuntimeError("EXEC_MODE line does not confirm backend")})
    e, lines, order = run_sw(tmp_path, run)
    assert isinstance(e, r.SweepStop) and e.exit_code == 4
    assert [x[1] for x in run.calls if x[2] == 3] == [1, 2] and not (tmp_path / "run" / "rep0" / "attempt3").exists()
    banner = "\n".join(lines)
    assert "\a" in banner and "twice" in banner.lower() and "EXEC_MODE line does not confirm" in banner


def test_same_error_twice_detected_across_invocations(tmp_path):
    run = Boom({(0, "*", 3): RuntimeError("same text")})
    run_sw(tmp_path, run, max_attempts=1)                          # budget exhausted after one attempt
    run2 = Boom({(0, "*", 3): RuntimeError("same text")})
    e, lines, _ = run_sw(tmp_path, run2, max_attempts=3)
    assert isinstance(e, r.SweepStop) and [x[1] for x in run2.calls if x[2] == 3] == [2]          # the second identical failure (attempt 2) stops at once


def test_different_errors_or_cells_do_not_trigger_the_stop(tmp_path):
    run = Boom({(0, 1, 3): RuntimeError("first"), (0, 2, 3): RuntimeError("second"), (0, 3, 2): RuntimeError("second")})
    e, lines, _ = run_sw(tmp_path, run, max_attempts=5)
    assert not isinstance(e, Exception)
    run = Boom({(0, 1, 3): RuntimeError("same"), (0, 2, 2): RuntimeError("same")})                # same text but another cell
    e, lines, _ = run_sw(tmp_path / "y", run, max_attempts=5)
    assert not isinstance(e, Exception)


def test_non_consecutive_same_error_does_not_stop(tmp_path):
    run = Boom({(0, 1, 3): RuntimeError("same"), (0, 2, 3): RuntimeError("other"), (0, 3, 3): RuntimeError("same")})
    e, lines, _ = run_sw(tmp_path, run, max_attempts=5)
    assert not isinstance(e, Exception)


def test_attempt_budget_is_per_invocation_and_numbers_continue(tmp_path):
    run = Boom({(0, 1, 0): RuntimeError("a1"), (0, 2, 0): RuntimeError("a2")})
    e, lines, _ = run_sw(tmp_path, run, max_attempts=2)
    assert isinstance(e, RuntimeError) and "attempts" in str(e) and sorted(p.name for p in (tmp_path / "run" / "rep0").iterdir()) == ["attempt1", "attempt2"]
    run2 = Boom({(0, 3, 0): RuntimeError("a3")})
    e, lines, _ = run_sw(tmp_path, run2, max_attempts=2)             # attempts 1 and 2 are on disk but do not count: attempts 3 (fails) and 4 (ok)
    assert not isinstance(e, Exception)
    assert (tmp_path / "run" / "rep0" / "attempt4").exists() and not (tmp_path / "run" / "rep0" / "attempt5").exists()
    assert r.final_attempts(tmp_path / "run", r.make_order(3, 2)) == {0: 4, 1: 1}


def test_budget_exhaustion_writes_status(tmp_path):
    run = Boom({(0, 1, 0): RuntimeError("a1"), (0, 2, 0): RuntimeError("a2")})
    run_sw(tmp_path, run, max_attempts=2)
    assert "attempts" in (tmp_path / "run" / "STATUS.txt").read_text()


def test_main_returns_4_on_sweep_stop_and_prints_the_rerun_command(tmp_path, capsys):
    rg_synth.write_fresh_clock_check(tmp_path / "run")

    def refuse(arm, rep, out_dir, cfg, **kw):
        raise c.CellRefused("device mismatch")
    argv = main_args(tmp_path, "--run-dir", str(tmp_path / "run"))
    code = r.main(argv, probes=FakeProbes(), runner=refuse)
    out = capsys.readouterr()
    assert code == 4 and "device mismatch" in out.out + out.err and "tools.realgame.run" in out.out + out.err and "--run-dir" in out.out + out.err


# ================================================================= 5. chunking, progress, STATUS
def test_stop_after_reps_exits_cleanly_and_resumes(tmp_path):
    run = Boom()
    res, lines, order = run_sw(tmp_path, run, reps=3, stop_after_reps=1)
    assert res == "chunk" and len(run.calls) == 6
    assert any("1 rep(s) done, rerun the same command to continue" in ln for ln in lines)
    assert "1 rep(s) done" in (tmp_path / "run" / "STATUS.txt").read_text()
    run2 = Boom()
    res, lines, _ = run_sw(tmp_path, run2, reps=3, stop_after_reps=1)           # reps already on disk do not count
    assert res == "chunk" and {x[0] for x in run2.calls} == {1}
    run3 = Boom()
    res, lines, _ = run_sw(tmp_path, run3, reps=3, stop_after_reps=2)
    assert res == "complete" and {x[0] for x in run3.calls} == {2}


def test_stop_after_reps_zero_means_no_limit_and_cli_flag(tmp_path):
    res, _, _ = run_sw(tmp_path, Boom(), reps=2, stop_after_reps=0)
    assert res == "complete"
    seen = {}
    import tools.realgame.run as rr
    rg_synth.write_fresh_clock_check(tmp_path / "z")
    orig = rr.run_sweep
    rr.run_sweep = lambda *a, **k: seen.update(k)
    try:
        assert r.main(main_args(tmp_path, "--run-dir", str(tmp_path / "z"), "--stop-after-reps", "2"), probes=FakeProbes(), runner=lambda *a, **k: None) == 0
    finally:
        rr.run_sweep = orig
    assert seen["stop_after_reps"] == 2 and "tools.realgame.run" in seen["rerun_cmd"]


def test_main_exit_code_zero_on_chunk(tmp_path, capsys):
    rg_synth.write_fresh_clock_check(tmp_path / "run")
    code = r.main(main_args(tmp_path, "--run-dir", str(tmp_path / "run"), "--reps", "2", "--stop-after-reps", "1"), probes=FakeProbes(), runner=Boom())
    assert code == 0 and "1 rep(s) done, rerun the same command to continue" in capsys.readouterr().out


def test_progress_line_per_cell_with_elapsed_and_remaining(tmp_path):
    t = {"now": 100.0}

    def clk():
        return t["now"]

    class Slow(Boom):
        def __call__(self, *a, **k):
            t["now"] += 60.0
            return super().__call__(*a, **k)
    res, lines, order = run_sw(tmp_path, Slow(), reps=1, clock=clk)
    prog = [ln for ln in lines if ln.startswith("progress")]
    assert len(prog) == 6
    assert "cell 1/6" in prog[0] and "elapsed 00:01:00" in prog[0] and "remaining" in prog[0] and "00:05:00" in prog[0]          # 60 s mean x 5 cells left
    assert "cell 6/6" in prog[5] and "00:00:00" in prog[5]


def test_status_file_after_every_cell(tmp_path):
    snaps = []

    class Spy(Boom):
        def __call__(self, arm, rep, out_dir, cfg, **kw):
            p = tmp_path / "run" / "STATUS.txt"
            snaps.append(p.read_text() if p.exists() else None)
            return super().__call__(arm, rep, out_dir, cfg, **kw)
    res, lines, order = run_sw(tmp_path, Spy(), reps=1)
    assert snaps[0] is None and "last completed cell: rep0/attempt1/0_SOLO" in snaps[1] and "rep 0" in snaps[1] and "UTC" in snaps[1]
    final = (tmp_path / "run" / "STATUS.txt").read_text()
    assert "complete" in final.lower() and "5_SOLO" in final and re.search(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", final)


def test_status_records_error_text_on_failure(tmp_path):
    run = Boom({(0, "*", 1): RuntimeError("weird failure text")})
    run_sw(tmp_path, run)
    st = (tmp_path / "run" / "STATUS.txt").read_text()
    assert "weird failure text" in st


def test_completion_banner_and_bell(tmp_path):
    res, lines, _ = run_sw(tmp_path, Boom(), reps=1)
    assert res == "complete"
    tail = "\n".join(lines[-6:])
    assert "\a" in tail and "SWEEP COMPLETE" in tail


def test_keyboard_interrupt_writes_status_and_propagates(tmp_path):
    class Intr(Boom):
        def __call__(self, *a, **k):
            if len(self.calls) == 2:
                raise KeyboardInterrupt
            return super().__call__(*a, **k)
    with pytest.raises(KeyboardInterrupt):
        r.run_sweep(make_cfg(tmp_path), tmp_path / "run", r.make_order(3, 1), Intr(), seed=3, log=lambda *a: None)
    assert "interrupt" in (tmp_path / "run" / "STATUS.txt").read_text().lower()


# ================================================================= 2b. CLI
def test_cli_device_match_default_and_option(tmp_path):
    seen = {}
    import tools.realgame.run as rr
    rg_synth.write_fresh_clock_check(tmp_path / "z")
    orig = rr.run_sweep
    rr.run_sweep = lambda cfg, *a, **k: seen.update(cfg=cfg)
    try:
        assert r.main(main_args(tmp_path, "--run-dir", str(tmp_path / "z")), probes=FakeProbes(), runner=lambda *a, **k: None) == 0
        assert seen["cfg"].igpu_device_match == "780M" and seen["cfg"].igpu_vk_index is None
        assert r.main(main_args(tmp_path, "--run-dir", str(tmp_path / "z"), "--igpu-device-match", "Radeon", "--igpu-vk-index", "3"), probes=FakeProbes(), runner=lambda *a, **k: None) == 0
        assert seen["cfg"].igpu_device_match == "Radeon" and seen["cfg"].igpu_vk_index is None
    finally:
        rr.run_sweep = orig


def test_vk_index_deprecation_is_one_line(tmp_path, capsys):
    r.main(main_args(tmp_path, "--dry-run", "--igpu-vk-index", "1"), probes=FakeProbes())
    err = [ln for ln in capsys.readouterr().err.splitlines() if "igpu-vk-index" in ln]
    assert len(err) == 1 and "deprecated" in err[0].lower()
