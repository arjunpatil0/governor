"""Smoke-2 analysis (analysis/smoke_overrun.py): how far past the next frame arrival does a background token end?
Instruction (Arjun + reviewer, 2026-10-22): "second ~20-min hardware smoke before W5a, recording token durations and overrun; diagnose the guard-0 overrun from the data".
Pure function, no GPU."""
import numpy as np

from analysis.smoke_overrun import overrun_stats

PERIOD = 1000.0 / 60.0


def frames(n, t0=0.0):
    return t0 + np.arange(n) * PERIOD / 1000.0


def test_token_inside_slack_has_no_overrun():
    f = frames(10)
    # token starts 2 ms after a frame arrival and runs 4 ms: ends well before the next arrival
    tok_end = np.array([f[2] + 0.006]); tok_ms = np.array([4.0])
    s = overrun_stats(f, tok_end, tok_ms, PERIOD)
    assert s["n"] == 1 and s["frac_overrun"] == 0.0 and s["overrun_ms_max"] <= 0.0


def test_token_past_next_arrival_is_measured_in_ms():
    f = frames(10)
    # starts 12 ms after arrival 2, runs 6 ms: ends 18 ms after arrival 2 = 1.333 ms past arrival 3
    tok_end = np.array([f[2] + 0.018]); tok_ms = np.array([6.0])
    s = overrun_stats(f, tok_end, tok_ms, PERIOD)
    assert s["frac_overrun"] == 1.0
    assert abs(s["overrun_ms_max"] - (18.0 - PERIOD)) < 1e-6


def test_start_is_end_minus_duration_and_picks_the_following_arrival():
    f = frames(10)
    # token that starts 1 ms before arrival 5 and lasts 3 ms: overrun 2 ms past arrival 5
    tok_end = np.array([f[5] + 0.002]); tok_ms = np.array([3.0])
    s = overrun_stats(f, tok_end, tok_ms, PERIOD)
    assert abs(s["overrun_ms_max"] - 2.0) < 1e-6


def test_percentiles_and_duration_summary_and_empty_input():
    f = frames(100)
    rng = np.random.default_rng(1)
    start = f[:90] + 0.001
    dur = rng.uniform(2.0, 5.0, size=90)
    s = overrun_stats(f, start + dur / 1000.0, dur, PERIOD)
    assert s["n"] == 90 and s["tok_ms_p50"] > 2.0 and s["tok_ms_p99"] <= 5.0 and s["frac_overrun"] == 0.0
    e = overrun_stats(f, np.array([]), np.array([]), PERIOD)
    assert e["n"] == 0 and np.isnan(e["overrun_ms_p50"])
