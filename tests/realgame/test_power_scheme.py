"""Power scheme guard (read-only powercfg reader, record, --expect-power-scheme) and the rehearsal evidence bound to the current executables. All with fakes."""
import json
import subprocess
from pathlib import Path

import pytest

import rg_synth
from test_cell import Clock, FakeProbes, make_cfg, make_deps
from test_rehearse import deps_for, sweep_main
from test_review2 import main_args
from tools.realgame import cell as c
from tools.realgame import run as r

SILENT = ("64a64f24-65b9-4b56-befd-5ec1eaced9b3", "Silent")
TURBO = ("11111111-2222-3333-4444-555555555555", "Turbo")
OUT = "Power Scheme GUID: 64a64f24-65b9-4b56-befd-5ec1eaced9b3  (Silent)\n"


# ---------------------------------------------------------------- reader
def test_parse_power_scheme():
    assert c.parse_power_scheme(OUT) == SILENT
    assert c.parse_power_scheme("Power Scheme GUID: 381B4222-F694-41F0-9685-FF5BB260DF2E  (Balanced)") == ("381b4222-f694-41f0-9685-ff5bb260df2e", "Balanced")


@pytest.mark.parametrize("text", ["", "garbage", "Power Scheme GUID: nothex  (X)", None])
def test_parse_power_scheme_unparseable(text):
    with pytest.raises(c.PowerSchemeError):
        c.parse_power_scheme(text)


def test_reader_uses_full_path_fixed_argv_no_shell_timeout():
    seen = {}

    def run(argv, **kw):
        seen.update(argv=argv, **kw)
        return subprocess.CompletedProcess(argv, 0, stdout=OUT)
    assert c.read_active_power_scheme(run=run, system_root=r"C:\Windows") == SILENT
    assert seen["argv"] == [str(Path(r"C:\Windows") / "System32" / "powercfg.exe"), "/getactivescheme"]
    assert seen["shell"] is False and seen["timeout"] == 20 and seen["check"] is True


def test_reader_wraps_failures():
    def run(argv, **kw):
        raise subprocess.TimeoutExpired(argv, 20)
    with pytest.raises(c.PowerSchemeError):
        c.read_active_power_scheme(run=run, system_root=r"C:\Windows")


def test_system_probes_has_power_scheme():
    assert callable(c.SystemProbes.power_scheme) and callable(c.SystemProbes.file_stat) and callable(c.SystemProbes.git_changed)


# ---------------------------------------------------------------- matching
@pytest.mark.parametrize("expect,ok", [("silent", True), ("SIL", True), (SILENT[0], True), (SILENT[0].upper(), True), ("turbo", False), ("64a64f24", False), (TURBO[0], False)])
def test_match_by_name_and_guid(expect, ok):
    assert c.power_scheme_matches(expect, *SILENT) is ok


# ---------------------------------------------------------------- preflight
def pf(tmp_path, probes, expect):
    return c.preflight(make_cfg(tmp_path, expect_power_scheme=expect), probes)


def test_preflight_match_passes_and_mismatch_refuses(tmp_path):
    assert pf(tmp_path, FakeProbes(), "silent") is None
    assert pf(tmp_path, FakeProbes(), SILENT[0]) is None
    p = FakeProbes()
    p.scheme = TURBO
    with pytest.raises(c.PreflightError, match="(?i)power scheme"):
        pf(tmp_path, p, "silent")
    with pytest.raises(c.PreflightError, match="(?i)power scheme"):
        pf(tmp_path, p, SILENT[0])


def test_preflight_unparseable_refuses_only_with_flag(tmp_path):
    p = FakeProbes()
    p.scheme = c.PowerSchemeError("cannot parse")
    assert pf(tmp_path, p, None) is None
    with pytest.raises(c.PreflightError, match="(?i)power scheme"):
        pf(tmp_path, p, "silent")


# ---------------------------------------------------------------- cell
def cell(tmp_path, scheme, expect=None, out="cell"):
    clock = Clock()
    cfg = make_cfg(tmp_path, expect_power_scheme=expect)
    d, _ = make_deps(cfg, clock)
    d.probes = FakeProbes()
    d.probes.scheme = scheme
    return c.run_cell("UNGATED", 0, tmp_path / out, cfg, d)


def test_cell_records_scheme_in_meta_and_result_start_and_end(tmp_path):
    res = cell(tmp_path, SILENT)
    for doc in (res, json.loads((tmp_path / "cell" / "result.json").read_text()), json.loads((tmp_path / "cell" / "meta.json").read_text())):
        assert (doc["power_scheme_guid"], doc["power_scheme_name"]) == SILENT
        assert (doc["power_scheme_guid_end"], doc["power_scheme_name_end"]) == SILENT


def test_cell_match_by_name_and_guid_passes(tmp_path):
    cell(tmp_path, SILENT, "silent", "a")
    cell(tmp_path, SILENT, SILENT[0], "b")


@pytest.mark.parametrize("expect", ["turbo", TURBO[0]])
def test_cell_mismatch_refuses_deterministically(tmp_path, expect):
    with pytest.raises(c.CellRefused, match="(?i)power scheme"):
        cell(tmp_path, SILENT, expect, "x")
    assert not (tmp_path / "x" / "result.json").exists()


def test_cell_unparseable_refuses_only_with_flag(tmp_path):
    bad = c.PowerSchemeError("cannot parse")
    res = cell(tmp_path, bad, None, "n")
    assert res["power_scheme_guid"] is None and res["power_scheme_name"] is None
    with pytest.raises(c.CellRefused, match="(?i)power scheme"):
        cell(tmp_path, bad, "silent", "f")


def test_mid_cell_change_fails_the_cell(tmp_path):
    with pytest.raises(RuntimeError, match="(?i)power scheme.*changed") as e:
        cell(tmp_path, [SILENT, TURBO], None, "m")
    assert not isinstance(e.value, c.CellRefused)
    assert not (tmp_path / "m" / "result.json").exists()
    meta = json.loads((tmp_path / "m" / "meta.json").read_text())
    assert meta["power_scheme_name"] == "Silent" and meta["power_scheme_name_end"] == "Turbo"


def test_mid_cell_change_fails_with_flag_too(tmp_path):
    with pytest.raises(RuntimeError, match="(?i)changed"):
        cell(tmp_path, [SILENT, TURBO], "silent", "m2")


# ---------------------------------------------------------------- run_meta / records
def test_sweep_start_records_has_scheme():
    rec = c.sweep_start_records(FakeProbes())
    assert (rec["power_scheme_guid"], rec["power_scheme_name"]) == SILENT
    p = FakeProbes()
    p.scheme = c.PowerSchemeError("x")
    assert c.sweep_start_records(p)["power_scheme_guid"].startswith("unavailable")
    assert "power_scheme_guid" in r.RECORD_KEYS and "power_scheme_name" in r.RECORD_KEYS


def test_run_meta_has_scheme_in_llm_alone(tmp_path):
    rg_synth.write_fresh_clock_check(tmp_path / "run")
    runner = lambda arm, rep, out, cfg, **k: (Path(out).mkdir(parents=True, exist_ok=True), (Path(out) / "result.json").write_text("{}"))
    assert r.main(main_args(tmp_path, "--llm-alone", "--run-dir", str(tmp_path / "run")), probes=FakeProbes(game=False), runner=runner) == 0
    assert json.loads((tmp_path / "run" / "run_meta.json").read_text())["power_scheme_name"] == "Silent"


def test_cli_flag_refuses_before_any_cell(tmp_path, capsys):
    p = FakeProbes()
    p.scheme = TURBO
    assert r.main(main_args(tmp_path, "--dry-run", "--expect-power-scheme", "silent"), probes=p) == 2
    assert "power scheme" in capsys.readouterr().err.lower()
    assert r.main(main_args(tmp_path, "--dry-run", "--expect-power-scheme", "turbo"), probes=p) == 0


# ---------------------------------------------------------------- rehearsal binding
def test_all_match_passes(tmp_path):
    code, seen = sweep_main(tmp_path)
    assert code == 0 and seen


def refused(tmp_path, capsys, probes=None, **doc_update):
    code, seen = sweep_main(tmp_path, probes=probes, rehearsal=doc_update)
    err = capsys.readouterr().err
    assert code == 2 and not seen and "--rehearse" in err
    return err


def test_llm_exe_hash_mismatch(tmp_path, capsys):
    assert "llm_exe " in refused(tmp_path, capsys, exe_sha256={"llm_exe": "other", "llm_exe_vk": "sha-llama_realgame_bench_vk.exe"})


def test_vk_exe_hash_mismatch(tmp_path, capsys):
    assert "llm_exe_vk" in refused(tmp_path, capsys, exe_sha256={"llm_exe": "sha-a", "llm_exe_vk": "other"})


def test_vk_ignored_when_igpu_dropped(tmp_path):
    rg_synth.write_fresh_clock_check(tmp_path / "run", rehearsal=False)
    rg_synth.write_fresh_rehearsal(tmp_path / "run", arms=("UNGATED", "PRIO_IDLE", "DUTY50"), exe_sha256={"llm_exe": "sha-a"})
    seen = []
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(r, "run_sweep", lambda *a, **k: seen.append(a) or "complete")
        code = r.main(main_args(tmp_path, "--run-dir", str(tmp_path / "run"), "--reps", "1", "--drop-igpu", "no vk"), probes=FakeProbes(), runner=lambda *a, **k: None)
    assert code == 0 and seen


def test_model_size_mismatch(tmp_path, capsys):
    assert "size" in refused(tmp_path, capsys, model={"size": 999, "mtime": 1.0})


def test_model_mtime_mismatch(tmp_path, capsys):
    assert "mtime" in refused(tmp_path, capsys, model={"size": 1000, "mtime": 2.0})


def test_presentmon_hash_mismatch(tmp_path, capsys):
    assert "PresentMon" in refused(tmp_path, capsys, presentmon_sha256="0" * 64)


def test_git_changed_files_refused(tmp_path, capsys):
    p = FakeProbes()
    p.changed = ["tools/realgame/cell.py"]
    assert "tools/realgame/cell.py" in refused(tmp_path, capsys, probes=p, git_head="old")


def test_git_same_head_not_diffed_and_clean_diff_passes(tmp_path):
    p = FakeProbes()
    p.changed = ["tools/realgame/cell.py"]
    assert sweep_main(tmp_path, probes=p)[0] == 0                                        # same head: nothing to diff
    assert sweep_main(tmp_path, probes=FakeProbes(), rehearsal={"git_head": "old"})[0] == 0   # head moved, nothing relevant changed


@pytest.mark.parametrize("key", ["exe_sha256", "presentmon_sha256", "model", "git_head"])
def test_missing_records_refuse(tmp_path, capsys, key):
    code, _ = sweep_main(tmp_path, rehearsal={key: None})
    assert code == 2 and "--rehearse" in capsys.readouterr().err


def test_first_mismatch_is_named(tmp_path, capsys):
    err = refused(tmp_path, capsys, exe_sha256={"llm_exe": "x", "llm_exe_vk": "y"}, model={"size": 1, "mtime": 9})
    assert "llm_exe " in err and "llm_exe_vk" not in err and "size" not in err


def test_rehearse_records_binding(tmp_path):
    cfg, d, clock = deps_for(tmp_path, game=False)
    d.probes = FakeProbes(game=False)
    r.main(main_args(tmp_path, "--rehearse", "--run-dir", str(tmp_path / "run")), probes=d.probes, deps=d)
    doc = json.loads((tmp_path / "run" / "rehearsal.json").read_text())
    assert doc["git_head"] == "abc123" and doc["model"] == {"size": 1000, "mtime": 1.0} and "llm_exe" in doc["exe_sha256"]
    assert doc["presentmon_sha256"] == c.PRESENTMON_SHA256_PREREG
    assert "power_scheme_name" in json.loads((tmp_path / "run" / "rehearsal_start_records.json").read_text())
