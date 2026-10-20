"""Pure statistics for the W2 analyses (tested in tests/test_w2_stats.py)."""
import numpy as np


def find_knee(rel_thr_by_level, threshold=0.95):
    """Lowest SM clock level whose median relative throughput (vs unlocked) is >= threshold, or None."""
    if not rel_thr_by_level:
        raise ValueError("no levels")
    ok = [lv for lv, v in rel_thr_by_level.items() if v >= threshold]
    return min(ok) if ok else None


def _ols_slope(x, y):
    xm = x - x.mean()
    return float((xm * (y - y.mean())).sum() / (xm ** 2).sum())


def equivalence_slope(x, y, blocks, bounds=(0.8, 1.25), ci=0.90, n_boot=2000, seed=0):
    """OLS slope of y on x with a block-cluster bootstrap CI; 'equivalent' iff the whole CI lies within `bounds`."""
    x, y, blocks = np.asarray(x, float), np.asarray(y, float), np.asarray(blocks)
    if not (x.shape == y.shape == blocks.shape):
        raise ValueError("x, y, blocks must have the same shape")
    ids = np.unique(blocks)
    if ids.size < 2:
        raise ValueError("need at least 2 blocks to bootstrap over blocks")
    by = [np.flatnonzero(blocks == b) for b in ids]
    rng = np.random.default_rng(seed)
    slopes = []
    for _ in range(n_boot):
        idx = np.concatenate([by[i] for i in rng.integers(0, len(by), len(by))])
        if np.ptp(x[idx]) > 0:
            slopes.append(_ols_slope(x[idx], y[idx]))
    lo, hi = np.percentile(slopes, [50 * (1 - ci), 100 - 50 * (1 - ci)])
    return dict(slope=_ols_slope(x, y), ci_lo=float(lo), ci_hi=float(hi), bounds=bounds,
                equivalent=bool(bounds[0] <= lo and hi <= bounds[1]))
