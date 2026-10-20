"""W2 pure helpers: slice/arrival generation, latency without coordinated omission, residual-wait prediction with
utilisation (journal 0008 mod A.1), and the dxdiag HAGS parser (journal 0010)."""
import numpy as np
import pytest

from loadgen import gamma_slice_durations, latencies, parse_hags, poisson_arrivals, residual_wait


# ---- slice durations: target mean and CV, seeded
@pytest.mark.parametrize("mean,cv", [(1.0, 0.0), (2.0, 0.5), (4.0, 1.0)])
def test_slices_hit_target_mean_and_cv(mean, cv):
    s = gamma_slice_durations(200_000, mean, cv, seed=7)
    assert s.mean() == pytest.approx(mean, rel=0.02)
    assert s.std() / s.mean() == pytest.approx(cv, abs=0.02)


def test_cv_zero_is_constant_and_slices_positive():
    s = gamma_slice_durations(50, 3.0, 0.0, seed=1)
    assert np.all(s == 3.0)
    assert np.all(gamma_slice_durations(1000, 1.0, 1.0, seed=1) > 0)


def test_slices_are_seeded_and_reject_bad_args():
    assert np.array_equal(gamma_slice_durations(10, 1, 1, seed=3), gamma_slice_durations(10, 1, 1, seed=3))
    assert not np.array_equal(gamma_slice_durations(10, 1, 1, seed=3), gamma_slice_durations(10, 1, 1, seed=4))
    for bad in (dict(n=0, mean_ms=1, cv=0), dict(n=5, mean_ms=0, cv=0), dict(n=5, mean_ms=1, cv=-0.1)):
        with pytest.raises(ValueError):
            gamma_slice_durations(seed=1, **bad)


# ---- Poisson arrivals on an absolute time grid
def test_arrivals_poisson_rate_sorted_and_absolute():
    a = poisson_arrivals(rate_hz=200.0, n=20_000, seed=5, t0=10.0)
    assert np.all(np.diff(a) > 0) and a[0] > 10.0
    assert 1.0 / np.diff(a).mean() == pytest.approx(200.0, rel=0.03)
    gaps = np.diff(a)
    assert gaps.std() / gaps.mean() == pytest.approx(1.0, abs=0.05)   # exponential gaps: CV 1


def test_arrivals_seeded_and_validated():
    assert np.array_equal(poisson_arrivals(50, 100, seed=2), poisson_arrivals(50, 100, seed=2))
    with pytest.raises(ValueError):
        poisson_arrivals(0, 10, seed=1)


# ---- latency measured from the SCHEDULED arrival (no coordinated omission)
def test_latency_counts_queueing_behind_a_late_request():
    # request 1 was scheduled at t=1 but only finished at 3.0: its latency is 2.0, and request 2
    # (scheduled at 2, finished 3.5) is 1.5, not the 0.5 a closed-loop sender would report.
    lat = latencies(arrivals=[0.0, 1.0, 2.0], completions=[0.5, 3.0, 3.5])
    assert lat == pytest.approx([0.5, 2.0, 1.5])


def test_latency_rejects_mismatch_and_time_travel():
    with pytest.raises(ValueError):
        latencies([0.0, 1.0], [0.5])
    with pytest.raises(ValueError):
        latencies([1.0], [0.5])            # completion before arrival: broken clock, fail loudly


# ---- residual wait with utilisation from logged slice timestamps
def test_residual_wait_constant_slices_no_gaps():
    # five 2 ms slices back to back: rho = 1, E[S] = 2, E[S^2] = 4 -> residual 1 ms, predicted 1 ms
    starts = np.arange(5) * 0.002
    r = residual_wait(starts, starts + 0.002)
    assert r["rho"] == pytest.approx(1.0)
    assert r["residual_s"] == pytest.approx(0.001)
    assert r["predicted_s"] == pytest.approx(0.001)
    assert r["gap_mean_s"] == pytest.approx(0.0, abs=1e-12)


def test_residual_wait_scales_with_utilisation():
    # 1 ms slice, 1 ms idle gap: rho = 10/(10+9) -> exact from timestamps
    starts = np.arange(10) * 0.002
    r = residual_wait(starts, starts + 0.001)
    assert r["rho"] == pytest.approx(10 * 0.001 / (9 * 0.002 + 0.001))
    assert r["residual_s"] == pytest.approx(0.0005)
    assert r["predicted_s"] == pytest.approx(r["rho"] * 0.0005)
    assert r["gap_mean_s"] == pytest.approx(0.001) and r["gap_p99_s"] == pytest.approx(0.001)


def test_residual_wait_uses_second_moment_not_just_mean():
    # slices 1 and 3 ms: E[S] = 2, E[S^2] = 5 -> residual 5/(2*2) = 1.25 ms (> 1 ms of a constant 2 ms slice)
    r = residual_wait([0.0, 0.001], [0.001, 0.004])
    assert r["residual_s"] == pytest.approx(0.00125)
    assert r["n_slices"] == 2


def test_residual_wait_validates_input():
    with pytest.raises(ValueError):
        residual_wait([], [])
    with pytest.raises(ValueError):
        residual_wait([0.0, 0.0005], [0.001, 0.002])   # overlapping slices: one stream cannot overlap
    with pytest.raises(ValueError):
        residual_wait([0.0], [0.0])                     # zero-length slice


# ---- dxdiag parse for meta.json (journal 0010)
DXDIAG = """\
Card name: AMD Radeon 780M Graphics
Driver Model: WDDM 3.1
Hardware Scheduling: DriverSupportState:AlwaysOff Enabled:False
Card name: NVIDIA GeForce RTX 4070 Laptop GPU
Driver Model: WDDM 3.2
Hardware Scheduling: DriverSupportState:Stable Enabled:True
"""


def test_parse_hags_picks_the_nvidia_adapter():
    assert parse_hags(DXDIAG) == {"adapter": "NVIDIA GeForce RTX 4070 Laptop GPU",
                                  "line": "DriverSupportState:Stable Enabled:True", "enabled": True}


def test_parse_hags_fails_loudly_when_missing():
    with pytest.raises(ValueError):
        parse_hags("Card name: NVIDIA GeForce RTX 4070 Laptop GPU\nDriver Model: WDDM 3.2\n")
    with pytest.raises(ValueError):
        parse_hags(DXDIAG, adapter="Intel")


# ---- derived metrics for the secondary analyses (SA1 phase, SA2 slice stretch) and the duty-cycle gap
from loadgen import duty_gap, phase_in_slice, slice_stretch


def test_phase_is_time_since_the_start_of_the_containing_slice():
    starts, ends = np.array([0.0, 0.002, 0.004]), np.array([0.002, 0.004, 0.006])
    phase_ms, inside = phase_in_slice(np.array([0.0005, 0.0035, 0.0071]), starts, ends)
    assert inside.tolist() == [True, True, False]                 # 7.1 ms is after the last slice
    assert phase_ms[:2] == pytest.approx([0.5, 1.5])


def test_arrival_in_an_idle_gap_is_not_inside_a_slice():
    starts, ends = np.array([0.0, 0.004]), np.array([0.002, 0.006])
    _, inside = phase_in_slice(np.array([0.003]), starts, ends)
    assert inside.tolist() == [False]


def test_slice_stretch_uses_slices_with_exactly_one_completion():
    starts = np.array([0.0, 0.003, 0.006, 0.009])
    ends = starts + np.array([0.002, 0.002, 0.0033, 0.002])       # third slice is 1.3 ms longer
    stretch_s, n = slice_stretch(starts, ends, completions=np.array([0.007]))
    assert n == 1 and stretch_s == pytest.approx([0.0013])


def test_slice_stretch_ignores_slices_with_two_completions():
    starts = np.array([0.0, 0.003, 0.006]); ends = starts + 0.002
    stretch_s, n = slice_stretch(starts, ends, completions=np.array([0.0035, 0.0045]))
    assert n == 0 and len(stretch_s) == 0


def test_duty_gap():
    assert duty_gap(0.002, 1.0) == 0.0
    assert duty_gap(0.002, 0.5) == pytest.approx(0.002)
    assert duty_gap(0.002, 0.25) == pytest.approx(0.006)
    for bad in (0, -0.1, 1.5):
        with pytest.raises(ValueError):
            duty_gap(0.002, bad)
