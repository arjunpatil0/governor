"""Pure pacing decisions (ms timeline). Single source of truth for the plant (sim/plant.py) and the reference for the C++ mirror
workloads/background/pacing.h used by the governed llama.cpp driver; tests/test_pacing_cpp.py compares the two on golden cases."""
import math

EPS = 1e-9


def unaligned_wake(t_start, t_end, duty):
    """Duty cycle: after a token, sleep measured_token_time * (1/duty - 1) (as the A2 DLL bg_loop). duty <= 0: never; duty >= 1: no gap."""
    if duty <= 0.0:
        return math.inf
    if duty >= 1.0:
        return t_end
    return t_end + (t_end - t_start) * (1.0 / duty - 1.0)


def aligned_may_start(now, fg_busy, tok_est, guard, next_arrival):
    """Slack-filling: start a token only while no fg frame is queued/running and it is expected to finish guard ms before the next fg arrival
    (next_arrival = inf when no frame is expected soon, i.e. the fg is idle)."""
    return (not fg_busy) and (now + tok_est + guard <= next_arrival + EPS)
