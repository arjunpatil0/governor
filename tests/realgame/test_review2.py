"""Second-review defects A to M (one or more tests per item)."""
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

import rg_synth
from test_cell import Clock, FakeCapture, FakeLlm, FakeNvml, FakeProbes, FakeSampler, SAMPLE_HEADER, exec_line, make_cfg, make_deps
from tools.realgame import analyze as a
from tools.realgame import cell as c
from tools.realgame import decision as d
from tools.realgame import metrics, presentmon
from tools.realgame import run as r
from tools.realgame.gpu_priority import PriorityError

ROOT = Path(__file__).resolve().parents[2]
BASE_ARGS = ["--armoury-mode", "Turbo", "--llm-exe", "a", "--model", "b", "--prompt", "c", "--presentmon", "d", "--game-process", "g.exe", "--n-prompt", "64"]


def main_args(tmp_path, *extra):
    return [*extra, *BASE_ARGS, "--llama-dir", str(tmp_path / "llama.cpp"), "--repo-root", str(tmp_path)]


def run_ok(tmp_path, arm="UNGATED", deps_kw=None, cfg_kw=None, out="cell", rep=0):
    clock = Clock()
    cfg = make_cfg(tmp_path, **(cfg_kw or {}))
    dp, box = make_deps(cfg, clock, **(deps_kw or {}))
    res = c.run_cell(arm, rep, tmp_path / out, cfg, dp)
    return res, dp, box, clock, cfg


# ================================================================= A. LLM_ALONE in its own invocation
def test_a_preflight_llm_alone_refuses_when_game_running(tmp_path):
    with pytest.raises(c.PreflightError, match="(?i)absent"):
        c.preflight(make_cfg(tmp_path), FakeProbes(game=True), need_game=False, game_absent=True)
    assert c.preflight(make_cfg(tmp_path), FakeProbes(game=False), need_game=False, game_absent=True) is None


def test_a_run_cell_llm_alone_records_game_absent_and_refuses_with_game(tmp_path):
    clock = Clock()
    cfg = make_cfg(tmp_path)
    dp, _ = make_deps(cfg, clock)
    dp.probes = FakeProbes(game=False)
    res = c.run_cell("LLM_ALONE", 0, tmp_path / "alone", cfg, dp)
    assert res["game_absent"] is True and json.loads((tmp_path / "alone" / "result.json").read_text())["game_absent"] is True
    dp.probes = FakeProbes(game=True)
    with pytest.raises(RuntimeError, match="(?i)absent"):
        c.run_cell("LLM_ALONE", 0, tmp_path / "alone2", cfg, dp)
    assert not (tmp_path / "alone2" / "result.json").exists()


def test_a_main_llm_alone_mode_runs_only_llm_alone(tmp_path):
    calls = []
    runner = lambda arm, rep, out, cfg: (calls.append((arm, Path(out))), Path(out).mkdir(parents=True, exist_ok=True), (Path(out) / "result.json").write_text("{}"))[0]
    code = r.main(main_args(tmp_path, "--llm-alone", "--run-dir", str(tmp_path / "run")), probes=FakeProbes(game=False), runner=runner)
    assert code == 0 and calls == [("LLM_ALONE", tmp_path / "run" / "llm_alone")]


def test_a_main_llm_alone_mode_refuses_with_game_present(tmp_path, capsys):
    calls = []
    code = r.main(main_args(tmp_path, "--llm-alone", "--run-dir", str(tmp_path / "run")), probes=FakeProbes(game=True), runner=lambda *x: calls.append(x))
    assert code == 2 and calls == [] and "absent" in capsys.readouterr().err.lower()


def test_a_analyze_refuses_without_llm_alone_reference(tmp_path):
    root = tmp_path / "run"
    rg_synth.build_tree(root)
    (root / "llm_alone" / "result.json").unlink()
    with pytest.raises(ValueError, match="LLM_ALONE"):
        a.run_analysis(root, tmp_path / "o", plots=False)


def test_a_analyze_refuses_llm_alone_not_run_with_game_absent(tmp_path):
    root = tmp_path / "run"
    rg_synth.build_tree(root)
    p = root / "llm_alone" / "result.json"
    j = json.loads(p.read_text())
    j.pop("game_absent")
    p.write_text(json.dumps(j))
    with pytest.raises(ValueError, match="game_absent"):
        a.run_analysis(root, tmp_path / "o", plots=False)


# ================================================================= B. IGPU
def test_b_igpu_uses_vk_exe_and_vulkan_device_env(tmp_path, monkeypatch):
    monkeypatch.setenv("GGML_VK_VISIBLE_DEVICES", "9")
    seen = []
    clock = Clock()
    cfg = make_cfg(tmp_path, igpu_vk_index=2)
    dp, _ = make_deps(cfg, clock)
    dp.spawn_llm = lambda cmd, env, p: (seen.append((cmd, dict(env))), FakeLlm(clock, p, exec_line(env)))[1]
    c.run_cell("IGPU", 0, tmp_path / "i", cfg, dp)
    c.run_cell("UNGATED", 0, tmp_path / "u", cfg, dp)
    assert seen[0][0][0] == str(cfg.llm_exe_vk) and seen[0][1]["GGML_VK_VISIBLE_DEVICES"] == "2"
    assert seen[1][0][0] == str(cfg.llm_exe) and "GGML_VK_VISIBLE_DEVICES" not in seen[1][1]       # never leaks into the other arms


def test_b_igpu_needs_index_and_vk_exe(tmp_path):
    for kw in (dict(igpu_vk_index=None), dict(llm_exe_vk=None)):
        with pytest.raises(RuntimeError, match="(?i)igpu"):
            run_ok(tmp_path, "IGPU", cfg_kw=kw, out="x" + str(len(kw)))


@pytest.mark.parametrize("device,ok", [("AMD Radeon(TM) 780M Graphics", True), ("Radeon something", True), ("AMD 780M", True), ("NVIDIA GeForce RTX 4060 Laptop GPU", False)])
def test_b_igpu_refused_unless_device_is_780m_or_radeon(tmp_path, device, ok):
    clock = Clock()
    cfg = make_cfg(tmp_path)
    dp, _ = make_deps(cfg, clock)
    dp.spawn_llm = lambda cmd, env, p: FakeLlm(clock, p, f"EXEC_MODE vulkan device={device} offloaded=29/29 n_layer=28 duty=0")
    if ok:
        c.run_cell("IGPU", 0, tmp_path / "i", cfg, dp)
    else:
        with pytest.raises(RuntimeError, match="780M"):
            c.run_cell("IGPU", 0, tmp_path / "i", cfg, dp)
        assert not (tmp_path / "i" / "result.json").exists()


def test_b_vk_exe_hashed_into_meta(tmp_path):
    run_ok(tmp_path, "IGPU", out="i")
    meta = json.loads((tmp_path / "i" / "meta.json").read_text())
    assert meta["llm_exe_vk_sha256"] == "sha-llm_vk.exe"


def test_b_main_requires_igpu_vk_index_unless_igpu_dropped(tmp_path, capsys):
    argv = [*BASE_ARGS, "--dry-run", "--llama-dir", str(tmp_path / "llama.cpp"), "--repo-root", str(tmp_path)]
    try:
        code = r.main(argv, probes=FakeProbes())
    except SystemExit as e:
        code = e.code
    assert code not in (0, None) and "igpu-vk-index" in capsys.readouterr().err
    assert r.main([*argv, "--drop-igpu", "build failed"], probes=FakeProbes()) == 0
    assert r.main([*argv, "--igpu-vk-index", "1"], probes=FakeProbes()) == 0


# ================================================================= C. window start
class RecLlm(FakeLlm):
    def send(self, text):
        self.sent_at = self.clock.now()
        super().send(text)


def test_c_pdh_during_warmup_energy_at_t_open_go_at_warmup_start(tmp_path):
    clock = Clock()
    cfg = make_cfg(tmp_path)
    log = []
    dp, box = make_deps(cfg, clock, llm=RecLlm(clock, str(tmp_path / "cell" / "llm"), exec_line({"RG_BACKEND": "cuda", "RG_DUTY": "0"})))
    (tmp_path / "cell").mkdir()
    dp.shared_mem = lambda pid: (log.append(("pdh", clock.now())), 5)[1]
    nv = FakeNvml(clock)
    dp.nvml = type("N", (), {"energy_mj": lambda s: (log.append(("energy", clock.now(), len([x for x in log if x[0] == "pdh"]))), nv.energy_mj())[1],
                             "temp_c": lambda s: 61.0, "vram_used_mb": lambda s: 1.0})()
    t_start = clock.now()
    res = c.run_cell("UNGATED", 0, tmp_path / "cell", cfg, dp)
    pdh = [x for x in log if x[0] == "pdh"]
    en = [x for x in log if x[0] == "energy"]
    assert pdh[0][1] < res["t_open"] and en[0][2] == 1               # PDH start reading taken before the window opens, none between warm-up and the first energy read
    assert en[0][1] == pytest.approx(res["t_open"], abs=1e-3) and en[1][1] == pytest.approx(res["t_close"], abs=1e-3)      # energy window is [t_open, t_close)
    assert pdh[1][1] >= res["t_close"] - 1e-3                        # end reading after the window
    assert box["l"].sent_at == pytest.approx(res["t_open"] - cfg.warmup_s, abs=1e-3) and box["l"].sent_at >= t_start        # GO at the START of the warm-up
    assert float(box["l"].sent[0].split()[1]) == pytest.approx(res["t_close"])
    assert res["power_w"] == pytest.approx(90.0, rel=1e-3)


def test_c_pdh_overrunning_warmup_fails_the_cell(tmp_path):
    clock = Clock()
    cfg = make_cfg(tmp_path)
    dp, _ = make_deps(cfg, clock)
    dp.shared_mem = lambda pid: (clock.sleep(cfg.warmup_s + 1), 5)[1]
    with pytest.raises(RuntimeError, match="(?i)warm-up"):
        c.run_cell("UNGATED", 0, tmp_path / "x", cfg, dp)


def test_c_rg_nctx_default_16384_but_env_respected(tmp_path, monkeypatch):
    seen = []
    clock = Clock()
    cfg = make_cfg(tmp_path)
    dp, _ = make_deps(cfg, clock)
    dp.spawn_llm = lambda cmd, env, p: (seen.append(env.get("RG_NCTX")), FakeLlm(clock, p, exec_line(env)))[1]
    monkeypatch.delenv("RG_NCTX", raising=False)
    c.run_cell("UNGATED", 0, tmp_path / "a", cfg, dp)
    monkeypatch.setenv("RG_NCTX", "4096")
    c.run_cell("UNGATED", 0, tmp_path / "b", cfg, dp)
    assert seen == ["16384", "4096"]


class ResetLlm(FakeLlm):
    def __init__(self, *a, offset=-3.0, **k):
        super().__init__(*a, **k)
        self.offset = offset

    def send(self, text):
        super().send(text)
        t_stop = float(text.split()[1])
        with open(str(self.prefix) + "_tokens.csv", "a") as f:
            f.write(f"{t_stop + self.offset:.6f},50.0,reset\n")


def test_c_reset_row_inside_window_fails_the_cell(tmp_path):
    clock = Clock()
    cfg = make_cfg(tmp_path)
    dp, _ = make_deps(cfg, clock, llm=ResetLlm(clock, str(tmp_path / "x" / "llm"), exec_line({"RG_BACKEND": "cuda", "RG_DUTY": "0"})))
    (tmp_path / "x").mkdir()
    with pytest.raises(RuntimeError, match="reset"):
        c.run_cell("UNGATED", 0, tmp_path / "x", cfg, dp)
    assert not (tmp_path / "x" / "result.json").exists()


def test_c_reset_row_before_window_is_fine(tmp_path):
    clock = Clock()
    cfg = make_cfg(tmp_path)
    dp, _ = make_deps(cfg, clock, llm=ResetLlm(clock, str(tmp_path / "x" / "llm"), exec_line({"RG_BACKEND": "cuda", "RG_DUTY": "0"}), offset=-7.5))
    (tmp_path / "x").mkdir()
    assert c.run_cell("UNGATED", 0, tmp_path / "x", cfg, dp)["n_tokens"] > 0


def test_c_count_resets_overlap_semantics(tmp_path):
    p = tmp_path / "t.csv"
    p.write_text("t_tok_end_s,dur_ms,kind\n1.0,1.0,token\n5.0,50.0,reset\n")
    assert metrics.count_resets(p, 4.0, 6.0) == 1
    assert metrics.count_resets(p, 5.1, 6.0) == 0
    assert metrics.count_resets(p, 4.0, 4.9) == 0
    assert metrics.count_resets(p, 4.96, 6.0) == 1            # the reset ran 4.95 to 5.0 and overlaps the window


# ================================================================= D. PresentMon gap detection and the QPC assertion
HZ = 1e7


def frames_at(starts, ms=16.67):
    return [presentmon.Frame(s * HZ, ms, 8.0, 1.0, True, "0xA", "Flip") for s in starts]


def regular(t_open=100.0, n=3600, step=1 / 60.0, first=0.0):
    return [t_open + first + i * step for i in range(n)]


def check(starts, ms=16.67, t_open=100.0, t_close=160.0):
    return presentmon.check_window_continuity(frames_at(starts, ms), t_open, t_close, HZ)


def test_d_good_window_passes():
    assert check(regular()) is None


def test_d_first_frame_late_by_more_than_0_1s_fails():
    with pytest.raises(presentmon.PresentMonError, match="first"):
        check(regular(first=0.11, n=3590))
    assert check(regular(first=0.09, n=3590)) is None


def test_d_last_frame_ending_early_fails():
    s = regular(n=3560)                                          # last frame starts at 159.31 s, ends 159.33 s: 0.67 s early
    with pytest.raises(presentmon.PresentMonError, match="last"):
        check(s)


def test_d_gap_between_frame_starts_above_0_5s_fails():
    s = regular()
    s = s[:1000] + [x + 0.51 for x in s[1000:3580]]
    with pytest.raises(presentmon.PresentMonError, match="gap"):
        check(s)
    s = regular()
    s = s[:1000] + [x + 0.48 for x in s[1000:3580]]
    assert check(s) is None


def test_d_frame_count_below_95_percent_fails():
    s = regular(n=3600)[::2]                                     # 30 fps: gaps are small, edges fine, count 1800
    with pytest.raises(presentmon.PresentMonError, match="count"):
        check(s)
    s = [x for i, x in enumerate(regular()) if i % 20 != 0]       # 95.0 % of 3600 = 3420 exactly passes
    assert len(s) == 3420 and check(s) is None
    s = [x for i, x in enumerate(regular()) if i % 20 != 0 and i != 1]
    with pytest.raises(presentmon.PresentMonError, match="count"):
        check(s)


class GapCapture(FakeCapture):
    def stop(self, timeout=10.0):
        super().stop(timeout)
        lines = Path(self.out_csv).read_text().splitlines()
        keep = [lines[0]] + [x for x in lines[1:] if not (1004.0 * 1e7 <= int(x.split(",")[9]) < 1004.8 * 1e7)]
        Path(self.out_csv).write_text("\n".join(keep) + "\n")


def test_d_run_cell_fails_on_presentmon_gap(tmp_path):
    clock = Clock()
    cfg = make_cfg(tmp_path)
    dp, box = make_deps(cfg, clock)
    dp.make_capture = lambda cfg_, out_csv, session: GapCapture(clock, out_csv)
    with pytest.raises(presentmon.PresentMonError, match="gap"):
        c.run_cell("UNGATED", 0, tmp_path / "x", cfg, dp)
    assert not (tmp_path / "x" / "result.json").exists() and box["l"].killed


def test_d_qpc_assertion_at_cell_start(tmp_path):
    clock = Clock()
    cfg = make_cfg(tmp_path)
    dp, _ = make_deps(cfg, clock)
    dp.qpc_counter = lambda: int((clock.now() + 0.005) * 1e7)
    with pytest.raises(RuntimeError, match="QueryPerformanceCounter"):
        c.run_cell("SOLO", 0, tmp_path / "x", cfg, dp)
    assert not (tmp_path / "x" / "meta.json").exists()          # fails before anything else happens
    dp.qpc_counter = lambda: int((clock.now() + 0.0005) * 1e7)
    assert c.run_cell("SOLO", 0, tmp_path / "y", cfg, dp)["arm"] == "SOLO"


@pytest.mark.skipif(sys.platform != "win32", reason="QueryPerformanceCounter")
def test_d_real_qpc_matches_perf_counter():
    assert abs(time.perf_counter() - c.query_qpc_counter() / c.query_qpc_hz()) < 0.001


# ================================================================= E. PRIO_IDLE end read-back
def test_e_priority_error_on_end_readback_fails_the_cell(tmp_path):
    clock = Clock()
    cfg = make_cfg(tmp_path)

    def bad_get(pid):
        raise PriorityError("get failed", set_status=None, readback=None)
    dp, box = make_deps(cfg, clock, get_prio=bad_get)
    with pytest.raises(PriorityError):
        c.run_cell("PRIO_IDLE", 0, tmp_path / "p", cfg, dp)
    assert box["l"].killed and not (tmp_path / "p" / "result.json").exists()


def test_e_successful_wrong_class_at_end_voids_only(tmp_path):
    res, *_ = run_ok(tmp_path, "PRIO_IDLE", deps_kw=dict(get_prio=lambda pid: 2))
    assert res["prio_valid"] is False and res["prio_readbacks"] == [0, 2]


# ================================================================= F. PRIO_IDLE read-backs from every attempt
def test_f_discarded_attempt_readbacks_void_prio_idle(tmp_path):
    root = tmp_path / "run"
    order = rg_synth.build_tree(root, prio_readbacks=(0, 0))
    pos = order[0].index("PRIO_IDLE")
    rg_synth.write_cell(r.cell_dir(root, 0, 1, pos, "PRIO_IDLE"), "PRIO_IDLE", 0, 5, 7000.0, prio_readbacks=[0, 2])       # in the discarded attempt 1 of rep 0
    s = a.run_analysis(root, tmp_path / "o", plots=False)
    assert s["decision"]["prio_idle_valid"] is False
    assert all(c_["attempt"] == 2 for c_ in s["cells"] if c_["rep"] == 0)


def test_f_collects_every_attempt(tmp_path):
    root = tmp_path / "run"
    order = rg_synth.build_tree(root, prio_readbacks=(0, 0))
    pos = order[0].index("PRIO_IDLE")
    rg_synth.write_cell(r.cell_dir(root, 0, 1, pos, "PRIO_IDLE"), "PRIO_IDLE", 0, 5, 7000.0, prio_readbacks=[0, 0, 0])
    got = a.collect_prio_readbacks(root, order)
    assert len(got) == 3 * 2 + 3 and set(got) == {0}


# ================================================================= G. unfinished attempt on resume
def test_g_unfinished_attempt_is_failed_and_new_attempt_starts(tmp_path):
    from test_run import Runner, sweep
    first = Runner(interrupt_at=3)
    with pytest.raises(KeyboardInterrupt):
        sweep(tmp_path, first)
    second = Runner()
    order = sweep(tmp_path, second)
    a1 = tmp_path / "run" / "rep0" / "attempt1"
    assert list(a1.rglob("FAILED.json")) and "interrupted" in next(a1.rglob("FAILED.json")).read_text()
    assert (tmp_path / "run" / "rep0" / "attempt2" / f"0_SOLO" / "result.json").exists()
    assert second.calls[0][2:] == ("attempt2", "0_SOLO")            # never continues the partial attempt
    assert r.final_attempts(tmp_path / "run", order) == {0: 2, 1: 1}
    assert r.failed_attempts(tmp_path / "run", order)[0] == [1]


def test_g_interrupted_attempts_count_against_max_attempts(tmp_path):
    from test_run import Runner, sweep
    with pytest.raises(KeyboardInterrupt):
        sweep(tmp_path, Runner(interrupt_at=2))
    with pytest.raises(RuntimeError, match="attempts"):
        sweep(tmp_path, Runner(), max_attempts=1)


# ================================================================= H. security
class BadPm(FakeProbes):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.version_calls = 0

    def sha256(self, path):
        return "0" * 64 if Path(path).name in ("pm.exe", "d") else super().sha256(path)

    def presentmon_version(self, exe):
        self.version_calls += 1
        return "PresentMon 2.6.0"


def test_h_preflight_refuses_presentmon_hash_mismatch(tmp_path):
    with pytest.raises(c.PreflightError, match="(?i)presentmon.*sha256|sha256.*presentmon"):
        c.preflight(make_cfg(tmp_path), BadPm())
    assert c.preflight(make_cfg(tmp_path, allow_pm_hash_mismatch=True), BadPm()) is None


def test_h_build_meta_checks_hash_before_any_presentmon_execution(tmp_path):
    p = BadPm()
    with pytest.raises(c.PreflightError):
        c.build_meta(make_cfg(tmp_path), p)
    assert p.version_calls == 0
    m = c.build_meta(make_cfg(tmp_path, allow_pm_hash_mismatch=True), p)
    assert p.version_calls == 1 and m["allow_pm_hash_mismatch"] is True and m["presentmon_sha256_matches_prereg"] is False
    assert c.build_meta(make_cfg(tmp_path), FakeProbes())["allow_pm_hash_mismatch"] is False


def test_h_main_flag_and_prints_driver_hashes(tmp_path, capsys):
    argv = main_args(tmp_path, "--dry-run", "--igpu-vk-index", "1")
    assert r.main(argv, probes=BadPm()) == 2
    assert r.main([*argv, "--allow-pm-hash-mismatch"], probes=BadPm()) == 0
    out = capsys.readouterr().out
    assert "sha256" in out and "sha-a" in out and "sha-llama_realgame_bench_vk.exe" in out


def test_h_tool_paths_resolved_to_full_paths(monkeypatch, tmp_path):
    monkeypatch.setenv("SystemRoot", str(tmp_path / "win"))
    monkeypatch.setattr(shutil, "which", lambda name, *a, **k: str(tmp_path / "bin" / "git.exe") if name == "git" else None)
    c._TOOLS.clear()
    t = c.tool_paths()
    assert Path(t["git"]) == tmp_path / "bin" / "git.exe"
    assert Path(t["tasklist"]) == tmp_path / "win" / "System32" / "tasklist.exe"
    assert Path(t["typeperf"]) == tmp_path / "win" / "System32" / "typeperf.exe"
    c._TOOLS.clear()


def test_h_git_found_in_cwd_is_refused(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda name, *a, **k: str(Path.cwd() / "git.exe"))
    c._TOOLS.clear()
    with pytest.raises(RuntimeError, match="(?i)cwd|current"):
        c.tool_paths()
    c._TOOLS.clear()


def test_h_subprocess_calls_use_full_paths(monkeypatch, tmp_path):
    monkeypatch.setenv("SystemRoot", str(tmp_path / "win"))
    monkeypatch.setattr(shutil, "which", lambda name, *a, **k: str(tmp_path / "bin" / "git.exe"))
    c._TOOLS.clear()
    argv = []

    class R:
        returncode, stdout, stderr = 0, "", ""
    monkeypatch.setattr(c.subprocess, "run", lambda cmd, *a, **k: (argv.append(list(cmd)), R())[1])
    monkeypatch.setitem(sys.modules, "psutil", None)               # force the tasklist path
    c._git(tmp_path, "status")
    c._process_table()
    c.read_shared_gpu_mem(12)
    assert [Path(x[0]).name for x in argv] == ["git.exe", "tasklist.exe", "typeperf.exe"]
    assert all(Path(x[0]).is_absolute() for x in argv)
    c._TOOLS.clear()


def test_h_presentmon_csv_size_cap(tmp_path, monkeypatch):
    p = tmp_path / "f.csv"
    p.write_text(SAMPLE_HEADER + "\n")
    assert presentmon.MAX_CSV_BYTES == 500 * 1024 * 1024
    monkeypatch.setattr(presentmon, "MAX_CSV_BYTES", 10)
    with pytest.raises(presentmon.PresentMonError, match="(?i)size|large"):
        presentmon.parse_csv(p)


def test_h_csv_error_wrapped_as_presentmon_error():
    text = SAMPLE_HEADER + "\n" + "x" * 200_000 + ",1\n"
    with pytest.raises(presentmon.PresentMonError, match="(?i)csv"):
        presentmon.parse_csv(text)


@pytest.mark.parametrize("name,ok", [("game.exe", True), ("GAME.EXE", True), ("game", False), ("-x.exe", False), ("game.exe ", False), ("", False)])
def test_h_game_process_validation(name, ok):
    if ok:
        assert c.validate_game_process(name) == name
    else:
        with pytest.raises(ValueError):
            c.validate_game_process(name)


def test_h_main_rejects_bad_game_process(tmp_path, capsys):
    argv = [x for x in main_args(tmp_path, "--dry-run", "--igpu-vk-index", "1") if x != "g.exe"]; argv = [("--game-process=-evil.exe" if x == "--game-process" else x) for x in argv]
    assert r.main(argv, probes=FakeProbes()) == 2
    assert "game-process" in capsys.readouterr().err


def test_h_unique_session_name_per_cell(tmp_path):
    order = []
    clock = Clock()
    cfg = make_cfg(tmp_path)
    dp, _ = make_deps(cfg, clock, order=order)
    c.run_cell("UNGATED", 0, tmp_path / "a", cfg, dp)
    c.run_cell("UNGATED", 0, tmp_path / "b", cfg, dp)
    s = [o[1] for o in order if o[0] == "capture"]
    assert len(s) == 2 and s[0] != s[1] and all(x.startswith("R1_UNGATED_0_") and len(x) > len("R1_UNGATED_0_") for x in s)


def test_h_elevation_in_meta_and_note_without_refusal(tmp_path, capsys):
    class Admin(FakeProbes):
        def is_elevated(self):
            return True
    assert c.preflight(make_cfg(tmp_path), Admin()) is None
    assert "elevated" in capsys.readouterr().out.lower()
    assert c.build_meta(make_cfg(tmp_path), Admin())["elevated"] is True
    assert c.build_meta(make_cfg(tmp_path), FakeProbes())["elevated"] is False


# ================================================================= I. DUTY50
def test_i_duty_achieved_parsed_into_result(tmp_path):
    res, *_ = run_ok(tmp_path, "DUTY50")
    assert res["duty_achieved"] == pytest.approx(0.49)
    assert json.loads((tmp_path / "cell" / "result.json").read_text())["duty_achieved"] == pytest.approx(0.49)
    assert run_ok(tmp_path, "UNGATED", out="u")[0]["duty_achieved"] is None


def test_i_missing_duty_line_fails_the_duty_cell(tmp_path):
    clock = Clock()
    cfg = make_cfg(tmp_path)
    dp, _ = make_deps(cfg, clock)

    class NoDuty(FakeLlm):
        def wait_for(self, prefix, timeout):
            if prefix == "DUTY_ACHIEVED":
                raise TimeoutError("no DUTY_ACHIEVED")
            return super().wait_for(prefix, timeout)
    dp.spawn_llm = lambda cmd, env, p: NoDuty(clock, p, exec_line(env))
    with pytest.raises(TimeoutError):
        c.run_cell("DUTY50", 0, tmp_path / "x", cfg, dp)


def test_i_driver_source_uses_high_resolution_waitable_timer():
    src = (ROOT / "workloads" / "background" / "llama_realgame_bench.cpp").read_text()
    assert "CreateWaitableTimerExW" in src and "CREATE_WAITABLE_TIMER_HIGH_RESOLUTION" in src and "Sleep(1)" in src    # Sleep(1) stays as the fallback
    assert "timeBeginPeriod" not in src.replace("no timeBeginPeriod", "")
    assert "16384" in src


# ================================================================= J. paging: exact PDH instance, end-of-window reading
TP = ('"(PDH-CSV 4.0)","\\\\H\\GPU Process Memory(pid_12_luid_0x0_0x1_phys_0)\\Shared Usage","\\\\H\\GPU Process Memory(pid_123_luid_0x0_0x1_phys_0)\\Shared Usage",'
      '"\\\\H\\GPU Process Memory(pid_12_luid_0x0_0x2_phys_0)\\Shared Usage"\n"01/01/2026 00:00:00.000","100","7000","20"\n')


def test_j_exact_pdh_instance_not_prefix(monkeypatch):
    class R:
        returncode, stdout = 0, TP
    seen = []
    monkeypatch.setattr(c.subprocess, "run", lambda cmd, *a, **k: (seen.append(cmd), R())[1])
    assert c.read_shared_gpu_mem(12) == 120                              # pid_12_ columns only; pid_123_ excluded
    assert "pid_12_*" in seen[0][1] and "pid_12*)" not in seen[0][1]
    assert c.read_shared_gpu_mem(123) == 7000
    assert c.read_shared_gpu_mem(1) == "unavailable"                     # no column of pid_1_


def test_j_paging_uses_end_of_window_reading():
    cells = [{"rep": 0, "pos": 0, "arm": "SOLO", "shared_gpu_mem_bytes": {"start": 0, "end": 10 * 2**20}},
             {"rep": 0, "pos": 1, "arm": "UNGATED", "shared_gpu_mem_bytes": {"start": 500 * 2**20, "end": 12 * 2**20}},
             {"rep": 0, "pos": 2, "arm": "IGPU", "shared_gpu_mem_bytes": {"start": 0, "end": 100 * 2**20}}]
    assert [x["arm"] for x in a._flags(cells)["paging"]] == ["IGPU"]
    assert "end-of-window" in (a._flags.__doc__ or "")


# ================================================================= K. rest before every cell but the first
def test_k_rest_between_every_pair_of_consecutive_cells(tmp_path):
    from test_run import Runner, sweep
    rests, temps = [], iter(range(50, 200))

    def rest(read_temp, start_temp):
        rests.append(start_temp)
        return {"rest_s": 30.0, "reached": True, "start_temp": start_temp, "final_temp": 50.0}
    sweep(tmp_path, Runner(), reps=3, read_temp=lambda: float(next(temps)), rest=rest)
    log = [json.loads(x) for x in (tmp_path / "run" / "rest_log.jsonl").read_text().splitlines()]
    assert len(rests) == len(log) == 3 * 6 - 1
    befores = [(e["rep"], e["before"]) for e in log]
    assert (0, "0_SOLO") not in befores and (1, "0_SOLO") in befores and (2, "0_SOLO") in befores
    assert [e["before"] for e in log][:5] == [f"{i}_{x}" for i, x in enumerate(r.make_order(3, 3)[0]) if i > 0]


# ================================================================= L. UNGATED token gaps
def tok_csv(tmp_path, times, name="t.csv"):
    p = tmp_path / name
    p.write_text("t_tok_end_s,dur_ms,kind\n" + "".join(f"{t:.4f},10.0,token\n" for t in times))
    return p


def test_l_max_token_gap_inside_window(tmp_path):
    p = tok_csv(tmp_path, [0.5, 1.0, 2.5, 3.0, 9.9])
    assert metrics.max_token_gap(p, 0.0, 10.0) == pytest.approx(6.9)
    assert metrics.max_token_gap(tok_csv(tmp_path, [0.5], "o.csv"), 0.0, 10.0) == pytest.approx(10.0)     # <2 tokens: no evidence of tokens throughout


def test_l_ungated_with_a_token_gap_over_1s_is_void(tmp_path):
    from test_decision import REPS, arm, arms, run, GOOD, GOOD_TOKENS
    base = arm(**GOOD, toks=50.0)
    ok = arm(**GOOD, toks=60.0)
    assert run(arms(ok, base, base))["branch"] == "NO_PROBLEM"
    gap = tok_csv(tmp_path, [i * 0.01 for i in range(1, 300)] + [4.9 + i * 0.01 for i in range(0, 510)])        # 1.95 s hole
    ok[2] = dict(ok[2], tokens_csv=gap)
    ev = run(arms(ok, base, base))
    assert ev["branch"] == "VOID" and ev["ungated_valid"] is False and "gap" in " ".join(ev["reasons"])


def test_l_gap_of_exactly_1s_is_allowed_and_csv_is_required(tmp_path):
    from test_decision import arm, arms, run, GOOD
    base = arm(**GOOD, toks=50.0)
    ok = arm(**GOOD, toks=60.0)
    edge = tok_csv(tmp_path, [0.5 + i * 0.01 for i in range(0, 200)] + [3.49 + i * 0.01 for i in range(0, 400)])
    ok[0] = dict(ok[0], tokens_csv=edge, t_open=0.5, t_close=8.0)
    assert run(arms(ok, base, base))["ungated_valid"] is True
    missing = arm(**GOOD, toks=60.0)
    missing[1] = {k: v for k, v in missing[1].items() if k != "tokens_csv"}
    with pytest.raises(ValueError, match="token CSV"):
        run(arms(missing, base, base))


def test_l_analyze_passes_token_csv_to_decision(tmp_path):
    root = tmp_path / "run"
    order = rg_synth.build_tree(root)
    s = a.run_analysis(root, tmp_path / "o", plots=False)
    assert s["decision"]["ungated_valid"] is True and s["decision"]["ungated_max_token_gap_s"] < 1.0


# ================================================================= M. small items
def test_m_baseline_constant_is_16_67_and_predictor_documented():
    assert metrics.BASELINE_PERIOD_MS == 16.67
    assert "N-1" in metrics.predictability.__doc__ and "16.67" in metrics.predictability.__doc__


def test_m_solo_hitch_condition_documented_as_per_cell_max():
    assert "each SOLO" in d.noise_precondition.__doc__
    s = [({"p99": 100.0, "hitch": 0.2}, {"p99": 100.0, "hitch": 1.0})] * 5
    assert d.noise_precondition(s)["solo_hitch_below_1pct_every_rep"] is False


class MaskSampler(FakeSampler):
    def __init__(self, clock, mask):
        super().__init__(clock)
        self.throttle = [mask] * 2000


@pytest.mark.parametrize("mask,power,flag", [(0x4, True, False), (0x24, True, True), (0x1 | 0x2, False, False), (0x80, False, True), (0x0, False, False), (0x4 | 0x8 | 0x20 | 0x40, True, True)])
def test_m_throttle_record_raw_mask_swpowercap_and_flag(tmp_path, mask, power, flag):
    clock = Clock()
    cfg = make_cfg(tmp_path)
    dp, _ = make_deps(cfg, clock)
    dp.make_sampler = lambda nv: MaskSampler(clock, mask)
    res = c.run_cell("UNGATED", 0, tmp_path / "x", cfg, dp)
    assert res["throttle_mask_or"] == mask and res["throttle_swpowercap"] is power and res["throttle_flag"] is flag
    assert res["flags"]["throttling"] is flag
