"""telemetry/ring.py: named shared-memory single-writer ring (frame / token records) and seqlock block (control / pace values) shared between Python and the C++ driver.
Instruction: "Proceed to the telemetry daemon, llama_governed driver and admin clock helper (/security-scan), test-first, no GPU"."""
import subprocess
import sys
import threading
import uuid

import numpy as np
import pytest

from telemetry.ring import SeqBlock, SharedRing


def nm():
    return "Local\\gov_test_" + uuid.uuid4().hex


def test_ring_returns_records_in_order_and_only_once():
    n = nm()
    w, r = SharedRing(n, 8, 3, create=True), SharedRing(n, 8, 3, create=False)
    for i in range(5):
        w.push([i, i * 10.0, i * 100.0])
    rec, dropped = r.read_new()
    assert dropped == 0 and rec.shape == (5, 3) and rec[:, 0].tolist() == [0, 1, 2, 3, 4] and rec[2].tolist() == [2.0, 20.0, 200.0]
    rec, dropped = r.read_new()
    assert rec.shape == (0, 3) and dropped == 0
    w.push([9, 9, 9])
    rec, _ = r.read_new()
    assert rec[:, 0].tolist() == [9]


def test_ring_overflow_keeps_the_newest_records_and_counts_the_dropped_ones():
    n = nm()
    w, r = SharedRing(n, 4, 1, create=True), SharedRing(n, 4, 1, create=False)
    for i in range(10):
        w.push([float(i)])
    rec, dropped = r.read_new()
    assert dropped == 6 and rec[:, 0].tolist() == [6.0, 7.0, 8.0, 9.0]


def test_reader_geometry_comes_from_the_writer_header():
    n = nm()
    w = SharedRing(n, 16, 2, create=True)
    r = SharedRing(n, 16, 2, create=False)
    assert r.capacity == 16
    with pytest.raises(ValueError):
        SharedRing(n, 8, 2, create=False)            # wrong geometry is rejected, not silently misread


def test_seqblock_roundtrip_and_never_returns_a_torn_value():
    n = nm()
    w, r = SeqBlock(n, 4, create=True), SeqBlock(n, 4, create=False)
    assert r.read() is None                           # nothing written yet
    w.write([1.0, 2.0, 3.0, 4.0])
    assert r.read() == (1.0, 2.0, 3.0, 4.0)
    stop = threading.Event()

    def hammer():
        k = 0.0
        while not stop.is_set():
            k += 1.0
            w.write([k, k, k, k])

    t = threading.Thread(target=hammer, daemon=True)
    t.start()
    try:
        for _ in range(20000):
            v = r.read()
            assert v is None or len(set(v)) == 1
    finally:
        stop.set(); t.join(2)


def test_ring_is_readable_from_another_process():
    n = nm()
    w = SharedRing(n, 8, 2, create=True)
    code = ("import sys; sys.path.insert(0, %r); from telemetry.ring import SharedRing; r = SharedRing(%r, 8, 2, create=False); rec, d = r.read_new(); "
            "print(rec.shape[0], rec[-1, 1] if len(rec) else -1)") % (str(__import__("pathlib").Path(__file__).resolve().parents[1]), n)
    w.push([1.0, 11.0]); w.push([2.0, 22.0])
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=30).stdout.split()
    assert out == ["2", "22.0"]
