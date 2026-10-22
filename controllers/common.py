"""Shared controller pieces: allowed clock levels, the L-table knee, rolling latency windows and idle detection."""
import sys
from collections import deque
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "analysis"))
from w2_stats import find_knee  # noqa: E402

MIN_CLOCK_MHZ = 900.0       # lowest level the governor uses (W1/B measured the fg down to 600; below 900 frames take more than 2x)
IDLE_TICKS = 5


def ALLOWED_CLOCKS(P):
    return tuple(f for f in P.levels if f >= MIN_CLOCK_MHZ)


def knee_clock(P):
    """Lowest L level with >= 95% of the unlocked decode throughput (journal 0027: 1500 MHz for llama.cpp Q4_K_M)."""
    return find_knee({k: v for k, v in P.rel_thr_L.items() if k != "unlocked"})


class Window:
    def __init__(self, n):
        self.d = deque(maxlen=n)

    def add(self, lat):
        self.d.append(np.asarray(lat, float))

    def lat(self):
        xs = [x for x in self.d if len(x)]
        return np.concatenate(xs) if xs else np.empty(0)

    def q(self, p):
        x = self.lat()
        return float(np.percentile(x, p)) if len(x) else float("nan")


class IdleDetector:
    def __init__(self, n=IDLE_TICKS):
        self.n, self.k = n, 0

    def update(self, obs):
        self.k = self.k + 1 if obs.n_arrived == 0 else 0
        return self.k >= self.n
