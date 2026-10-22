"""Interop test: the C++ side of the shared memory (workloads/background/shm.h, used by the governed llama.cpp driver) must read/write exactly the layouts that
telemetry/ring.py creates. Compiles tests/cpp/test_shm.cpp with MSVC and runs it against Python-created mappings. No GPU.
Instruction: "Proceed to the telemetry daemon, llama_governed driver and admin clock helper (/security-scan), test-first, no GPU"."""
import os
import subprocess
import uuid
from pathlib import Path

import pytest

from telemetry.ring import SeqBlock, SharedRing

ROOT = Path(__file__).resolve().parents[1]
VCVARS = r"C:\Program Files (x86)\Microsoft Visual Studio\18\BuildTools\VC\Auxiliary\Build\vcvars64.bat"


def build(tmp_path, src, exe, extra=""):
    bat = tmp_path / ("build_" + exe.stem + ".bat")
    obj = str(tmp_path / (exe.stem + ".obj"))
    bat.write_text("\r\n".join(["@echo off", f'call "{VCVARS}" >nul',
                                f'cl /nologo /O2 /EHsc /std:c++17 /I"{ROOT / "workloads" / "background"}" {extra} "{src}" /Fe:"{exe}" /Fo:"{obj}"', ""]))
    env = dict(os.environ, **{"ProgramFiles(x86)": r"C:\Program Files (x86)"})        # bash-launched pytest drops variables with parentheses
    b = subprocess.run([str(bat)], capture_output=True, text=True, timeout=300, env=env)
    assert b.returncode == 0 and exe.exists(), b.stdout + b.stderr


def warm(exe):
    """The first execution of a freshly built exe is intercepted by the endpoint scanner on this machine (14 s, and the program body ran twice: ring count 10 instead of 5,
    measured 2026-10-22), so run it once against throwaway mappings before the real checks."""
    c, p, r = SeqBlock(nm(), 3, create=True), SeqBlock(nm(), 3, create=True), SharedRing(nm(), 8, 1, create=True)
    subprocess.run([str(exe), c.name, p.name, r.name, "8"], capture_output=True, text=True, timeout=120)


def nm():
    return "Local\\gov_cpp_" + uuid.uuid4().hex


def test_cpp_reads_the_control_and_pace_blocks_and_writes_the_token_ring(tmp_path):
    exe = tmp_path / "test_shm.exe"
    build(tmp_path, ROOT / "tests" / "cpp" / "test_shm.cpp", exe)
    warm(exe)
    ctrl, pace, ring = SeqBlock(nm(), 3, create=True), SeqBlock(nm(), 3, create=True), SharedRing(nm(), 8, 1, create=True)
    ctrl.write([1.0, 0.5, 0.7])
    pace.write([1.0, 12.5, 3.25])
    r = subprocess.run([str(exe), ctrl.name, pace.name, ring.name, "8"], capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "CTRL 1 0.5 0.7" in r.stdout and "PACE 1 12.5 3.25" in r.stdout
    rec, dropped = ring.read_new()
    assert dropped == 0 and rec[:, 0].tolist() == [1.0, 2.0, 3.0, 4.0, 5.0]


def test_cpp_reports_an_unwritten_block_and_rejects_a_wrong_geometry(tmp_path):
    exe = tmp_path / "test_shm.exe"
    build(tmp_path, ROOT / "tests" / "cpp" / "test_shm.cpp", exe)
    warm(exe)
    ctrl, pace, ring = SeqBlock(nm(), 3, create=True), SeqBlock(nm(), 3, create=True), SharedRing(nm(), 8, 1, create=True)
    r = subprocess.run([str(exe), ctrl.name, pace.name, ring.name, "8"], capture_output=True, text=True, timeout=30)
    assert "CTRL none" in r.stdout and r.returncode == 0
    r = subprocess.run([str(exe), ctrl.name, pace.name, ring.name, "16"], capture_output=True, text=True, timeout=30)
    assert r.returncode != 0 and "geometry" in (r.stdout + r.stderr)
