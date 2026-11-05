"""Python binding of the frame-slack hint protocol (python/slackhint; spec docs/SPEC_FRAME_SLACK_HINTS.md). No GPU, no compiler.
Instruction (Arjun): "Extract a small library: include/slackhint.h ... and a Python binding, with tests." """
import math
import struct
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


def nm():
    return "Local\\slackhint_py_" + uuid.uuid4().hex


def test_wire_format_is_the_existing_seqblock_in_both_directions():
    name = nm()
    p = sh.Producer(name)
    p.publish(True, 12.5, 3.25)
    assert SeqBlock(name, 3, create=False).read() == (1.0, 12.5, 3.25)            # producer -> the experiments' reader
    name2 = nm()
    b = SeqBlock(name2, 3, create=True)
    b.write([0.0, 7.0, 6.5])
    assert sh.Consumer(name2).read() == (0.0, 7.0, 6.5)                           # the experiments' writer -> consumer
    assert struct.unpack_from("<QQ", p.mm, 0) == (2, 3)                            # seq even after one publish, nfields 3


def test_consumer_refuses_a_geometry_mismatch():
    name = nm()
    SeqBlock(name, 5, create=True)
    with pytest.raises(ValueError):
        sh.Consumer(name)


def test_never_written_block_means_app_idle():
    name = nm()
    p = sh.Producer(name)                                                          # keep a reference: a named mapping dies with its last handle
    c = sh.Consumer(name)
    assert p.name == name and c.read() is None
    assert c.get(now=100.0) == (False, math.inf)


def test_producer_helpers_publish_the_documented_records():
    name = nm()
    p, c = sh.Producer(name), sh.Consumer(name)
    p.frame_started(1.0, 1.5)
    assert c.read() == (1.0, 1.5, 1.0)
    p.frame_done(1.2, 1.6)
    assert c.read() == (0.0, 1.6, 1.2)
    p.idle(2.0)
    assert c.read() == (0.0, math.inf, 2.0)


def test_a_record_older_than_the_stale_limit_means_app_idle_and_the_limit_is_inclusive():
    name = nm()
    p, c = sh.Producer(name), sh.Consumer(name)
    p.publish(True, 5.0, now=10.0)
    assert c.get(now=10.05) == (True, 5.0)
    assert c.get(now=10.125, stale_s=0.125) == (True, 5.0)                         # exactly at the limit (binary-exact numbers): still fresh
    assert c.get(now=10.2) == (False, math.inf)                                    # older than 100 ms (default limit)


def test_a_failed_read_keeps_the_last_good_value_it_is_not_idle():
    """journal 0041: the legacy policy treated a failed read (writer mid-write) as 'fg idle, next arrival = +inf'."""
    name = nm()
    p, c = sh.Producer(name), sh.Consumer(name)
    p.publish(True, 5.0, now=10.0)
    assert c.get(now=10.01) == (True, 5.0)
    seq = struct.unpack_from("<Q", p.mm, 0)[0]
    struct.pack_into("<Q", p.mm, 0, seq + 1)                                       # a writer stuck mid-write: seq odd, every retry fails
    assert c.read() is None
    assert c.get(now=10.02) == (True, 5.0)                                         # last good value, NOT (False, inf)
    assert c.get(now=10.2) == (False, math.inf)                                    # but a last good value gone stale is idle


def test_fit_rule_boundaries():
    assert sh.may_start(now=0.0, busy=False, estimate_s=0.010, guard_s=0.001, next_deadline_s=0.011)             # ends exactly guard before the deadline
    assert not sh.may_start(now=0.0, busy=False, estimate_s=0.010, guard_s=0.001, next_deadline_s=0.0109)
    assert not sh.may_start(now=0.0, busy=True, estimate_s=0.001, guard_s=0.0, next_deadline_s=math.inf)         # busy blocks even with infinite slack
    assert sh.may_start(now=0.0, busy=False, estimate_s=10.0, guard_s=1.0, next_deadline_s=math.inf)             # idle app: free run
    assert not sh.may_start(now=0.0, busy=False, estimate_s=0.0101, guard_s=0.0, next_deadline_s=0.0100)         # a unit larger than the slack never starts


def test_duty_wake():
    assert sh.duty_wake(1.0, 2.0, 0.0) == math.inf and sh.duty_wake(1.0, 2.0, -1.0) == math.inf
    assert sh.duty_wake(1.0, 2.0, 1.0) == 2.0 and sh.duty_wake(1.0, 2.0, 1.5) == 2.0
    assert sh.duty_wake(1.0, 2.0, 0.5) == pytest.approx(3.0)                       # duty 0.5: gap = duration
    assert sh.duty_wake(0.0, 0.01, 0.25) == pytest.approx(0.04)


def test_stretched_units_do_not_inflate_the_clean_estimate_but_lift_the_ewma():
    e = sh.Estimator()
    for _ in range(8):
        e.push(0.0101, False)
    base = e.value()
    e.push(0.0207, True)                                                           # one unit stretched by a frame (about 2x)
    assert e.value() == pytest.approx(base) and e.ewma() > 0.0105
    assert e.clean() == pytest.approx(0.0101)


def test_estimator_falls_back_to_the_ewma_until_a_clean_unit_exists():
    e = sh.Estimator()
    assert e.value() == 0.0 and math.isnan(e.clean())
    e.push(0.02, True)
    assert e.value() == pytest.approx(0.02)
    e.push(0.01, False)
    assert e.value() == pytest.approx(0.01)


def test_unit_overlap_rule():
    assert sh.unit_overlapped(t1_s=1.02, next_at_start_s=1.01, t0_s=1.0, have=True, updated_s=0.0)
    assert not sh.unit_overlapped(t1_s=1.005, next_at_start_s=1.01, t0_s=1.0, have=True, updated_s=0.0)
    assert sh.unit_overlapped(t1_s=1.02, next_at_start_s=math.inf, t0_s=1.0, have=True, updated_s=1.01)           # the app published during an idle-start unit
    assert not sh.unit_overlapped(t1_s=1.02, next_at_start_s=math.inf, t0_s=1.0, have=True, updated_s=0.5)
    assert not sh.unit_overlapped(t1_s=1.02, next_at_start_s=math.inf, t0_s=1.0, have=False, updated_s=0.0)


def test_time_base_is_the_experiments_qpc_timeline():
    assert abs(sh.now_s() - time.perf_counter()) < 0.01


def test_a_reader_never_sees_a_torn_record_while_a_writer_runs():
    """Invariant of every published record: updated = next - 5, busy = parity of next/10. A torn read would mix two records."""
    name = nm()
    p, c = sh.Producer(name), sh.Consumer(name)
    stop = threading.Event()

    def writer():
        k = 0
        while not stop.is_set():
            k += 1
            p.publish(k % 2, k * 10.0, k * 10.0 - 5.0)

    th = threading.Thread(target=writer, daemon=True)
    th.start()
    ok = bad = 0
    t_end = time.time() + 1.0
    while time.time() < t_end:
        v = c.read()
        if v is None:
            continue
        ok += 1
        if not (abs(v[2] - (v[1] - 5.0)) < 1e-9 and v[0] == (round(v[1] / 10.0) % 2)):
            bad += 1
    stop.set(); th.join(2)
    assert ok > 100 and bad == 0, (ok, bad)
