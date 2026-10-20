#!/usr/bin/env python3
"""W2 analysis: the pre-registered decision rules of experiments/w2_colocation.yaml, as tested functions (tests/test_w2_analysis.py),
plus a command-line driver (see main) that reads a run's results.csv and per-cell logs and writes data/w2_<part>_results.md.
Seeds for every bootstrap are fixed (SEED); multiplicity is Holm within each family named in the yaml."""
import numpy as np
import pandas as pd
from scipy.stats import wilcoxon

from w2_stats import bootstrap_median_ci, equivalence_slope, find_knee, ols_block_bootstrap

SEED = 20261021
ALPHA = 0.05
UNLOCKED_KEY = 10_000          # 'unlocked' sorts above every locked level when comparing knees


def holm(pvals):
    p = np.asarray(pvals, float); order = np.argsort(p); m = len(p); adj = np.empty(m); run = 0.0
    for rank, i in enumerate(order):
        run = max(run, (m - rank) * p[i]); adj[i] = min(1.0, run)
    return adj


def _wilcoxon_greater(d):
    d = np.asarray(d, float)
    if np.all(d == 0):
        return 1.0
    return float(wilcoxon(d, alternative="greater", zero_method="wilcox").pvalue)


# ---- HA1 / HA2 (Experiment A) ---------------------------------------------------------------------------------------
def ha1(cells):
    """cells: block, cell_id, m_ms, cv, pred_ms, obs_ms (obs = mean latency - block baseline mean latency). Supported iff the slope
    equivalence test (OLS WITH intercept, 90% block-bootstrap CI inside [0.8, 1.25]) holds AND >= 70% of cell medians are within +/-25%."""
    r = equivalence_slope(cells.pred_ms, cells.obs_ms, cells.block, seed=SEED)
    med = cells.groupby("cell_id")[["obs_ms", "pred_ms"]].median()
    frac = float(((med.obs_ms - med.pred_ms).abs() <= 0.25 * med.pred_ms).mean())
    r.update(frac_within25=frac, n_cells=int(len(med)), supported=bool(r["equivalent"] and frac >= 0.7))
    return r


def classify_ha1(cells, res):
    """Registered order: preempted_or_concurrent, then scheduler_capped, else other."""
    if res["supported"]:
        return "supported"
    med = cells.groupby(["cell_id", "m_ms", "cv"])[["obs_ms", "pred_ms"]].median().reset_index()
    big = med[med.m_ms >= 2]
    if res["ci_hi"] < 0.8 and float((big.obs_ms / big.pred_ms).median()) < 0.5:
        return "preempted_or_concurrent"
    c0 = med[med.cv == 0].set_index("m_ms")
    if c0.loc[8, "obs_ms"] <= 1.25 * c0.loc[2, "obs_ms"] and c0.loc[8, "pred_ms"] / c0.loc[2, "pred_ms"] >= 3:
        return "scheduler_capped"
    return "other"


def ha2(cells):
    """At each m: one-sided paired Wilcoxon obs(c=1) > obs(c=0) over blocks; Holm over m; supported iff >= 4 of the m values."""
    rows = []
    for m, g in cells.groupby("m_ms"):
        w = g.pivot_table(index="block", columns="cv", values="obs_ms")
        rows.append(dict(m_ms=m, n=len(w), median_diff=float((w[1.0] - w[0.0]).median()), p=_wilcoxon_greater(w[1.0] - w[0.0])))
    t = pd.DataFrame(rows)
    t["p_holm"] = holm(t.p); t["significant"] = t.p_holm < ALPHA
    n = int(t.significant.sum())
    return dict(table=t, n_sig=n, supported=n >= 4)


# ---- SA1 ------------------------------------------------------------------------------------------------------------
def sa1_label(phase_ms, latency_ms, blocks):
    """Slope of fg latency on arrival phase within the slice (ms per ms): -1 = waits out the slice, 0 = phase independent."""
    r = ols_block_bootstrap(phase_ms, latency_ms, blocks, seed=SEED)
    lo, hi = r["ci_lo"], r["ci_hi"]
    label = "phase-independent" if (-0.25 <= lo and hi <= 0.25) else "waits-out-the-slice" if (-1.25 <= lo and hi <= -0.8) else "mixed"
    return dict(label=label, slope=r["slope"], ci_lo=lo, ci_hi=hi)


# ---- HB1 / HB2 (Experiment B) ---------------------------------------------------------------------------------------
def hb1(df, rel_w1):
    """df: block, frame, kind ('fma'|'mem'), level, service_ms (bg off). Ratio service(L)/service(1800) per block vs rel_W1(1800)/rel_W1(L);
    ok iff the 90% bootstrap CI of the median ratio lies within +/-10% (fma) or +/-5% (mem) of the prediction. Supported iff every
    fma frame is ok at L in {900, 1200, 1500}."""
    rows = []
    for (frame, kind), g in df.groupby(["frame", "kind"]):
        ref = g[g.level == 1800].set_index("block").service_ms
        for L in (900, 1200, 1500):
            s = g[g.level == L].set_index("block").service_ms
            ratio = (s / ref).dropna().to_numpy()
            lo, hi = bootstrap_median_ci(ratio, seed=SEED)
            pred = rel_w1[kind][1800] / rel_w1[kind][L]
            tol = 0.10 if kind == "fma" else 0.05
            rows.append(dict(frame=frame, kind=kind, level=L, ratio_median=float(np.median(ratio)), ci_lo=lo, ci_hi=hi, pred=pred,
                             tol=tol, ok=bool(pred * (1 - tol) <= lo and hi <= pred * (1 + tol))))
    t = pd.DataFrame(rows)
    return dict(table=t, supported=bool(t[t.kind == "fma"].ok.all()))


def hb2(df, budget_ms, pred_ratio):
    """df: block, level, miss_frac, service_ms for one frame kind / background condition. One-sided paired Wilcoxon miss(L) > miss(1800)
    for L in pred_ratio, Holm over those levels. Supported iff significant at every level whose predicted service (median measured
    service at 1800 x HB1 ratio) exceeds the frame budget."""
    ref = df[df.level == 1800].set_index("block")
    levels = sorted(pred_ratio)
    ps = [_wilcoxon_greater((df[df.level == L].set_index("block").miss_frac - ref.miss_frac).dropna()) for L in levels]
    adj = holm(ps)
    svc1800 = float(ref.service_ms.median())
    must = [L for L in levels if svc1800 * pred_ratio[L] > budget_ms]
    sig = {L: bool(a < ALPHA) for L, a in zip(levels, adj)}
    return dict(table=pd.DataFrame(dict(level=levels, p=ps, p_holm=adj, significant=[sig[L] for L in levels])),
                must_be_significant=must, supported=bool(must) and all(sig[L] for L in must))


# ---- HC1 / knees (Experiment C) -------------------------------------------------------------------------------------
def _lvl(x):
    return UNLOCKED_KEY if x == "unlocked" else int(x)


def block_knees(df):
    """Per-block knee level for each variant (graph launch mode): lowest level with relative throughput >= 0.95."""
    g = df[df.graph]
    rows = {}
    for (b, variant), d in g.groupby(["block", "variant"]):
        k = find_knee({_lvl(l): v for l, v in zip(d.level, d.rel_thr)})
        rows.setdefault(b, {})[variant] = UNLOCKED_KEY if k is None else k
    return pd.DataFrame.from_dict(rows, orient="index").sort_index()


def hc1(df):
    """df: block, variant ('int4'|'fp16'), graph, level, rel_thr (vs the same block's unlocked cell). One-sided paired Wilcoxon
    (int4 knee > fp16 knee, zero_method='wilcox'); INCONCLUSIVE if fewer than 6 blocks have a nonzero difference."""
    kt = block_knees(df)
    d = (kt["int4"] - kt["fp16"]).to_numpy(float)
    nz = int((d != 0).sum())
    if nz < 6:
        return dict(knee_table=kt, n_nonzero=nz, status="inconclusive", p=None)
    p = _wilcoxon_greater(d)
    return dict(knee_table=kt, n_nonzero=nz, status="supported" if p < ALPHA else "not supported", p=p)
