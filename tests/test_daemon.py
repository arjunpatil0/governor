"""Telemetry daemon (telemetry/daemon.py), observation builder (telemetry/obs_builder.py), actuator wiring (actuators/control.py) and the governor loop (controllers/runtime.py).
All on fake sources/actuators: no GPU, no admin. Instruction: "Proceed to the telemetry daemon, llama_governed driver and admin clock helper (/security-scan), test-first, no GPU"."""
import csv
import time
import uuid
from pathlib import Path

import numpy as np
import pytest

from actuators.control import ControlActuator
from controllers.pi import PIController
from controllers.runtime import Governor
from sim.params import load_params
from sim.plant import Action
from telemetry.daemon import Daemon
from telemetry.obs_builder import ObsBuilder
from telemetry.ring import SeqBlock, SharedRing

ROOT = Path(__file__).resolve().parents[1]
PERIOD = 1000.0 / 60.0


@pytest.fixture(scope="module")
def P():
    return load_params(ROOT)


def nm():
    return "Local\\gov_test_" + uuid.uuid4().hex


# ---------------------------------------------------------------- observation builder
def test_obs_builder_turns_ring_records_into_the_controller_observation():
    ob = ObsBuilder(PERIOD, PERIOD)
    frames = np.array([[0.000, 0.0005, 0.007], [0.0167, 0.0170, 0.0240], [0.0333, 0.0335, 0.0535]])        # QPC s: sched, start, end
    o = ob.build(frames, n_tokens=2, energy_j=5.0, dt_s=0.1, clock_mhz=1800.0, t_ms=100.0)
    assert o.lat_ms.tolist() == pytest.approx([7.0, 7.3, 20.2]) and o.n_missed == 1 and o.n_arrived == 3 and o.tokens == 2
    assert o.power_w == pytest.approx(50.0) and o.clock_mhz == 1800.0 and o.t_ms == 100.0 and o.period_ms == PERIOD


def test_obs_builder_handles_an_empty_tick():
    o = ObsBuilder(PERIOD, PERIOD).build(np.empty((0, 3)), 0, 0.0, 0.1, 1500.0, 200.0)
    assert len(o.lat_ms) == 0 and o.n_arrived == 0 and o.n_missed == 0 and o.power_w == 0.0


# ---------------------------------------------------------------- daemon
class FakeSrc:
    """Value changes every `every` calls, like NVML power (22 ms) vs temperature (1.8 s)."""
    def __init__(self, every):
        self.n, self.every = 0, every

    def __call__(self):
        self.n += 1
        return dict(v=float(self.n // self.every))


def test_daemon_logs_monotone_qpc_rows_with_age_and_changed_flags(tmp_path):
    out = tmp_path / "t.csv"
    d = Daemon({"fast": FakeSrc(1), "slow": FakeSrc(5)}, period_s=0.05, path=out, header={"execution_mode": "fake"})
    d.run(duration_s=1.5)
    rows = list(csv.DictReader(l for l in out.read_text().splitlines() if not l.startswith("#")))
    t = np.array([float(r["t_qpc_s"]) for r in rows])
    assert len(rows) >= 25 and np.all(np.diff(t) > 0) and abs(np.median(np.diff(t)) - 0.05) < 0.01
    assert [r["fast_changed"] for r in rows[1:6]] == ["1"] * 5
    assert sum(r["slow_changed"] == "1" for r in rows[1:]) < len(rows) / 3
    ages = np.array([float(r["slow_age_ms"]) for r in rows])
    assert ages.max() >= 100 and ages.min() < 20                     # grows between changes, resets at each change
    assert "# execution_mode=fake" in out.read_text().splitlines()[0]
    assert d.stats["rows"] == len(rows) and d.stats["dropped_rows"] == 0


def test_daemon_loop_is_not_stalled_by_a_slow_disk(tmp_path):
    slow = lambda: time.sleep(0.03)                                   # noqa: E731  sink stall per row
    d = Daemon({"x": FakeSrc(1)}, period_s=0.05, path=tmp_path / "s.csv", write_hook=slow, queue_max=4)
    d.run(duration_s=1.5)
    assert d.stats["dropped_rows"] > 0 or d.stats["rows"] >= 25     # either the queue absorbed it or rows were counted as dropped, never a stalled loop
    assert d.stats["loop_late_p99_ms"] < 25


def test_daemon_reports_ring_overflow_as_a_drop_count(tmp_path):
    ring = SharedRing(nm(), 4, 3, create=True)
    for i in range(10):
        ring.push([i, i, i])
    d = Daemon({}, period_s=0.05, path=tmp_path / "r.csv", rings={"frames": ring})
    d.run(duration_s=0.2)
    assert d.stats["ring_dropped"]["frames"] == 6


# ---------------------------------------------------------------- actuators and the governor loop
class FakeClock:
    def __init__(self):
        self.calls = []

    def lock(self, mhz):
        self.calls.append(("lock", mhz)); return True

    def reset(self):
        self.calls.append(("reset",)); return True

    def heartbeat(self):
        self.calls.append(("hb",)); return True


def test_control_actuator_writes_the_control_block_and_maps_unlocked_to_reset(P):
    blk, clk = SeqBlock(nm(), 3, create=True), FakeClock()
    act = ControlActuator(blk, clk, unlocked_mhz=P.UNLOCKED_MHZ)
    act.apply(Action(clock=1500.0, pacing="aligned", duty=1.0, guard_ms=0.7))
    assert SeqBlock(blk.name, 3, create=False).read() == (1.0, 1.0, 0.7)               # pacing code (1 = aligned), duty, guard_ms
    act.apply(Action(clock=1500.0, pacing="unaligned", duty=0.3))
    assert SeqBlock(blk.name, 3, create=False).read()[0] == 0.0
    act.apply(Action(clock=P.UNLOCKED_MHZ, pacing="unaligned", duty=0.3))
    assert [c for c in clk.calls if c[0] != "hb"] == [("lock", 1500), ("reset",)]       # unchanged clock is not re-sent
    assert ("hb",) in clk.calls


def test_governor_loop_runs_the_unchanged_controller_on_ring_data(P):
    frames, tokens, ctl = SharedRing(nm(), 64, 3, create=True), SharedRing(nm(), 64, 1, create=True), SeqBlock(nm(), 3, create=True)
    clk = FakeClock()
    gov = Governor(PIController(P, "unaligned"), ObsBuilder(PERIOD, PERIOD), ControlActuator(ctl, clk, unlocked_mhz=P.UNLOCKED_MHZ),
                   frame_ring=SharedRing(frames.name, 64, 3, create=False), token_ring=SharedRing(tokens.name, 64, 1, create=False),
                   period_ms=PERIOD, deadline_ms=PERIOD)
    gov.start(t_ms=0.0)
    d0 = SeqBlock(ctl.name, 3, create=False).read()[1]
    t = 0.0
    for k in range(10):                                              # 10 ticks of frames that finish late (20 ms > 16.7 ms deadline)
        for j in range(6):
            frames.push([t / 1000 + j * 0.0167, t / 1000 + j * 0.0167 + 0.001, t / 1000 + j * 0.0167 + 0.020])
        t += 100.0
        gov.step(t_ms=t, energy_j=5.0, clock_mhz=1800.0)
    assert SeqBlock(ctl.name, 3, create=False).read()[1] < d0 and gov.last_obs.n_missed > 0
