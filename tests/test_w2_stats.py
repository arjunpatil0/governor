"""W2 pure statistics: knee rule (journal 0008 mod C / plan C) and the slope equivalence test (mod A.2)."""
import numpy as np
import pytest

from w2_stats import equivalence_slope, find_knee


# ---- knee: lowest level whose median relative throughput >= threshold (default 0.95)
def test_knee_is_lowest_level_reaching_threshold():
    rel = {600: 0.81, 900: 0.89, 1050: 0.94, 1200: 0.993, 1500: 0.997, 1800: 0.998}
    assert find_knee(rel) == 1200


def test_knee_exactly_at_threshold_counts_and_nonmonotone_takes_lowest():
    assert find_knee({900: 0.95, 1200: 0.90, 1500: 1.0}) == 900
    assert find_knee({900: 0.9499, 1200: 0.97}) == 1200


def test_knee_none_when_never_reached_and_custom_threshold():
    assert find_knee({600: 0.5, 900: 0.7}) is None
    assert find_knee({600: 0.5, 900: 0.7}, threshold=0.6) == 900
    with pytest.raises(ValueError):
        find_knee({})


# ---- equivalence: 90% block-bootstrap CI of the OLS slope must lie within [0.8, 1.25]
def _blocks(slope, noise, n_blocks=10, per=18, seed=0):
    rng = np.random.default_rng(seed)
    x = np.tile(np.linspace(0.1, 4.0, per), n_blocks)
    y = slope * x + 0.05 + rng.normal(0, noise, x.size)
    return x, y, np.repeat(np.arange(n_blocks), per)


def test_equivalent_when_slope_is_one_and_tight():
    x, y, b = _blocks(1.0, 0.02)
    r = equivalence_slope(x, y, b, seed=1)
    assert r["equivalent"] is True
    assert 0.8 <= r["ci_lo"] <= r["slope"] <= r["ci_hi"] <= 1.25


def test_not_equivalent_when_slope_is_two():
    x, y, b = _blocks(2.0, 0.02)
    r = equivalence_slope(x, y, b, seed=1)
    assert r["equivalent"] is False and r["ci_lo"] > 1.25


def test_wide_ci_around_one_is_not_equivalent():
    # slope 1 on average but so noisy that the CI spills outside [0.8, 1.25]: a CI-includes-1 test would pass, this must not
    x, y, b = _blocks(1.0, 3.0, n_blocks=6, per=6)
    r = equivalence_slope(x, y, b, seed=1)
    assert r["ci_lo"] < 0.8 or r["ci_hi"] > 1.25
    assert r["equivalent"] is False


def test_equivalence_is_seeded_and_validates():
    x, y, b = _blocks(1.0, 0.1)
    assert equivalence_slope(x, y, b, seed=4) == equivalence_slope(x, y, b, seed=4)
    with pytest.raises(ValueError):
        equivalence_slope(x[:5], y[:4], b[:5], seed=1)
    with pytest.raises(ValueError):
        equivalence_slope(x[:5], y[:5], np.zeros(5), seed=1)   # one block: cannot bootstrap over blocks
