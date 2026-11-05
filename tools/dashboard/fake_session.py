"""SYNTHETIC live session for trying the dashboard's LIVE mode without the GPU, the helper or a model. NOT a measurement and NOT hardware: a thread publishes 60 Hz frames (6-9 ms, a few late) and tokens into freshly created
shared-memory rings, and the REAL HybridController (d'B) runs in the REAL Governor loop on them (10 Hz) with decision telemetry on. Writes the session registry (default data/dashboard_live/session.json) with synthetic = true, so the page
labels it 'SYNTHETIC test feed' and never as the real GPU; removes the registry at the end.
   python tools/dashboard/fake_session.py --seconds 60        then open the dashboard (python tools/dashboard/server.py) and pick LIVE"""
import argparse
import json
import math
import os
import sys
import threading
import time
import uuid
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(HERE))
PERIOD = 1.0 / 60.0
SESSION_FILE = ROOT / "data" / "dashboard_live" / "session.json"


class CtrlActuator:
    """Writes the commanded pacing to the control block like actuators/control.py, without a clock helper (there is no GPU here)."""

    def __init__(self, ctrl):
        self.ctrl = ctrl

    def apply(self, a):
        self.ctrl.write([1.0 if a.pacing == "aligned" else 0.0, float(a.duty), float(a.guard_ms)])


def run(seconds, session_file=SESSION_FILE, seed=1):
    from controllers.hybrid import HybridController
    from controllers.runtime import Governor
    from sim.params import load_params
    from telemetry.decision_block import DecisionBlock, DecisionPublisher
    from telemetry.fg_publisher import FramePublisher
    from telemetry.obs_builder import ObsBuilder
    from telemetry.ring import SeqBlock, SharedRing
    tag = uuid.uuid4().hex[:8]
    names = dict(frames="Local\\fake_fr_" + tag, tokens="Local\\fake_tk_" + tag, ctrl="Local\\fake_ct_" + tag, pace="Local\\fake_pc_" + tag, decision="Local\\fake_dc_" + tag, frames_capacity=8192, tokens_capacity=65536)
    frames, tokens = SharedRing(names["frames"], 8192, 3, True), SharedRing(names["tokens"], 65536, 2, True)
    ctrl, pace = SeqBlock(names["ctrl"], 3, True), SeqBlock(names["pace"], 3, True)
    dec = DecisionBlock(names["decision"], True)
    ctrl.write([1.0, 1.0, 0.5])
    P = load_params(ROOT)
    gov = Governor(HybridController(P, 59.08, safety=0.7, switch_gain=2.0, clock_every=20), ObsBuilder(PERIOD * 1000, PERIOD * 1000), CtrlActuator(ctrl),
                   SharedRing(names["frames"], 8192, 3, False), SharedRing(names["tokens"], 65536, 2, False), PERIOD * 1000, PERIOD * 1000, params=P, telemetry=DecisionPublisher(dec))
    gov.start(0.0)
    session = dict(names=names, pid=os.getpid(), id="synthetic_dB", scene="S1", controller="d'B", workload="llama32_3b", budget_w=60.0, demo=True, synthetic=True)
    session_file = Path(session_file)
    session_file.parent.mkdir(parents=True, exist_ok=True)
    session_file.write_text(json.dumps(session), encoding="utf-8")
    stop, rng = threading.Event(), np.random.default_rng(seed)
    pub = FramePublisher(frames, pace)

    def producer():
        t0 = time.perf_counter() + 0.1
        k = 0
        while not stop.is_set():
            ts = t0 + k * PERIOD
            while time.perf_counter() < ts - 0.001 and not stop.is_set():
                time.sleep(0.0005)
            cost = (0.5 + 0.5 * (1 + math.sin(k / 120.0))) * 0.003 + 0.0055 + (0.012 if rng.random() < 0.02 else 0.0)        # about 6-9 ms, an occasional 12 ms stretch
            pub.frame_started(time.perf_counter(), ts + PERIOD)
            while time.perf_counter() < ts + cost and not stop.is_set():
                time.sleep(0.0003)
            now = time.perf_counter()
            pub.frame_done(ts, max(ts, now - cost), now, ts + PERIOD, now)
            k += 1

    def toks():
        while not stop.is_set():
            time.sleep(0.010 + 0.003 * rng.random())
            tokens.push([time.perf_counter(), 10.0 + rng.random()])

    for fn in (producer, toks):
        threading.Thread(target=fn, daemon=True).start()
    t_end, tick = time.perf_counter() + seconds, time.perf_counter()
    clock = 1800.0
    try:
        while time.perf_counter() < t_end:
            tick += 0.1
            time.sleep(max(0.0, tick - time.perf_counter()))
            a = gov.step(time.perf_counter() * 1000.0, 0.0, clock, power_w=40.0 + 15.0 * rng.random())
            clock = float(min(a.clock, P.UNLOCKED_MHZ))
    finally:
        stop.set()
        try:
            session_file.unlink()
        except OSError:
            pass


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--seconds", type=float, default=60.0); ap.add_argument("--session-file", default=str(SESSION_FILE))
    a = ap.parse_args(argv)
    print(f"SYNTHETIC session for {a.seconds:.0f} s (no GPU; registry {a.session_file}); open the dashboard and pick LIVE", flush=True)
    run(a.seconds, a.session_file)


if __name__ == "__main__":
    main()
