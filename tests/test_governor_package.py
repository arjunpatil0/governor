"""The importable package python/governor (FrameHintWriter, FrameHintReader, DeadlineGate): thin wrappers over python/slackhint, so the tests check that the names exist, that the wire format is
the slackhint one, and that the gate's decisions equal the library rules it composes. No GPU.
Instruction (Arjun, 2026-11-07): "Make the gate + hint importable: a minimal package (e.g. governor/ with pyproject.toml) exposing FrameHintWriter, FrameHintReader, DeadlineGate. No new features." """
import math
import sys
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
import governor  # noqa: E402
import slackhint as sh  # noqa: E402
from governor import DeadlineGate, FrameHintReader, FrameHintWriter  # noqa: E402


def nm():
    return "Local\\gov_test_pkg_" + uuid.uuid4().hex


def test_public_names_and_wire_compatibility_with_slackhint():
    assert set(governor.__all__) >= {"FrameHintWriter", "FrameHintReader", "DeadlineGate"}
    name = nm()
    w = FrameHintWriter(name, create=True)
    w.frame_started(5.0, 5.0167)
    assert sh.Consumer(name).read() == (1.0, 5.0167, 5.0)                      # a plain slackhint consumer reads the writer's record
    assert FrameHintReader(name).get(5.01) == (True, 5.0167)
    w.frame_done(5.004, 5.0167)
    assert FrameHintReader(name).get(5.005) == (False, 5.0167)
    w.idle(5.01)
    assert FrameHintReader(name).get(5.011) == (False, math.inf)
    with pytest.raises(ValueError):
        FrameHintReader(nm())                                                  # no writer: geometry mismatch, no silent fallback


def test_gate_starts_a_unit_only_where_it_fits_and_learns_the_unit_time():
    name = nm()
    w, r = FrameHintWriter(name, create=True), FrameHintReader(name)
    gate = DeadlineGate(r, guard_s=0.0005)
    w.frame_done(10.000, 10.0167)                                              # app idle until 10.0167
    assert gate.may_start(10.001)                                              # estimate 0.0: everything fits
    assert gate.unit_done(10.001, 10.0111) is False                            # a 10.0 ms unit that ended before the deadline: clean
    assert gate.estimate_s() == pytest.approx(0.0101, abs=1e-9)
    w.frame_done(10.0167 + 0.004, 10.0334)                                     # next frame done 4 ms after its start
    assert gate.may_start(10.0207)                                             # 10.0207 + 0.0101 + 0.0005 = 10.0313 <= 10.0334
    assert gate.unit_done(10.0207, 10.0308) is False
    assert not gate.may_start(10.0300)                                         # 10.0300 + 0.0101 + 0.0005 > 10.0334: does not fit
    w.frame_started(10.0324, 10.05)                                            # app busy
    assert not gate.may_start(10.0330)


def test_gate_decisions_equal_the_library_rule_and_overlap_is_reported():
    name = nm()
    w, r = FrameHintWriter(name, create=True), FrameHintReader(name)
    gate = DeadlineGate(r, guard_s=0.001, duty=0.5)
    w.frame_done(20.0, 20.0167)
    assert gate.may_start(20.0) == sh.may_start(20.0, False, 0.0, 0.001, 20.0167)
    assert gate.unit_done(20.0, 20.012) is False
    assert gate.wake_s == pytest.approx(sh.duty_wake(20.0, 20.012, 0.5))      # duty 0.5: gap equal to the unit
    assert not gate.may_start(20.015)                                          # inside the duty gap
    w.frame_done(20.03, 20.05)
    assert gate.may_start(20.03)
    assert gate.unit_done(20.03, 20.06) is True                                # ended after the deadline it was gated against: overlapped
    assert gate.estimate_s() == pytest.approx(0.012)                           # the overlapped unit does not enter the clean median
