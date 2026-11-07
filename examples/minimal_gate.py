"""Minimal deadline gate, no GPU, no admin rights. Windows (the hint record is a named file mapping). Everything printed is simulated: an illustration of the mechanism, not a measurement.
   python examples/minimal_gate.py            (from the repository root; needs numpy and pandas; uses python/ on the path, so no install is needed)
Part 1 runs the plant simulator (sim/, parameters from the committed measurements) twice per frame cost on the same 60 fps scene and the same background LLM: tokens started back to back ("free") and tokens started
only where they fit before the next frame ("gated", the rule of the gate). Part 2 drives the importable gate (python/governor) in simulated time with a hint record in shared memory and checks that
every start decision equals the simulator's own rule (sim/pacing.py aligned_may_start)."""
import dataclasses
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "python"))

from governor import DeadlineGate, FrameHintReader, FrameHintWriter  # noqa: E402
from sim.pacing import aligned_may_start  # noqa: E402
from sim.params import load_params  # noqa: E402
from sim.plant import Action, Plant, _Static, summarise  # noqa: E402
from sim.scenarios import PERIOD_MS, build  # noqa: E402

CLOCK = 1800.0                    # MHz, the clock at which the nominal 7 ms frame cost is defined
GUARD_MS = 0.5                    # the guard the experiments started with


def part1_plant(params):
    print("Part 1: plant simulator, 20 s per run, 1800 MHz, constant frame cost, a 3B-class decode as the background (token 10.1 ms)")
    print(f"{'frame ms':<10}{'tokens start':<14}{'late frames %':>14}{'tokens/s':>10}")
    for cost in (4.0, 6.0, 7.0, 9.0):
        sc = build("S0", duration_ms=20000.0)
        sc.fg = dataclasses.replace(sc.fg, cost_ms=lambda t, c=cost: c)
        for label, mode in (("free", "unaligned"), ("gated", "aligned")):
            res = summarise(Plant(params, sc, seed=1).run(_Static(Action(clock=CLOCK, pacing=mode, duty=1.0, guard_ms=GUARD_MS))))
            print(f"{cost:<10.0f}{label:<14}{100.0 * res['miss_frac']:>14.2f}{res['bg_tok_s']:>10.1f}")
    print("The gate keeps frames on time at every cost. It also shows the slack cliff: once the frame leaves less room than a token (above about 6 ms here) it starts nothing.\n")


def part2_gate(params, seconds=2.0, frame_ms=4.0):
    name = "Local\\gov_example_" + uuid.uuid4().hex
    writer, reader = FrameHintWriter(name, create=True), FrameHintReader(name)
    gate = DeadlineGate(reader, guard_s=GUARD_MS / 1000.0)
    period, cost, tok = PERIOD_MS / 1000.0, frame_ms / 1000.0, 1.0 / params.tok_s(CLOCK)
    lead, dt, t0 = 0.001, 0.0002, 1000.0                 # the app publishes busy 1 ms before each frame; the worker polls every 0.2 ms of simulated time
    t, k, in_frame, unit_end, unit_start = t0, 0, False, None, None
    tokens = overlapped = mismatches = 0
    while t < t0 + seconds:
        ts = t0 + (k + 1) * period                       # the first frame is due one period after the start
        if not in_frame and t >= ts - lead:
            writer.frame_started(t, ts + period)
            in_frame = True
        if in_frame and t >= ts + cost:
            writer.frame_done(t, ts + period)
            in_frame, k = False, k + 1
        if unit_end is None:
            ok = gate.may_start(t)
            busy, nxt = reader.get(t)
            if ok != aligned_may_start(t * 1000.0, busy, gate.estimate_s() * 1000.0, GUARD_MS, nxt * 1000.0):
                mismatches += 1
            if ok:
                unit_start, unit_end = t, t + tok
        elif t >= unit_end:
            overlapped += gate.unit_done(unit_start, unit_end)
            tokens, unit_end = tokens + 1, None
        t += dt
    writer.idle(t)
    print(f"Part 2: the importable gate in simulated time, {seconds:.0f} s, frame cost {frame_ms:.0f} ms every {PERIOD_MS:.2f} ms, token {tok * 1000:.1f} ms")
    print(f"  tokens finished {tokens} ({tokens / (k or 1):.2f} per frame), tokens that overlapped a frame {overlapped}, decisions that differ from sim.pacing.aligned_may_start: {mismatches}")
    print("  Each token starts after a frame has finished and ends before the next one is due, so none overlaps a frame; the first token runs before the app has published anything (an unwritten record means idle).")
    return mismatches


if __name__ == "__main__":
    P = load_params(ROOT)
    part1_plant(P)
    sys.exit(1 if part2_gate(P) else 0)
