"""The governed llama.cpp driver (workloads/background/llama_governed_bench.cpp) must compile and link against the pinned llama.cpp build and keep the no-CPU-fallback
checks of the original driver. Build only: running it needs the GPU (hardware smoke, not part of this stage).
Instruction: "Proceed to the telemetry daemon, llama_governed driver and admin clock helper (/security-scan), test-first, no GPU"."""
import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "workloads" / "background" / "llama_governed_bench.cpp"


def test_governed_driver_source_keeps_the_gpu_only_guards_and_the_shared_pacing_header():
    s = SRC.read_text(encoding="utf-8")
    for needle in ("llama_supports_gpu_offload", "not all layers offloaded to the GPU", "EXEC_MODE cuda offloaded=", '#include "pacing.h"', '#include "shm.h"',
                   "aligned_may_start", "unaligned_wake"):
        assert needle in s, needle


def test_governed_driver_builds(tmp_path):
    bat = ROOT / "workloads" / "background" / "build_llama_governed.bat"
    exe = ROOT / "workloads" / "background" / "llama_governed_bench.exe"
    backup = tmp_path / "llama_governed_bench.exe.bak"
    had = exe.exists()
    if had:
        shutil.copy2(exe, backup)                                                       # the registered runs need an identical exe hash across sessions (yaml session_break_rule): put the original back afterwards
        exe.unlink()
    env = dict(os.environ, **{"ProgramFiles(x86)": r"C:\Program Files (x86)"})        # bash-launched pytest drops variables with parentheses
    try:
        b = subprocess.run([str(bat)], capture_output=True, text=True, timeout=600, env=env)
        assert exe.exists(), b.stdout + b.stderr
    finally:
        if had:
            shutil.copy2(backup, exe)


def test_governed_driver_shifts_the_context_instead_of_stopping_when_it_is_full():
    s = SRC.read_text(encoding="utf-8")
    for needle in ("llama_memory_can_shift", "llama_memory_seq_rm", "llama_memory_seq_add", "shifted"):
        assert needle in s, needle
    assert "(int)ids.size() + n_prompt + 2 < (int)cp.n_ctx" not in s            # the old stop at a full context (smoke 3: 1534 tokens)
