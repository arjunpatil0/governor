from pathlib import Path

PKG = Path(__file__).resolve().parents[2] / "tools" / "realgame"
# clockcheck.py holds the READ-ONLY clock-state checks of amendment 15: it must name the helper it looks for ('clock_helper': a process command-line match and the pipe path) to
# refuse to run while that helper exists. It never issues a clock command; only that one token is allowed there, every other forbidden string still applies to it.
ALLOWED = {"clockcheck.py": ("clock_helper",)}
FORBIDDEN = ("lgc", "rgc", "lmc", "clock_helper", "safeclient", "handover_cell", "timebeginperiod", "--lock", "nvidia-smi -")


def test_package_exists_and_has_the_named_files():
    for n in ("__init__", "presentmon", "gpu_priority", "metrics", "decision", "cell", "run", "analyze", "clockcheck"):
        assert (PKG / f"{n}.py").exists(), n


def test_no_clock_lock_strings_anywhere_in_tools_realgame():
    hits = []
    for p in PKG.rglob("*.py"):
        low = p.read_text(encoding="utf-8").lower()
        hits += [(p.name, f) for f in FORBIDDEN if f in low and f not in ALLOWED.get(p.name, ())]
    assert hits == []


def test_no_windows_only_imports_at_module_level():
    import re
    bad = re.compile(r"^(import|from)\s+(winreg|pynvml|experiments\.|pywintypes|win32\w*|psutil)", re.M)
    for p in PKG.rglob("*.py"):
        assert not bad.search(p.read_text(encoding="utf-8")), p.name
        assert "windll" not in "".join(l for l in p.read_text(encoding="utf-8").splitlines() if not l.startswith((" ", "\t"))), p.name


def test_clockcheck_only_reads_and_names_the_helper_only_in_the_allowed_token():
    src = (PKG / "clockcheck.py").read_text(encoding="utf-8")
    assert "subprocess.run" in src          # the nvidia-smi queries moved to cell.py (amendment 21); the idle reader that used them is gone
    for bad in ("nvmlDeviceSetGpuLockedClocks", "SetApplicationsClocks", "nvmlDeviceSet", "ResetGpuLockedClocks", "os.remove", "os.kill", "terminate", ".kill("):
        assert bad not in src, bad
