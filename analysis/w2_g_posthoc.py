"""POST-HOC, exploratory re-analysis of Experiment G (review reviews/2026-10-22_G_results_review.md findings 1 and 2). NOT registered, and it does not
change any registered verdict. Question: are the fg/bg 'overlaps' (P6) a staggered per-SM context switch (time-slicing with a non-atomic switch) or genuine
concurrency? Tools: overlap durations, overlap position relative to run boundaries (against a uniform reference), per-switch stagger across SMs, same-SM cases,
and a fine-grid refit of tau. Pure numpy/pandas on the witness records; tested on synthetic timelines in tests/test_w2_g_posthoc.py."""
import numpy as np
import pandas as pd

from w2_g_timeline import OVERLAP_TOL_NS, _per_launch_intervals, launch_table, merge_intervals


def _bg_candidates(bg_i, lo, hi):
    return [t for t in sorted(bg_i) if bg_i[t][0].min() < hi and bg_i[t][1].max() > lo]


def overlap_pairs(fg_rec, bg_rec, fg_tags=None, tol_ns=OVERLAP_TOL_NS):
    """Every (fg on-interval, bg on-interval) pair that intersects by more than tol_ns, with the intersection and the block/SM identities."""
    fg_i = _per_launch_intervals(fg_rec); bg_i = _per_launch_intervals(bg_rec)
    tags = sorted(fg_i) if fg_tags is None else [int(t) for t in fg_tags if int(t) in fg_i]
    fsm = np.asarray(fg_rec["smid"]).astype(np.int64); bsm = np.asarray(bg_rec["smid"]).astype(np.int64)
    cols = {k: [] for k in ("ov_ns", "ov_start", "ov_end", "fg_tag", "bg_tag", "fg_blk", "bg_blk", "fg_sm", "bg_sm", "fg_s", "fg_e", "bg_s", "bg_e")}
    for t in tags:
        fs, fe, fb = fg_i[t]
        for bt in _bg_candidates(bg_i, fs.min(), fe.max()):
            bs, be, bb = bg_i[bt]
            lo = np.maximum(fs[:, None], bs[None, :]); hi = np.minimum(fe[:, None], be[None, :])
            i, j = np.nonzero(hi - lo > tol_ns)
            if not len(i):
                continue
            for k, v in (("ov_ns", (hi - lo)[i, j]), ("ov_start", lo[i, j]), ("ov_end", hi[i, j]), ("fg_tag", np.full(len(i), t)), ("bg_tag", np.full(len(i), bt)),
                         ("fg_blk", fb[i]), ("bg_blk", bb[j]), ("fg_sm", fsm[fb[i]]), ("bg_sm", bsm[bb[j]]), ("fg_s", fs[i]), ("fg_e", fe[i]), ("bg_s", bs[j]), ("bg_e", be[j])):
                cols[k].append(np.asarray(v))
    return {k: (np.concatenate(v) if v else np.zeros(0, np.int64)) for k, v in cols.items()}


def _boundaries(ft, bt, fg_tag, bg_tag):
    fi = int(np.flatnonzero(ft["tags"] == fg_tag)[0]); bi = int(np.flatnonzero(bt["tags"] == bg_tag)[0])
    fs, fe = ft["runs"][fi]; bs, be = bt["runs"][bi]
    return np.concatenate([fs, fe, bs, be])


def boundary_distances(pairs, fg_rec, bg_rec):
    """Distance (ns) from each overlap's midpoint to the nearest run boundary (start or end of a merged run of its fg launch or of its bg launch)."""
    ft, bt = launch_table(fg_rec), launch_table(bg_rec)
    mid = (pairs["ov_start"] + pairs["ov_end"]) / 2
    out = np.full(len(mid), np.nan)
    cache = {}
    for k in range(len(mid)):
        key = (int(pairs["fg_tag"][k]), int(pairs["bg_tag"][k]))
        if key not in cache:
            cache[key] = _boundaries(ft, bt, *key)
        out[k] = np.abs(cache[key] - mid[k]).min()
    return out


def uniform_boundary_fraction(fg_rec, bg_rec, fg_tags, within_ns, n=5000, seed=0):
    """Reference: fraction of points placed uniformly inside the fg launch spans that lie within within_ns of a run boundary of the fg launch or of a bg
    launch overlapping its span. If overlaps are no closer to boundaries than this, they are not concentrated at boundaries."""
    ft, bt = launch_table(fg_rec), launch_table(bg_rec)
    rng = np.random.default_rng(seed); hit = tot = 0
    tags = [int(t) for t in fg_tags]
    for _ in range(n):
        t = tags[int(rng.integers(len(tags)))]; i = int(np.flatnonzero(ft["tags"] == t)[0])
        a, b = float(ft["span_start"][i]), float(ft["span_end"][i]); x = rng.uniform(a, b)
        fs, fe = ft["runs"][i]; bnd = [fs, fe]
        for j in np.flatnonzero((bt["span_start"] < b) & (bt["span_end"] > a)):
            bnd += list(bt["runs"][j])
        bnd = np.concatenate(bnd); tot += 1; hit += int(np.abs(bnd - x).min() <= within_ns)
    return hit / max(tot, 1)


def _per_sm_runs(s, e, blk, sm_of):
    out = {}
    sm = sm_of[blk]
    for u in np.unique(sm):
        k = sm == u
        out[int(u)] = merge_intervals(s[k], e[k])
    return out


def switch_stagger(fg_rec, bg_rec, fg_tags, min_sm=30, window_ns=500_000, cluster_ns=200_000, tol_ns=OVERLAP_TOL_NS):
    """Per-switch stagger across SMs. For each fg launch, per SM: merged fg runs and merged bg runs (bg launches overlapping the fg span), alternating by
    start time. A per-SM transition = consecutive runs of different contexts (out = earlier, in = later). Transitions of one direction are clustered in time
    (gap > cluster_ns starts a new switch); a cluster with at least min_sm distinct SMs is one switch. Reported per switch: spread (max-min) of the outgoing
    context's last on-time and of the incoming context's first on-time across SMs, the cross-SM overlap (latest out end - earliest in start), the per-SM gap
    (in start - out end on the same SM; negative = same-SM overlap) and how many SMs have a same-SM overlap beyond tol_ns."""
    fg_i = _per_launch_intervals(fg_rec); bg_i = _per_launch_intervals(bg_rec)
    fsm = np.asarray(fg_rec["smid"]).astype(np.int64); bsm = np.asarray(bg_rec["smid"]).astype(np.int64)
    rows = []
    for t in (int(x) for x in fg_tags):
        if t not in fg_i:
            continue
        fs, fe, fb = fg_i[t]; a, b = int(fs.min()), int(fe.max())
        cs, ce, cb = [], [], []
        for bt in _bg_candidates(bg_i, a - window_ns, b + window_ns):
            s, e, k = bg_i[bt]; cs.append(s); ce.append(e); cb.append(k)
        if not cs:
            continue
        bs, be, bb = np.concatenate(cs), np.concatenate(ce), np.concatenate(cb)
        fr = _per_sm_runs(fs, fe, fb, fsm); br = _per_sm_runs(bs, be, bb, bsm)
        trans = {"fg->bg": [], "bg->fg": []}
        for sm in set(fr) & set(br):
            rs = np.concatenate([fr[sm][0], br[sm][0]]); re = np.concatenate([fr[sm][1], br[sm][1]])
            rc = np.r_[np.zeros(len(fr[sm][0]), int), np.ones(len(br[sm][0]), int)]
            o = np.argsort(rs, kind="stable"); rs, re, rc = rs[o], re[o], rc[o]
            for k in np.flatnonzero(rc[1:] != rc[:-1]):
                oe, ins = int(re[k]), int(rs[k + 1])
                if oe >= a - window_ns and ins <= b + window_ns:
                    trans["fg->bg" if rc[k] == 0 else "bg->fg"].append((sm, oe, ins))
        for d, lst in trans.items():
            if not lst:
                continue
            arr = np.array(lst, dtype=np.int64); ref = (arr[:, 1] + arr[:, 2]) / 2
            o = np.argsort(ref); arr, ref = arr[o], ref[o]
            cut = np.r_[0, np.flatnonzero(np.diff(ref) > cluster_ns) + 1, len(ref)]
            for lo, hi in zip(cut[:-1], cut[1:]):
                c = arr[lo:hi]
                if len(np.unique(c[:, 0])) < min_sm:
                    continue
                gap = c[:, 2] - c[:, 1]
                rows.append(dict(fg_tag=t, direction=d, n_sm=len(np.unique(c[:, 0])), out_end_spread_ns=int(c[:, 1].max() - c[:, 1].min()),
                                 in_start_spread_ns=int(c[:, 2].max() - c[:, 2].min()), cluster_overlap_ns=int(c[:, 1].max() - c[:, 2].min()),
                                 per_sm_gap_min_ns=int(gap.min()), per_sm_gap_median_ns=float(np.median(gap)), n_sm_same_sm_overlap=int((gap < -tol_ns).sum())))
    return pd.DataFrame(rows, columns=["fg_tag", "direction", "n_sm", "out_end_spread_ns", "in_start_spread_ns", "cluster_overlap_ns", "per_sm_gap_min_ns",
                                       "per_sm_gap_median_ns", "n_sm_same_sm_overlap"])


def same_sm_cases(pairs, fg_rec, bg_rec, n=15, seed=0, edge_us=30.0):
    """Up to n randomly chosen SAME-SM overlaps for hand inspection: where the intersection sits inside each block's on-interval, the block durations, read
    cadence and logged gaps, and whether the intersection touches an interval edge (within edge_us), the signature of a block-boundary timestamp artefact."""
    k = np.flatnonzero(pairs["fg_sm"] == pairs["bg_sm"])
    if not len(k):
        return pd.DataFrame(columns=["sm", "ov_us", "fg_pos_us", "bg_pos_us", "fg_block_us", "bg_block_us", "at_edge"])
    pick = np.random.default_rng(seed).permutation(k)[:n]
    rows = []
    for i in pick:
        fb, bb = int(pairs["fg_blk"][i]), int(pairs["bg_blk"][i])
        fg_pos = (pairs["ov_start"][i] - pairs["fg_s"][i]) * 1e-3; bg_pos = (pairs["ov_start"][i] - pairs["bg_s"][i]) * 1e-3
        fg_tail = (pairs["fg_e"][i] - pairs["ov_end"][i]) * 1e-3; bg_tail = (pairs["bg_e"][i] - pairs["ov_end"][i]) * 1e-3
        rows.append(dict(sm=int(pairs["fg_sm"][i]), fg_tag=int(pairs["fg_tag"][i]), bg_tag=int(pairs["bg_tag"][i]), fg_blk_rec=fb, bg_blk_rec=bb, ov_us=pairs["ov_ns"][i] * 1e-3,
                         fg_pos_us=fg_pos, fg_tail_us=fg_tail, bg_pos_us=bg_pos, bg_tail_us=bg_tail,
                         fg_block_us=float(fg_rec["t1"][fb] - fg_rec["t0"][fb]) * 1e-3, bg_block_us=float(bg_rec["t1"][bb] - bg_rec["t0"][bb]) * 1e-3,
                         fg_nreads=int(fg_rec["nreads"][fb]), bg_nreads=int(bg_rec["nreads"][bb]), fg_ngaps=int(fg_rec["ngaps"][fb]), bg_ngaps=int(bg_rec["ngaps"][bb]),
                         at_edge=bool(min(fg_pos, fg_tail, bg_pos, bg_tail) < edge_us)))
    return pd.DataFrame(rows)


def _role(s, e, t0, t1):
    first = s == t0; last = e == t1
    return np.where(first & last, "only", np.where(first, "first", np.where(last, "last", "interior")))


def overlap_roles(pairs, fg_rec, bg_rec):
    """Role of each overlapping on-interval inside its block: first (starts at the block start), last (ends at the block end = latest warp end), only
    (both) or interior. Gaps are logged from thread 0 only; stalls of the block's other warps before thread 0 starts or after it finishes are invisible,
    so overlaps made of first/last intervals are the candidates for a measurement artefact, interior-interval overlaps are not."""
    ft0 = np.asarray(fg_rec["t0"]).astype(np.int64); ft1 = np.asarray(fg_rec["t1"]).astype(np.int64)
    bt0 = np.asarray(bg_rec["t0"]).astype(np.int64); bt1 = np.asarray(bg_rec["t1"]).astype(np.int64)
    fb = pairs["fg_blk"].astype(np.int64); bb = pairs["bg_blk"].astype(np.int64)
    return dict(fg_role=_role(pairs["fg_s"], pairs["fg_e"], ft0[fb], ft1[fb]), bg_role=_role(pairs["bg_s"], pairs["bg_e"], bt0[bb], bt1[bb]))


def _tau_curve(r, y, grid):
    """SSE(tau) and offset for wait = offset + min(r, tau) (offset free) on every tau in grid, in O(n log n + |grid| log n) with prefix sums."""
    o = np.argsort(r); r, y = r[o], y[o]; n = len(r)
    cy = np.r_[0, np.cumsum(y)]; cr = np.r_[0, np.cumsum(r)]; cyy = np.r_[0, np.cumsum(y * y)]; cdd = np.r_[0, np.cumsum((y - r) ** 2)]
    k = np.searchsorted(r, grid, side="right")                      # the first k points have r <= tau
    n_hi = n - k; sy_hi = cy[n] - cy[k]; syy_hi = cyy[n] - cyy[k]
    sz = (cy[k] - cr[k]) + (sy_hi - grid * n_hi)
    szz = cdd[k] + (syy_hi - 2 * grid * sy_hi + n_hi * grid ** 2)
    return szz - sz ** 2 / n, sz / n


def fine_tau_fit(r_ms, wait_ms, blocks, grid=None, n_boot=500, seed=0, ci=0.90):
    """Sensitivity refit of the capped-wait plateau tau on a 0.2 us grid (the registered fit uses a 10 us grid, so its bootstrap CI collapsed to a point).
    Same model and block-cluster bootstrap."""
    r, y, b = np.asarray(r_ms, float), np.asarray(wait_ms, float), np.asarray(blocks)
    grid = np.arange(0.05, 1.5, 0.0002) if grid is None else np.asarray(grid, float)
    sse, off = _tau_curve(r, y, grid); i = int(np.argmin(sse))
    rng = np.random.default_rng(seed); ub = np.unique(b); by = {u: np.flatnonzero(b == u) for u in ub}
    ts = []
    for _ in range(n_boot):
        idx = np.concatenate([by[u] for u in rng.choice(ub, len(ub))])
        s2, _ = _tau_curve(r[idx], y[idx], grid); ts.append(grid[int(np.argmin(s2))])
    lo, hi = np.percentile(ts, [50 * (1 - ci), 100 - 50 * (1 - ci)])
    return dict(tau=float(grid[i]), offset=float(off[i]), tau_lo=float(lo), tau_hi=float(hi), grid_step=float(grid[1] - grid[0]))
