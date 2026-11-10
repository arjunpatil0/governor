from pathlib import Path

PKG = Path(__file__).resolve().parents[2] / "tools" / "realgame"
FORBIDDEN = ("lgc", "rgc", "lmc", "clock_helper", "safeclient", "handover_cell", "timebeginperiod", "--lock", "nvidia-smi -")


def test_package_exists_and_has_the_named_files():
    for n in ("__init__", "presentmon", "gpu_priority", "metrics", "decision", "cell", "run", "analyze"):
        assert (PKG / f"{n}.py").exists(), n


def test_no_clock_lock_strings_anywhere_in_tools_realgame():
    hits = []
    for p in PKG.rglob("*.py"):
        low = p.read_text(encoding="utf-8").lower()
        hits += [(p.name, f) for f in FORBIDDEN if f in low]
    assert hits == []


def test_no_windows_only_imports_at_module_level():
    import re
    bad = re.compile(r"^(import|from)\s+(winreg|pynvml|experiments\.|pywintypes|win32\w*|psutil)", re.M)
    for p in PKG.rglob("*.py"):
        assert not bad.search(p.read_text(encoding="utf-8")), p.name
        assert "windll" not in "".join(l for l in p.read_text(encoding="utf-8").splitlines() if not l.startswith((" ", "\t"))), p.name
