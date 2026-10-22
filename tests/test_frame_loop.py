"""Synthetic frame-paced foreground (workloads/foreground/frame_loop.py): periodic absolute schedule, cost and activity from the simulator scenarios (sim/scenarios.py), frame
records and pace block published through telemetry/fg_publisher.py. Tested with a fake frame runner (busy-wait of the requested cost): no GPU.
Instruction (2026-10-22): "Then build the foreground frame loop and draft the W5 yaml"."""
import time
import uuid

import numpy as np
import pytest

from sim.scenarios import build
from telemetry.fg_publisher import FramePublisher
from telemetry.ring import SeqBlock, SharedRing
from workloads.foreground.frame_loop import FrameLoop


def nm():
    return "Local\\gov_test_" + uuid.uuid4().hex


class FakeRunner:
    """Frame runner contract: run(cost_ms, t_sched_s) -> (t_launch_s, t_complete_s); waits for the scheduled time like the DLL, then occupies the 'GPU' for cost_ms."""
    def __init__(self, scale=1.0):
        self.costs, self.scale = [], scale

    def __call__(self, cost_ms, t_sched):
        while time.perf_counter() < t_sched:
            pass
        t0 = time.perf_counter()
        self.costs.append(cost_ms)
        while time.perf_counter() - t0 < cost_ms * self.scale / 1000.0:
            pass
        return t0, time.perf_counter()


def make(scn="S0", scale=1.0, **kw):
    sc = build(scn)
    ring, pace = SharedRing(nm(), 4096, 3, create=True), SeqBlock(nm(), 3, create=True)
    runner = FakeRunner(scale)
    loop = FrameLoop(sc.fg, runner, FramePublisher(ring, pace), **kw)
    return loop, runner, ring, pace


def test_frames_follow_an_absolute_60hz_schedule_and_publish_every_frame():
    loop, runner, ring, pace = make("S0")
    recs = loop.run(duration_s=1.0)
    assert 58 <= len(recs) <= 61
    t = np.array([r["t_sched"] for r in recs])
    assert np.allclose(np.diff(t), 1 / 60, atol=1e-9)
    assert np.median([r["lat_ms"] for r in recs]) == pytest.approx(7.0, abs=0.6)
    rec, _ = SharedRing(ring.name, 4096, 3, create=False).read_new()
    assert len(rec) == len(recs) and rec[0, 0] == pytest.approx(recs[0]["t_sched"])


def test_pace_block_goes_busy_just_before_a_frame_and_not_busy_with_the_next_arrival_after_it():
    loop, runner, ring, pace = make("S0")
    recs = loop.run(duration_s=0.3)
    busy, t_next, t_upd = pace.read()
    assert busy == 0.0 and t_next == pytest.approx(recs[-1]["t_sched"] + 1 / 60) and t_upd >= recs[-1]["t_end"] - 1e-3


def test_an_overloaded_frame_loop_keeps_the_schedule_and_shows_the_backlog_as_latency():
    loop, runner, ring, pace = make("S0", scale=25.0 / 7.0, grace_s=0.3)       # 25 ms frames at 60 Hz
    recs = loop.run(duration_s=1.0)
    lat = [r["lat_ms"] for r in recs if r["lat_ms"] == r["lat_ms"]]
    assert lat[-1] > lat[0] + 100 and loop.abandoned > 0 and len(recs) < 60       # never skips or re-times frames; whatever was not finished by duration + grace is abandoned


def test_frame_cost_comes_from_the_scenario_schedule():
    loop, runner, ring, pace = make("S1")
    loop.run(duration_s=0.2)
    assert runner.costs and all(c == pytest.approx(7.0) for c in runner.costs)        # S1: factor 1.0 during the first 10 s


def test_idle_phases_publish_idle_and_produce_no_frames(tmp_path):
    sc = build("S2")
    sc.fg.active = lambda t: t >= 200.0                                  # idle for the first 200 ms, then active
    ring, pace = SharedRing(nm(), 4096, 3, create=True), SeqBlock(nm(), 3, create=True)
    loop = FrameLoop(sc.fg, FakeRunner(), FramePublisher(ring, pace))
    recs = loop.run(duration_s=0.5)
    assert all(r["t_sched"] >= loop.t0 + 0.2 - 1e-9 for r in recs) and 15 <= len(recs) <= 20
