"""P5 co-run feasibility cell: does fg latency depend on where the arrival lands in a bg slice; do bg slices stretch when an fg kernel completes inside them?
Usage: python p5_phase_analysis.py <pilot dir containing p5_bg.csv and p5_fg.csv>"""
import sys, numpy as np
d = sys.argv[1]
bg = np.loadtxt(d + "/p5_bg.csv", delimiter=",", skiprows=1); fg = np.loadtxt(d + "/p5_fg.csv", delimiter=",", skiprows=1)
a, tl, tc, g = fg.T; lat = (tc - a) * 1e3
print("fg n", len(a), "lat p50/p90/p99 ms", np.percentile(lat, [50, 90, 99]).round(3), "max", lat.max().round(2))
print("fg gpu_ms p50/p90/p99", np.percentile(g, [50, 90, 99]).round(3))
ts, te = bg[:, 0], bg[:, 1]
idx = np.clip(np.searchsorted(ts, a, side="right") - 1, 0, len(ts) - 1)
ok = (a >= ts[0]) & (a < te[idx]); ph = (a - ts[idx]) * 1e3
print("arrivals inside a bg slice:", ok.sum(), "of", len(a))
for lo, hi in [(0, .5), (.5, 1), (1, 1.5), (1.5, 2.6)]:
    m = ok & (ph >= lo) & (ph < hi)
    if m.sum(): print(f"  phase {lo}-{hi} ms into slice: n={m.sum()} lat mean {lat[m].mean():.3f} p50 {np.median(lat[m]):.3f} max {lat[m].max():.3f}  gpu_ms mean {g[m].mean():.3f}")
contains = np.zeros(len(ts), bool)
for x in tc:
    i = np.searchsorted(ts, x, side="right") - 1
    if 0 <= i < len(ts) and x < te[i]: contains[i] = True
dd = (te - ts) * 1e3
print("bg slice ms: with fg completion inside mean %.3f (n=%d) | without mean %.3f (n=%d)" % (dd[contains].mean(), contains.sum(), dd[~contains].mean(), (~contains).sum()))
