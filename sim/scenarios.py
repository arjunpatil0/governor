"""Scenario builders for the simulator study, fixed by docs/W45_SIM_PROTOCOL.md (written before any controller ran).
fg: synthetic frame-paced FMA frame, 60 Hz periodic, deadline = period; bg: llama.cpp decode tokens (L)."""
import numpy as np

from sim.plant import BgSpec, FgSpec, Scenario

C0_MS = 7.0                      # base fg cost at 1800 MHz (protocol)
SIGMA = 0.03                     # frame jitter (ASSUMPTION, protocol)
PERIOD_MS = 1000.0 / 60.0
SCENARIOS = ("S0", "S1", "S1d", "S2", "S3", "S4")
_STEPS = (1.0, 0.7, 1.3, 0.7, 1.0, 1.3)


def _factor(name):
    if name in ("S1", "S4"):
        return lambda t: _STEPS[min(int(t // 10000.0), len(_STEPS) - 1)]
    if name == "S1d":
        return lambda t: 0.7 + 0.6 * min(max(t / 60000.0, 0.0), 1.0)
    return lambda t: 1.0


def build(name, duration_ms=60000.0, jitter=False):
    if name not in SCENARIOS:
        raise ValueError(name)
    f = _factor(name)
    active = (lambda t: (t < 20000.0) or (30000.0 <= t < 50000.0)) if name == "S2" else (lambda t: True)
    fg = FgSpec(period_ms=PERIOD_MS, arrivals="periodic", cost_ms=lambda t: C0_MS * f(t), jitter_sigma=SIGMA, deadline_ms=PERIOD_MS, active=active)
    return Scenario(name=name, duration_ms=duration_ms, fg=fg, bg=BgSpec(kind="llama", jitter=jitter), warmup_ms=5000.0,
                    clock_cap=[(30000.0, 1500.0)] if name == "S3" else None, interaction=0.5 if name == "S4" else 0.0)
