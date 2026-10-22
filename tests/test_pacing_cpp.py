"""Golden-case test: the C++ pacing decisions (workloads/background/pacing.h, used by the governed llama.cpp driver) must equal sim/pacing.py.
Compiles tests/cpp/test_pacing.cpp with MSVC (vcvars64 as in workloads/background/build_llama_driver.bat), runs it on generated cases. No GPU. Fails, never skips, if the toolchain is missing."""
import math
import os
import subprocess
from pathlib import Path

import numpy as np

from sim.pacing import aligned_may_start, unaligned_wake

ROOT = Path(__file__).resolve().parents[1]
VCVARS = r"C:\Program Files (x86)\Microsoft Visual Studio\18\BuildTools\VC\Auxiliary\Build\vcvars64.bat"


def _cases(n=400, seed=0):
    rng = np.random.default_rng(seed)
    rows = []
    for _ in range(n):
        ts = rng.uniform(0, 1000); te = ts + rng.uniform(0.5, 30); duty = float(rng.choice([0.0, 0.05, 0.25, 0.5, 0.9, 1.0, rng.uniform(0.01, 1.0)]))
        rows.append(("U", ts, te, duty, unaligned_wake(ts, te, duty)))
        now = rng.uniform(0, 1000); busy = int(rng.integers(0, 2)); tok = rng.uniform(1, 15); guard = rng.uniform(-4, 4)
        nxt = math.inf if rng.random() < 0.2 else now + rng.uniform(0, 30)
        rows.append(("A", now, busy, tok, guard, nxt, int(aligned_may_start(now, bool(busy), tok, guard, nxt))))
    rows.append(("A", 0.0, 0, 10.0, 0.5, 10.5, int(aligned_may_start(0.0, False, 10.0, 0.5, 10.5))))      # exactly fits
    return rows


def test_cpp_pacing_matches_the_python_reference_on_golden_cases(tmp_path):
    csv = tmp_path / "cases.csv"
    csv.write_text("\n".join(",".join(v if isinstance(v, str) else ("inf" if math.isinf(v) else repr(float(v))) for v in r) for r in _cases()) + "\n")
    exe = tmp_path / "test_pacing.exe"
    bat = tmp_path / "build.bat"
    src, inc, obj = ROOT / "tests" / "cpp" / "test_pacing.cpp", ROOT / "workloads" / "background", str(tmp_path / "t.obj")
    bat.write_text("\r\n".join(["@echo off", f'call "{VCVARS}" >nul',
                                f'cl /nologo /O2 /EHsc /std:c++17 /I"{inc}" "{src}" /Fe:"{exe}" /Fo:"{obj}"', ""]))
    env = dict(os.environ, **{"ProgramFiles(x86)": r"C:\Program Files (x86)"})       # bash-launched pytest drops variables with parentheses
    b = subprocess.run([str(bat)], capture_output=True, text=True, timeout=300, env=env)
    assert b.returncode == 0 and exe.exists(), b.stdout + b.stderr
    r = subprocess.run([str(exe), str(csv)], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "CHECKED 801" in r.stdout
