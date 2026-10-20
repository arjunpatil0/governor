"""Pure statistics for the W2 analyses (tested in tests/test_w2_stats.py)."""
import numpy as np


def find_knee(rel_thr_by_level, threshold=0.95):
    """Lowest SM clock level whose median relative throughput (vs unlocked) is >= threshold, or None."""
    if not rel_thr_by_level:
        raise ValueError("no levels")
    ok = [lv for lv, v in rel_thr_by_level.items() if v >= threshold]
    return min(ok) if ok else None


def _ols(x, y):
    xm = x - x.mean()
    slope = float((xm * (y - y.mean())).sum() / (xm ** 2).sum())
    return slope, float(y.mean() - slope * x.mean())


def _check_blocks(x, y, blocks):
    x, y, blocks = np.asarray(x, float), np.asarray(y, float), np.asarray(blocks)
    if not (x.shape == y.shape == blocks.shape):
        raise ValueError("x, y, blocks must have the same shape")
    ids = np.unique(blocks)
    if ids.size < 2:
        raise ValueError("need at least 2 blocks to bootstrap over blocks")
    return x, y, [np.flatnonzero(blocks == b) for b in ids]


def ols_block_bootstrap(x, y, blocks, ci=0.90, n_boot=2000, seed=0):
    """OLS y = intercept + slope * x with a block-cluster percentile bootstrap CI for both coefficients."""
    x, y, by = _check_blocks(x, y, blocks)
    rng = np.random.default_rng(seed)
    sl, ic = [], []
    for _ in range(n_boot):
        idx = np.concatenate([by[i] for i in rng.integers(0, len(by), len(by))])
        if np.ptp(x[idx]) > 0:
            s, i0 = _ols(x[idx], y[idx])
            sl.append(s); ic.append(i0)
    q = [50 * (1 - ci), 100 - 50 * (1 - ci)]
    (s_lo, s_hi), (i_lo, i_hi) = np.percentile(sl, q), np.percentile(ic, q)
    slope, intercept = _ols(x, y)
    return dict(slope=slope, ci_lo=float(s_lo), ci_hi=float(s_hi), intercept=intercept, int_lo=float(i_lo), int_hi=float(i_hi))


def equivalence_slope(x, y, blocks, bounds=(0.8, 1.25), ci=0.90, n_boot=2000, seed=0):
    """Slope equivalence test: 'equivalent' iff the whole block-bootstrap CI of the OLS slope (fit WITH intercept) lies in `bounds`.
    The intercept and its CI are returned too (review 2026-10-21 finding 1)."""
    r = ols_block_bootstrap(x, y, blocks, ci=ci, n_boot=n_boot, seed=seed)
    r["bounds"] = bounds
    r["equivalent"] = bool(bounds[0] <= r["ci_lo"] and r["ci_hi"] <= bounds[1])
    return r


def bootstrap_median_ci(values, ci=0.90, n_boot=2000, seed=0):
    """Percentile bootstrap CI of the median of per-block values."""
    v = np.asarray(values, float)
    rng = np.random.default_rng(seed)
    meds = np.median(v[rng.integers(0, v.size, (n_boot, v.size))], axis=1)
    lo, hi = np.percentile(meds, [50 * (1 - ci), 100 - 50 * (1 - ci)])
    return float(lo), float(hi)
