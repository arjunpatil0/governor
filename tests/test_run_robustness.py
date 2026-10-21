"""Run-harness robustness after the A2 stalls (journal 0023): console QuickEdit must be off, every nvidia-smi call must have a timeout."""
import ast
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SMI_FILES = ["experiments/w1_downclock/run.py", "experiments/w2_colocation/run.py", "experiments/w2_colocation/trace_cell.py"]


def _smi_runs_without_timeout(path):
    tree = ast.parse((ROOT / path).read_text(encoding="utf-8"))
    bad = []
    for n in ast.walk(tree):
        if (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "run"
                and n.args and isinstance(n.args[0], ast.List) and n.args[0].elts
                and isinstance(n.args[0].elts[0], ast.Constant) and n.args[0].elts[0].value == "nvidia-smi"
                and not any(k.arg == "timeout" for k in n.keywords)):
            bad.append(f"{path}:{n.lineno}")
    return bad


@pytest.mark.parametrize("path", SMI_FILES)
def test_every_nvidia_smi_subprocess_run_has_a_timeout(path):
    assert _smi_runs_without_timeout(path) == []


def test_quickedit_mode_clears_bit_0x40_and_sets_extended_flags():
    from console import quickedit_off_mode
    m = quickedit_off_mode(0x1F7)                       # a typical console input mode with QuickEdit (0x40) on
    assert m & 0x40 == 0 and m & 0x80 == 0x80           # ENABLE_QUICK_EDIT_MODE off, ENABLE_EXTENDED_FLAGS on
    assert m & 0x37 == 0x1F7 & 0x37                     # other bits untouched


def test_disable_quickedit_does_not_raise_without_a_console():
    from console import disable_quickedit
    assert disable_quickedit() in (True, False)


def test_smi_timeout_returns_failure_not_a_hang(monkeypatch):
    import run as R

    def boom(*a, **k):
        assert k.get("timeout")
        raise subprocess.TimeoutExpired(a[0], k["timeout"])
    monkeypatch.setattr(R.subprocess, "run", boom)
    rc, out = R.smi("-rgc")
    assert rc != 0 and "timed out" in out
