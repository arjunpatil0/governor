"""Pure helpers for the W2 co-location experiments (no GPU, no I/O): slice/arrival generation, latency, residual-wait.
Tested in tests/test_loadgen.py. Times are seconds unless a name says _ms."""
import re

import numpy as np


def gamma_slice_durations(n, mean_ms, cv, seed):
    """n slice durations (ms) with the given mean and coefficient of variation; cv == 0 gives constant slices."""
    if n < 1 or mean_ms <= 0 or cv < 0:
        raise ValueError(f"bad slice spec n={n} mean_ms={mean_ms} cv={cv}")
    if cv == 0:
        return np.full(n, float(mean_ms))
    shape = 1.0 / cv ** 2
    return np.random.default_rng(seed).gamma(shape, mean_ms / shape, n)


def poisson_arrivals(rate_hz, n, seed, t0=0.0):
    """Absolute arrival times (s) of a Poisson process: t0 + cumulative exponential gaps."""
    if rate_hz <= 0 or n < 1:
        raise ValueError(f"bad arrival spec rate_hz={rate_hz} n={n}")
    return t0 + np.cumsum(np.random.default_rng(seed).exponential(1.0 / rate_hz, n))


def latencies(arrivals, completions):
    """completion - SCHEDULED arrival, so a request delayed behind a late one carries its queueing time."""
    a, c = np.asarray(arrivals, float), np.asarray(completions, float)
    if a.shape != c.shape:
        raise ValueError(f"{a.size} arrivals vs {c.size} completions")
    lat = c - a
    if np.any(lat < 0):
        raise ValueError("completion before scheduled arrival: broken clock or log")
    return lat


def residual_wait(starts, ends):
    """Residual-wait prediction from logged background slices [start, end) (one stream, so non-overlapping).
    rho = busy / wall, residual = E[S^2] / (2 E[S]), predicted = rho * residual (journal 0004, 0008 mod A.1);
    gap_* are the idle times between consecutive slices."""
    s, e = np.asarray(starts, float), np.asarray(ends, float)
    if s.size == 0 or s.shape != e.shape:
        raise ValueError("need matching, non-empty start/end arrays")
    d = e - s
    if np.any(d <= 0):
        raise ValueError("zero or negative slice duration")
    gaps = s[1:] - e[:-1]
    if np.any(gaps < -1e-12):
        raise ValueError("overlapping slices")
    gaps = np.maximum(gaps, 0.0)
    wall = e[-1] - s[0]
    residual = float((d ** 2).mean() / (2 * d.mean()))
    rho = float(d.sum() / wall)
    return dict(n_slices=int(d.size), rho=rho, mean_s=float(d.mean()), residual_s=residual, predicted_s=rho * residual,
                gap_mean_s=float(gaps.mean()) if gaps.size else 0.0,
                gap_p50_s=float(np.percentile(gaps, 50)) if gaps.size else 0.0,
                gap_p99_s=float(np.percentile(gaps, 99)) if gaps.size else 0.0)


def parse_hags(dxdiag_text, adapter="NVIDIA"):
    """The 'Hardware Scheduling' line of the first display adapter whose 'Card name' contains `adapter`."""
    card = None
    for line in dxdiag_text.splitlines():
        line = line.strip()
        m = re.match(r"Card name:\s*(.+)", line)
        if m:
            card = m.group(1)
            continue
        m = re.match(r"Hardware Scheduling:\s*(.+)", line)
        if m and card and adapter in card:
            val = m.group(1).strip()
            en = re.search(r"Enabled:(True|False)", val)
            if not en:
                raise ValueError(f"no Enabled flag in {val!r}")
            return {"adapter": card, "line": val, "enabled": en.group(1) == "True"}
    raise ValueError(f"no 'Hardware Scheduling' line for an adapter matching {adapter!r}")
