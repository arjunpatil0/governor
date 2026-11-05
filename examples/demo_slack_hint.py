"""Demo of the frame-slack hint protocol, no GPU, no admin rights: a 60 Hz 'foreground app' (spin-loop frames) publishes hints; a 'background worker' (spin-loop work units) starts a unit
only if it fits the slack (python/slackhint). ILLUSTRATION ONLY: Python spin loops on a shared CPU, not a measurement; nothing printed here is a result of this project.
   python examples/demo_slack_hint.py                      (both modes, 3 s each)
   python examples/demo_slack_hint.py --frame-ms 9 --unit-ms 10   (a unit larger than the slack: once the app publishes, the hinted worker starts nothing (the few units it runs are the ones before the first frame, while the app is idle); the free worker overlaps frames)
Modes: hinted = the consumer rule (now + estimate + guard <= next deadline, app not busy); free = ignore the hints (back-to-back units)."""
import argparse
import subprocess
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))
import slackhint as sh  # noqa: E402

PERIOD = 1.0 / 60.0


def spin_until(t):
    while True:
        r = t - sh.now_s()
        if r <= 0:
            return
        if r > 0.003:
            time.sleep(r - 0.002)


def producer(name, seconds, frame_s):
    """The app: busy published 1 ms before each frame (lead), frame_done with the next deadline when the frame completes."""
    p = sh.Producer(name)
    t0 = sh.now_s() + 0.3
    k = 0
    while sh.now_s() < t0 + seconds + 0.3:
        ts = t0 + k * PERIOD
        spin_until(ts - 0.001)
        p.frame_started(sh.now_s(), ts + PERIOD)
        spin_until(ts)
        spin_until(ts + frame_s)
        p.frame_done(sh.now_s(), ts + PERIOD)
        k += 1
    p.idle(sh.now_s())


def consumer(name, seconds, unit_s, guard_s, hinted):
    c = sh.Consumer(name)
    est = sh.Estimator()
    units = late = while_busy = 0
    t_end = sh.now_s() + 0.35 + seconds
    while sh.now_s() < t_end:
        now = sh.now_s()
        busy, nxt = c.get(now)
        if hinted and not sh.may_start(now, busy, est.value(), guard_s, nxt):
            continue
        t0 = sh.now_s()
        spin_until(t0 + unit_s)
        t1 = sh.now_s()
        ov = sh.unit_overlapped(t1, nxt, t0, c.have, c.last[2])
        est.push(t1 - t0, ov)
        units += 1
        late += t1 > nxt                           # ended after the next deadline it was gated against
        while_busy += bool(busy)
    return units, late, while_busy


def run_mode(hinted, args):
    name = "Local\\slackhint_demo_" + uuid.uuid4().hex
    proc = subprocess.Popen([sys.executable, __file__, "--role", "producer", "--name", name, "--seconds", str(args.seconds), "--frame-ms", str(args.frame_ms)])
    t_wait = time.time() + 5
    while True:                                    # wait for the producer to create the block
        try:
            res = consumer(name, args.seconds, args.unit_ms / 1000.0, args.guard_ms / 1000.0, hinted)
            break
        except ValueError:
            if time.time() > t_wait:
                raise
            time.sleep(0.05)
    proc.wait(timeout=30)
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--role", default="demo")
    ap.add_argument("--name"); ap.add_argument("--seconds", type=float, default=3.0)
    ap.add_argument("--frame-ms", type=float, default=6.0); ap.add_argument("--unit-ms", type=float, default=4.0); ap.add_argument("--guard-ms", type=float, default=1.0)
    a = ap.parse_args()
    if a.role == "producer":
        return producer(a.name, a.seconds, a.frame_ms / 1000.0)
    print(f"frame {a.frame_ms} ms at 60 Hz (slack {1000 * PERIOD - a.frame_ms:.2f} ms), work unit {a.unit_ms} ms, guard {a.guard_ms} ms, {a.seconds} s per mode (illustration, not a measurement)")
    for hinted in (True, False):
        units, late, busy = run_mode(hinted, a)
        print(f"{'hinted' if hinted else 'free  '}: units started {units:5d}, ended after the next deadline {late:5d}, started while the app was busy {busy:5d}")


if __name__ == "__main__":
    main()
