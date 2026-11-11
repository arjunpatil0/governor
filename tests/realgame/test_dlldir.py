import json
import os

import pytest

from tools.realgame import cell as c
from tests.realgame.test_cell import Clock, FakeLlm, FakeProbes, exec_line, make_cfg, make_deps


def _run(tmp_path, monkeypatch, arm):
    monkeypatch.setenv("PATH", "OLDPATH_MARK")
    seen = []
    clock = Clock()
    cfg = make_cfg(tmp_path)
    dp, _ = make_deps(cfg, clock)
    dp.spawn_llm = lambda cmd, env, p: (seen.append(dict(env)), FakeLlm(clock, p, exec_line(env)))[1]
    out = tmp_path / arm
    res = c.run_cell(arm, 0, out, cfg, dp)
    return cfg, seen[0], out, res


def test_cuda_path_prefix(tmp_path, monkeypatch):
    cfg, env, out, res = _run(tmp_path, monkeypatch, "UNGATED")
    want = str((cfg.llama_dir / "build" / "bin").resolve())
    assert env["PATH"] == want + os.pathsep + "OLDPATH_MARK"
    assert json.loads((out / "meta.json").read_text())["llm_dll_dir"] == want
    assert json.loads((out / "result.json").read_text())["llm_dll_dir"] == want == res["llm_dll_dir"]


def test_vulkan_path_prefix(tmp_path, monkeypatch):
    cfg, env, out, res = _run(tmp_path, monkeypatch, "IGPU")
    want = str((cfg.llama_dir / "build_vk" / "bin").resolve())
    assert env["PATH"] == want + os.pathsep + "OLDPATH_MARK"
    assert json.loads((out / "meta.json").read_text())["llm_dll_dir"] == want


def test_preflight_refuses_missing_dll_dir(tmp_path):
    cfg = make_cfg(tmp_path)
    d = (cfg.llama_dir / "build" / "bin").resolve()
    with pytest.raises(c.PreflightError) as e:
        c.preflight(cfg, FakeProbes(missing=[d]))
    assert str(d) in str(e.value)


@pytest.mark.parametrize("dll", ["ggml-base.dll", "ggml-cuda.dll"])
def test_preflight_refuses_dir_without_dlls(tmp_path, dll):
    cfg = make_cfg(tmp_path)
    d = (cfg.llama_dir / "build" / "bin").resolve()
    with pytest.raises(c.PreflightError) as e:
        c.preflight(cfg, FakeProbes(missing=[d / dll]))
    assert dll in str(e.value) and str(d) in str(e.value)


def test_preflight_vulkan_dir_checked_only_when_needed(tmp_path):
    cfg = make_cfg(tmp_path)
    d = (cfg.llama_dir / "build_vk" / "bin").resolve()
    assert c.preflight(cfg, FakeProbes(missing=[d / "ggml-vulkan.dll"])) is None
    with pytest.raises(c.PreflightError) as e:
        c.preflight(cfg, FakeProbes(missing=[d / "ggml-vulkan.dll"]), need_vk=True)
    assert "ggml-vulkan.dll" in str(e.value) and str(d) in str(e.value)


class _P:
    def __init__(self, rc, exits=True):
        self.rc, self.exits, self.waited = rc, exits, None
        self.stdout = iter(())

    def wait(self, timeout=None):
        self.waited = timeout
        if not self.exits:
            import subprocess
            raise subprocess.TimeoutExpired("x", timeout)
        return self.rc

    def poll(self):
        return None if not self.exits else self.rc


def _eof_msg(p):
    lp = c.LlmProc.__new__(c.LlmProc)
    import queue
    lp.p, lp.lines, lp._q = p, [], queue.Queue()
    lp._q.put(None)
    with pytest.raises(RuntimeError) as e:
        lp.wait_for("READY", 1)
    return str(e.value)


def test_rc_ntstatus_hex():
    p = _P(-1073741515)
    m = _eof_msg(p)
    assert "0xC0000135" in m and "DLL not found" in m and "None" not in m and p.waited == 5


def test_rc_plain_and_unsigned():
    assert "rc=1" in _eof_msg(_P(1))
    assert "0xC0000135" in _eof_msg(_P(0xC0000135))


def test_rc_never_exits():
    m = _eof_msg(_P(None, exits=False))
    assert "still running after 5 s" in m and "rc=None" not in m
