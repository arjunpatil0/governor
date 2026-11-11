"""Static power fields come from NVML (no process per cell); nvidia-smi text is information only with a 20 s timeout; every subprocess call has a timeout. Fakes only."""
import json
import re
import subprocess
from pathlib import Path

import pytest

from test_cell import Clock, FakeProbes, make_cfg, make_deps
from tools.realgame import cell as c

PKG = Path(__file__).resolve().parents[2] / "tools" / "realgame"


class FakeNv:
    def __init__(self, default_mw=80000, cons=(5000, 140000), err=None):
        self.default_mw, self.cons, self.err = default_mw, cons, err

    def nvmlInit(self):
        pass

    def nvmlDeviceGetHandleByIndex(self, i):
        return "h"

    def nvmlDeviceGetPowerManagementDefaultLimit(self, h):
        if self.err:
            raise self.err
        return self.default_mw

    def nvmlDeviceGetPowerManagementLimitConstraints(self, h):
        return self.cons


def test_nvml_static_read_parses():
    got = c.NvmlPowerStaticReader(FakeNv()).read()
    assert (got["default_power_limit_w"], got["min_power_limit_w"], got["max_power_limit_w"]) == (80.0, 5.0, 140.0) and got["source"] == "nvml"


def test_read_power_static_uses_probe_and_records_source():
    class P(FakeProbes):
        def nvml_power_static(self):
            return c.NvmlPowerStaticReader(FakeNv()).read()
    assert c.read_power_static(P())["source"] == "nvml"


def test_changed_default_refuses_and_half_watt_boundary():
    ref = c.NvmlPowerStaticReader(FakeNv()).read()
    assert c.power_static_problems(ref, c.NvmlPowerStaticReader(FakeNv(default_mw=90000)).read())
    assert c.power_static_problems(ref, c.NvmlPowerStaticReader(FakeNv(default_mw=80500)).read()) == []
    assert c.power_static_problems(ref, c.NvmlPowerStaticReader(FakeNv(default_mw=80600)).read())


def test_nvml_error_refuses_with_clear_message(tmp_path):
    class P(FakeProbes):
        def nvml_power_static(self):
            return c.NvmlPowerStaticReader(FakeNv(err=RuntimeError("nvml dead"))).read()
    with pytest.raises(c.PowerStaticError, match="(?i)NVML.*nvml dead.*refusing"):
        c.read_power_static(P())
    with pytest.raises(c.PreflightError, match="(?i)power"):
        c.preflight(make_cfg(tmp_path), P())


class TimeoutSmi(FakeProbes):
    def nvidia_smi_power_text(self):
        raise subprocess.TimeoutExpired("nvidia-smi", 20)

    def nvidia_smi_text(self):
        raise subprocess.TimeoutExpired("nvidia-smi", 20)

    def nvidia_smi_display(self):
        raise subprocess.TimeoutExpired("nvidia-smi", 20)


def test_sweep_start_survives_smi_timeouts():
    rec = c.sweep_start_records(TimeoutSmi())
    assert rec["nvidia_smi_processes"].startswith("unavailable (TimeoutExpired")
    assert rec["nvidia_smi_power"].startswith("unavailable (TimeoutExpired")
    assert rec["display_active"].startswith("unavailable (TimeoutExpired")
    assert rec["power_static"]["max_power_limit_w"] == 140.0 and rec["power_static"]["source"] == "nvml"


def test_sweep_start_records_smi_power_info_when_available():
    rec = c.sweep_start_records(FakeProbes())
    assert rec["nvidia_smi_power"]["current_power_limit_w"] == 80.0 and rec["nvidia_smi_power"]["raw_lines"]


def test_smi_timeout_message_text(monkeypatch):
    def boom(*a, **k):
        assert k["timeout"] == 20
        raise subprocess.TimeoutExpired("x", 20)
    monkeypatch.setattr(c.subprocess, "run", boom)
    monkeypatch.setattr(c, "nvidia_smi_exe", lambda: "nvidia-smi.exe")
    with pytest.raises(subprocess.TimeoutExpired):
        c.SystemProbes().nvidia_smi_power_text()
    assert c.info_timeout_text(subprocess.TimeoutExpired("x", 20)) == "unavailable (TimeoutExpired after 20 s)"


def test_git_timeout_refuses_with_clear_message(monkeypatch):
    def boom(*a, **k):
        assert k["timeout"] == 30
        raise subprocess.TimeoutExpired("git", 30)
    monkeypatch.setattr(c.subprocess, "run", boom)
    monkeypatch.setattr(c, "tool_paths", lambda: {"git": "git.exe"})
    with pytest.raises(RuntimeError, match="(?i)git.*timed out after 30 s.*refusing"):
        c._git(".", "status")


def test_per_cell_check_never_calls_nvidia_smi(tmp_path):
    calls = []

    class P(FakeProbes):
        def nvidia_smi_power_text(self):
            calls.append("power")
            return super().nvidia_smi_power_text()

        def nvidia_smi_text(self):
            calls.append("text")
            return ""

        def nvidia_smi_display(self):
            calls.append("display")
            return {}
    cfg = make_cfg(tmp_path, power_static_ref=c.read_power_static(FakeProbes()))
    c.preflight(cfg, P())
    d, _ = make_deps(cfg, Clock())
    d.probes = P()
    c.run_cell("SOLO", 0, tmp_path / "cell", cfg, d)
    assert calls == []
    assert json.loads((tmp_path / "cell" / "result.json").read_text())["power_static_cell_start"]["source"] == "nvml"


# Long-running children started with Popen (LLM driver, PresentMon) are exempt: they are stopped by their own wrappers.
POPEN_EXEMPT = {("cell.py", "popen=subprocess.Popen"), ("presentmon.py", "popen=subprocess.Popen"), ("presentmon.py", "run=subprocess.run")}


def test_every_subprocess_call_has_a_timeout():
    pat = re.compile(r"subprocess\.(run|Popen|check_output|check_call|call)\b")
    bad = []
    for p in PKG.glob("*.py"):
        src = p.read_text(encoding="utf-8")
        for m in pat.finditer(src):
            line = src[:m.start()].count("\n")
            lines = src.splitlines()
            text = lines[line]
            if any(e[0] == p.name and e[1] in text for e in POPEN_EXEMPT):
                continue
            if m.group(0).endswith("TimeoutExpired"):
                continue
            window = "\n".join(lines[line:line + 4])
            if "timeout=" not in window:
                bad.append(f"{p.name}:{line + 1}")
    assert bad == []
