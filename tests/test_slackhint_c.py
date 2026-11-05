"""Conformance of include/slackhint.h (C and C++) against the Python binding and the experiments' SeqBlock: wire format both ways, the last-good-value view, the fit and duty rules, the clean-unit
estimator, and a torn-read stress in both directions. Compiles with MSVC (no GPU). Spec: docs/SPEC_FRAME_SLACK_HINTS.md.
Instruction (Arjun): "Extract a small library: include/slackhint.h (C, producer and consumer API over the existing pace_view/seqlock code) and a Python binding, with tests." """
import math
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
import slackhint as sh  # noqa: E402
from telemetry.ring import SeqBlock  # noqa: E402
from test_shm_cpp import build  # noqa: E402

INC = f'/I"{ROOT / "include"}"'


def nm():
    return "Local\\slackhint_c_" + uuid.uuid4().hex


@pytest.fixture(scope="module")
def exe(tmp_path_factory):
    d = tmp_path_factory.mktemp("slackhint")
    e = d / "test_slackhint.exe"
    build(d, ROOT / "tests" / "cpp" / "test_slackhint.c", e, extra=f"/TC {INC}")
    subprocess.run([str(e), "rules"], capture_output=True, timeout=120)                    # warm the fresh exe (first run is intercepted by the endpoint scanner, journal 0036)
    return e


def run(exe, *args, timeout=60):
    r = subprocess.run([str(exe), *map(str, args)], capture_output=True, text=True, timeout=timeout)
    assert r.returncode == 0, r.stdout + r.stderr
    return r.stdout.split("\n")


def fields(lines, tag):
    return [ln.split()[1:] for ln in lines if ln.startswith(tag + " ")]


def test_c_rules_match_the_python_binding(exe):
    out = run(exe, "rules")
    assert fields(out, "FIT")[0] == ["1", "0", "0", "1", "0"]
    assert [float(x) for x in fields(out, "DUTY")[0]] == [math.inf, 2.0, pytest.approx(3.0), pytest.approx(0.04), 2.0]
    assert fields(out, "OVERLAP")[0] == ["1", "0", "1", "0", "0"]
    assert [sh.may_start(0.0, False, 0.010, 0.001, 0.011), sh.may_start(0.0, False, 0.010, 0.001, 0.0109), sh.may_start(0.0, True, 0.001, 0.0, math.inf),
            sh.may_start(0.0, False, 10.0, 1.0, math.inf), sh.may_start(0.0, False, 0.0101, 0.0, 0.0100)] == [True, False, False, True, False]


def test_c_estimator_equals_the_python_estimator_on_a_deterministic_sequence(exe):
    rows = fields(run(exe, "estimator"), "EST")
    e = sh.Estimator()
    assert len(rows) == 40
    for i, (idx, ewma, clean, value) in enumerate(rows):
        u = 0.010 + ((i * 7) % 5) * 0.0001
        ov = i % 4 == 0
        e.push(u * 2.0 if ov else u, ov)
        assert int(idx) == i and float(ewma) == pytest.approx(e.ewma(), rel=1e-9) and float(value) == pytest.approx(e.value(), rel=1e-9)
        if clean == "none":
            assert math.isnan(e.clean())
        else:
            assert float(clean) == pytest.approx(e.clean(), rel=1e-9)


def test_c_consumer_reads_a_python_producer_and_treats_a_stale_record_as_idle(exe):
    name = nm()
    p = sh.Producer(name)
    p.frame_started(3.25, 12.5)
    out = run(exe, "consume", name)
    assert fields(out, "READ")[0] == ["1", "12.5", "3.25"] and fields(out, "GET")[0] == ["1", "12.5"] and fields(out, "STALE")[0] == ["0", "inf"]


def test_c_consumer_reads_the_experiments_seqblock_writer(exe):
    name = nm()
    b = SeqBlock(name, 3, create=True)
    b.write([0.0, 7.0, 6.5])
    out = run(exe, "consume", name)
    assert fields(out, "READ")[0] == ["0", "7", "6.5"] and fields(out, "GET")[0] == ["0", "7"]


def test_c_producer_is_read_by_the_python_consumer_and_the_experiments_reader(exe):
    name = nm()
    proc = subprocess.Popen([str(exe), "produce", name, "3000"], stdout=subprocess.PIPE, text=True)
    try:
        assert proc.stdout.readline().strip() == "READY"
        assert sh.Consumer(name).read() == (1.0, 12.5, 3.25)
        assert SeqBlock(name, 3, create=False).read() == (1.0, 12.5, 3.25)
    finally:
        proc.kill(); proc.wait()


def test_c_consumer_rejects_a_missing_block_and_a_geometry_mismatch(exe):
    r = subprocess.run([str(exe), "consume", nm()], capture_output=True, text=True, timeout=30)
    assert r.returncode == 3 and "OPEN_FAILED 1" in r.stdout
    name = nm()
    keep = SeqBlock(name, 5, create=True)                                                   # keep a reference: a named mapping dies with its last handle
    assert keep.nfields == 5
    r = subprocess.run([str(exe), "consume", name], capture_output=True, text=True, timeout=30)
    assert r.returncode == 3 and "OPEN_FAILED 3" in r.stdout


def test_no_torn_read_with_a_c_writer_and_a_python_reader(exe):
    name = nm()
    proc = subprocess.Popen([str(exe), "stress_produce", name, "1500"], stdout=subprocess.PIPE, text=True)
    try:
        assert proc.stdout.readline().strip() == "READY"
        c = sh.Consumer(name)
        ok = bad = 0
        t_end = time.time() + 1.0
        while time.time() < t_end:
            v = c.read()
            if v is None:
                continue
            ok += 1
            if not (abs(v[2] - (v[1] - 5.0)) < 1e-9 and v[0] == (round(v[1] / 10.0) % 2)):
                bad += 1
        assert ok > 100 and bad == 0, (ok, bad)
    finally:
        proc.kill(); proc.wait()


def test_no_torn_read_with_a_python_writer_and_a_c_reader(exe):
    name = nm()
    p = sh.Producer(name)
    p.publish(1, 10.0, 5.0)
    stop = threading.Event()

    def writer():
        k = 0
        while not stop.is_set():
            k += 1
            p.publish(k % 2, k * 10.0, k * 10.0 - 5.0)

    th = threading.Thread(target=writer, daemon=True)
    th.start()
    try:
        out = run(exe, "stress_consume", name, 1000)
    finally:
        stop.set(); th.join(2)
    ok, torn, failed = [int(x) for x in out[0].split()[1::2]]
    assert ok > 100 and torn == 0, out[0]


def test_header_compiles_as_cpp_and_round_trips_in_process(tmp_path):
    e = tmp_path / "test_slackhint_cpp.exe"
    build(tmp_path, ROOT / "tests" / "cpp" / "test_slackhint_cpp.cpp", e, extra=INC)
    subprocess.run([str(e)], capture_output=True, timeout=120)                              # warm
    r = subprocess.run([str(e)], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0 and "OK" in r.stdout, r.stdout
