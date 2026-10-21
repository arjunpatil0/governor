"""GPU integration test for workloads/background/llama_decode_bench.exe (llama.cpp validation addendum). Needs the build under
third_party/llama.cpp, the pinned model under data/llama/ and the GPU; fails (never skips) if the driver is missing."""
import os
import subprocess
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
EXE = ROOT / "workloads" / "background" / "llama_decode_bench.exe"
BIN = ROOT / "third_party" / "llama.cpp" / "build" / "bin"
ENV = dict(os.environ, PATH=str(BIN) + os.pathsep + os.environ["PATH"])
MODEL = ROOT / "data" / "llama" / "Llama-3.2-3B-Instruct-Q4_K_M.gguf"


def test_driver_decodes_on_gpu_and_logs_execution_mode(tmp_path):
    assert EXE.exists(), "driver not built: run workloads/background/build_llama_driver.bat"
    out = tmp_path / "o.csv"
    r = subprocess.run([str(EXE), str(MODEL), str(ROOT / "data" / "llama" / "prompt.txt"), str(out), "-1", "1.5"],
                       capture_output=True, text=True, timeout=180, env=ENV)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "EXEC_MODE cuda offloaded=" in r.stdout
    d = pd.read_csv(out)
    assert len(d) > 20 and (d.t_tok_end.diff().dropna() > 0).all() and d.token.between(0, 200000).all()


def test_driver_refuses_missing_model(tmp_path):
    assert EXE.exists()
    r = subprocess.run([str(EXE), str(tmp_path / "nope.gguf"), str(ROOT / "data" / "llama" / "prompt.txt"), str(tmp_path / "o.csv"), "-1", "1"],
                       capture_output=True, text=True, timeout=60, env=ENV)
    assert r.returncode != 0
