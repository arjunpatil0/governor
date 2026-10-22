"""Experiment G timeline analysis: gap on-intervals, runs, q, s, overlap (P6), preempted fraction (P7), recorded interval, timer offsets, P3 ripple.
Definitions: experiments/w2_colocation_addendum_globaltimer_prerun_2026-10-22.md sections A-C (supersede the first G addendum's run/overlap definitions).
Pure numpy; no GPU. All times int64 nanoseconds on the GPU %globaltimer. Tested on synthetic timelines in tests/test_w2_g_timeline.py."""
import numpy as np

LOG_THR_NS = 20_000          # logging threshold (kernel)
MERGE_NS = 20_000            # on-interval pieces closer than this are one run
OVERLAP_TOL_NS = 10_000      # intersections of <= 10 us are ties, not overlaps


def block_on_intervals(rec):
    """(rec_index, start, end) int64 arrays of every block's on-intervals = [block start, block end] minus its logged gaps. The gap offsets
    are relative to tg0 (thread 0's own start)."""
    n = len(rec["t0"])
    t0 = np.asarray(rec["t0"]).astype(np.int64); t1 = np.asarray(rec["t1"]).astype(np.int64); tg0 = np.asarray(rec["tg0"]).astype(np.int64)
    gi = np.asarray(rec["gaps"]["rec_idx"]).astype(np.int64)
    gs = tg0[gi] + np.asarray(rec["gaps"]["off"]).astype(np.int64) if len(gi) else np.zeros(0, np.int64)
    ge = gs + np.asarray(rec["gaps"]["len"]).astype(np.int64)
    order = np.lexsort((gs, gi)); gi, gs, ge = gi[order], gs[order], ge[order]
    ar = np.arange(n)
    if len(gi):
        first = np.searchsorted(gi, ar, side="left")
        fc = np.minimum(first, len(gi) - 1)
        has = (first < len(gi)) & (gi[fc] == ar)
        ends0 = np.where(has, gs[fc], t1)
        next_same = np.r_[gi[1:] == gi[:-1], False]
        ends_after = np.where(next_same, np.r_[gs[1:], 0], t1[gi])
    else:
        ends0 = t1
        ends_after = np.zeros(0, np.int64)
    blk = np.r_[ar, gi]; starts = np.r_[t0, ge]; ends = np.r_[ends0, ends_after]
    ok = ends > starts
    return blk[ok], starts[ok], ends[ok]


def merge_intervals(starts, ends, merge_ns=MERGE_NS):
    """Union of intervals, joining pieces whose separation is below merge_ns. Returns (starts, ends) sorted and disjoint."""
    starts = np.asarray(starts, dtype=np.int64); ends = np.asarray(ends, dtype=np.int64)
    if len(starts) == 0:
        return starts, ends
    o = np.argsort(starts, kind="stable"); s = starts[o]; e = ends[o]
    cm = np.maximum.accumulate(e)
    new = np.r_[True, s[1:] > cm[:-1] + merge_ns]
    idx = np.flatnonzero(new)
    return s[idx], np.r_[cm[idx[1:] - 1], cm[-1]]


def _group_bounds(sorted_keys):
    cut = np.flatnonzero(np.diff(sorted_keys)) + 1
    return np.r_[0, cut], np.r_[cut, len(sorted_keys)]


def launch_table(rec):
    """Per launch (rec tag): span over ALL blocks (min start, max end), the number of untrusted blocks (overflow > 0), and the RUNS = the merged
    on-set of the trusted blocks, as a list of (starts, ends) aligned with `tags`."""
    tag = np.asarray(rec["tag"]).astype(np.int64)
    tags = np.unique(tag)
    t0 = np.asarray(rec["t0"]).astype(np.int64); t1 = np.asarray(rec["t1"]).astype(np.int64)
    span_start = np.array([t0[tag == t].min() for t in tags]); span_end = np.array([t1[tag == t].max() for t in tags])
    novf = np.asarray(rec["novf"]).astype(np.int64)
    untrusted = np.array([int((novf[tag == t] > 0).sum()) for t in tags])
    blk, s, e = block_on_intervals(rec)
    keep = novf[blk] == 0
    blk, s, e = blk[keep], s[keep], e[keep]
    it = tag[blk]; o = np.argsort(it, kind="stable"); it, s, e = it[o], s[o], e[o]
    by = {}
    if len(it):
        lo, hi = _group_bounds(it)
        by = {int(it[a]): (s[a:b], e[a:b]) for a, b in zip(lo, hi)}
    empty = (np.zeros(0, np.int64), np.zeros(0, np.int64))
    runs = [merge_intervals(*by[int(t)]) if int(t) in by else empty for t in tags]
    return dict(tags=tags, span_start=span_start, span_end=span_end, untrusted=untrusted, runs=runs)


def sliced_mask(span_ns, alone_span_ns, extra_ms):
    """A SLICED fg span: on-GPU span longer than the same-block alone span by more than `extra_ms` (2 x 0.243 ms)."""
    return np.asarray(span_ns, dtype=float) > float(alone_span_ns) + extra_ms * 1e6


def q_and_s(fg, bg, sliced_tags):
    """q (median length of COMPLETE runs, pooled and per context) and s (median gap between consecutive runs of different contexts) inside the
    time ranges of the sliced fg launches. Complete run = neither the first nor the last run of its launch. Negative s (runs overlapping in
    time) is counted in n_neg_s and left out of the median."""
    pos_fg = {int(t): i for i, t in enumerate(fg["tags"])}
    q_fg, q_bg, s_all = [], [], []
    n_neg = n_trans = n_sliced = 0
    for t in sliced_tags:
        i = pos_fg[int(t)]
        a, b = int(fg["span_start"][i]), int(fg["span_end"][i])
        fs, fe = fg["runs"][i]
        n_sliced += 1
        q_fg += list(fe[1:-1] - fs[1:-1])
        cand = np.flatnonzero((bg["span_start"] < b) & (bg["span_end"] > a))
        rs, re, rc = [fs], [fe], [np.zeros(len(fs), int)]
        for j in cand:
            bs, be = bg["runs"][j]
            cs, ce = bs[1:-1], be[1:-1]
            inside = (cs >= a) & (ce <= b)
            q_bg += list(ce[inside] - cs[inside])
            rs.append(bs); re.append(be); rc.append(np.ones(len(bs), int))
        rs, re, rc = np.concatenate(rs), np.concatenate(re), np.concatenate(rc)
        sel = (rs >= a) & (rs <= b)
        rs, re, rc = rs[sel], re[sel], rc[sel]
        o = np.argsort(rs, kind="stable"); rs, re, rc = rs[o], re[o], rc[o]
        diff = rc[1:] != rc[:-1]
        gap = rs[1:] - re[:-1]
        n_trans += int(diff.sum())
        n_neg += int((diff & (gap < 0)).sum())
        s_all += list(gap[diff & (gap >= 0)])
    med = lambda x: float(np.median(x)) * 1e-6 if len(x) else float("nan")
    return dict(q_pooled_ms=med(q_fg + q_bg), q_fg_ms=med(q_fg), q_bg_ms=med(q_bg), s_ms=med(s_all), n_neg_s=n_neg, n_transitions=n_trans,
                n_sliced=n_sliced, n_runs_fg=len(q_fg), n_runs_bg=len(q_bg),
                q_fg_raw_ms=np.array(q_fg, float) * 1e-6, q_bg_raw_ms=np.array(q_bg, float) * 1e-6, s_raw_ms=np.array(s_all, float) * 1e-6)


def _per_launch_intervals(rec):
    """Trusted blocks' on-intervals grouped by launch tag: dict tag -> (starts, ends, rec_index)."""
    tag = np.asarray(rec["tag"]).astype(np.int64); novf = np.asarray(rec["novf"])
    blk, s, e = block_on_intervals(rec)
    keep = novf[blk] == 0
    blk, s, e = blk[keep], s[keep], e[keep]
    it = tag[blk]; o = np.argsort(it, kind="stable"); it, blk, s, e = it[o], blk[o], s[o], e[o]
    if not len(it):
        return {}
    lo, hi = _group_bounds(it)
    return {int(it[a]): (s[a:b], e[a:b], blk[a:b]) for a, b in zip(lo, hi)}


def count_overlaps(fg_rec, bg_rec, fg_tags=None, tol_ns=OVERLAP_TOL_NS):
    """P6. An fg block OVERLAPS when one of its on-intervals intersects an on-interval of a bg block for more than tol_ns; intersections of 1..tol_ns
    are ties. Trusted blocks only; fg_tags limits the fg launches (the recorded interval). Same-SM / different-SM split by %smid."""
    fg_i = _per_launch_intervals(fg_rec); bg_i = _per_launch_intervals(bg_rec)
    tags = sorted(fg_i) if fg_tags is None else [int(t) for t in fg_tags if int(t) in fg_i]
    ftags_all = np.asarray(fg_rec["tag"]).astype(np.int64); novf = np.asarray(fg_rec["novf"])
    sel = np.isin(ftags_all, tags) if fg_tags is not None else np.ones(len(ftags_all), bool)
    n_fg_blocks = int(((novf == 0) & sel).sum()); n_untrusted = int(((novf > 0) & sel).sum())
    bg_tag_list = sorted(bg_i)
    bg_ss = np.array([bg_i[t][0].min() for t in bg_tag_list]) if bg_tag_list else np.zeros(0, np.int64)
    bg_se = np.array([bg_i[t][1].max() for t in bg_tag_list]) if bg_tag_list else np.zeros(0, np.int64)
    fsm = np.asarray(fg_rec["smid"]).astype(np.int64); bsm = np.asarray(bg_rec["smid"]).astype(np.int64)
    ov_blocks, same_blocks, diff_blocks, tie_blocks = set(), set(), set(), set()
    for t in tags:
        fs, fe, fb = fg_i[t]
        cand = np.flatnonzero((bg_ss < fe.max()) & (bg_se > fs.min()))
        if not len(cand):
            continue
        bs = np.concatenate([bg_i[bg_tag_list[j]][0] for j in cand]); be = np.concatenate([bg_i[bg_tag_list[j]][1] for j in cand])
        bb = np.concatenate([bg_i[bg_tag_list[j]][2] for j in cand])
        ov = np.minimum(fe[:, None], be[None, :]) - np.maximum(fs[:, None], bs[None, :])
        big = ov > tol_ns
        same = big & (fsm[fb][:, None] == bsm[bb][None, :])
        diff = big & (fsm[fb][:, None] != bsm[bb][None, :])
        tie = (ov > 0) & ~big
        for mask, store in ((big, ov_blocks), (same, same_blocks), (diff, diff_blocks), (tie, tie_blocks)):
            rows = mask.any(axis=1)
            store.update((t, int(b)) for b in fb[rows])
    ties_only = tie_blocks - ov_blocks
    return dict(n_fg_blocks=n_fg_blocks, n_untrusted_fg=n_untrusted, n_overlap=len(ov_blocks), n_overlap_same_sm=len(same_blocks),
                n_overlap_diff_sm=len(diff_blocks), n_ties=len(ties_only))


def recorded_interval(bg_rec, fg_rec):
    """The interval where BOTH contexts are recorded (addendum 2 section C): from the first recorded bg block start to the last bg block end,
    and the fg launches whose whole on-GPU span lies inside it."""
    start = int(np.asarray(bg_rec["t0"]).astype(np.int64).min()); end = int(np.asarray(bg_rec["t1"]).astype(np.int64).max())
    ft = launch_table(fg_rec)
    inside = (ft["span_start"] >= start) & (ft["span_end"] <= end)
    return dict(start_ns=start, end_ns=end, fg_tags=ft["tags"][inside], n_fg=int(inside.sum()), n_bg_launches=int(len(np.unique(bg_rec["tag"]))))


def gap_contains_fg(gap_starts, gap_ends, fg_starts, fg_ends, tol_ns=OVERLAP_TOL_NS):
    """For each gap, whether it intersects the fg ON-set (disjoint sorted intervals) for more than tol_ns."""
    fs = np.asarray(fg_starts, dtype=np.int64); fe = np.asarray(fg_ends, dtype=np.int64)
    gs = np.asarray(gap_starts, dtype=np.int64); ge = np.asarray(gap_ends, dtype=np.int64)
    if not len(fs):
        return np.zeros(len(gs), bool)
    cum = np.r_[0, np.cumsum(fe - fs)]

    def cover(t):
        i = np.searchsorted(fs, t, side="right") - 1
        j = np.maximum(i, 0)
        base = np.where(i >= 0, cum[j], 0)
        inner = np.where(i >= 0, np.clip(t - fs[j], 0, (fe - fs)[j]), 0)
        return base + inner
    return (cover(ge) - cover(gs)) > tol_ns


def preempted_fraction(bg_rec, fg_rec, g_thr_ns, tol_ns=OVERLAP_TOL_NS):
    """P7. Fraction of recorded bg blocks with at least one logged gap >= g_thr_ns, and of those whose gap contains fg execution (> tol_ns)."""
    n = len(bg_rec["t0"])
    gi = np.asarray(bg_rec["gaps"]["rec_idx"]).astype(np.int64); gl = np.asarray(bg_rec["gaps"]["len"]).astype(np.int64)
    big = gl >= g_thr_ns
    tg0 = np.asarray(bg_rec["tg0"]).astype(np.int64)
    gs = tg0[gi[big]] + np.asarray(bg_rec["gaps"]["off"]).astype(np.int64)[big]; ge = gs + gl[big]
    blk, s, e = block_on_intervals(fg_rec)
    ok = np.asarray(fg_rec["novf"])[blk] == 0
    fs, fe = merge_intervals(s[ok], e[ok])
    cont = gap_contains_fg(gs, ge, fs, fe, tol_ns)
    return dict(n_blocks=n, fraction=len(np.unique(gi[big])) / n if n else float("nan"),
                fraction_with_fg=len(np.unique(gi[big][cont])) / n if n else float("nan"))


def offset_at(t_qpc, sync0, sync1):
    """GPU-timer-to-QPC offset (s) at QPC time t, linearly interpolated between two (offset_s, round_trip_s, qpc_time_s) sync points."""
    (o0, _, t0), (o1, _, t1) = sync0, sync1
    return o0 + (o1 - o0) * (t_qpc - t0) / (t1 - t0)


def p3_ripple(binned, drop_ms=0.04, tol=1e-6):
    """P3: on the binned unstretched-axis curve, a local minimum in 0.35-0.40 and one in 0.80-0.85 ms, each at least `drop_ms` below the
    preceding local maximum (max of the bins before it; for the second, max of the bins from 0.40 up to 0.80)."""
    lo = binned["lo"].to_numpy(float); w = binned["mean_wait_ms"].to_numpy(float)

    def one(at, prev_lo, prev_hi):
        k = np.flatnonzero(np.isclose(lo, at, atol=tol))
        if not len(k) or k[0] == 0 or k[0] == len(w) - 1:
            return False, float("nan")
        k = k[0]
        is_min = w[k] < w[k - 1] and w[k] < w[k + 1]
        prev = w[(lo >= prev_lo - tol) & (lo < prev_hi - tol)]
        drop = float(prev.max() - w[k]) if len(prev) else float("nan")
        return bool(is_min and drop >= drop_ms), drop
    h1, d1 = one(0.35, 0.0, 0.35)
    h2, d2 = one(0.80, 0.40, 0.80)
    return dict(held=bool(h1 and h2), min1_ok=h1, min2_ok=h2, drop1_ms=d1, drop2_ms=d2)


def restrict_rec(rec, keep):
    """Sub-record of the blocks where `keep` is true (boolean over records); gap list remapped to the new record indices."""
    keep = np.asarray(keep, dtype=bool)
    idx = np.flatnonzero(keep)
    remap = -np.ones(len(keep), dtype=np.int64); remap[idx] = np.arange(len(idx))
    out = {k: v[keep] for k, v in rec.items() if isinstance(v, np.ndarray) and len(v) == len(keep) and k != "gaps"}
    gi = np.asarray(rec["gaps"]["rec_idx"]).astype(np.int64)
    g = keep[gi]
    out["gaps"] = dict(rec_idx=remap[gi[g]].astype(np.uint32), off=np.asarray(rec["gaps"]["off"])[g], len=np.asarray(rec["gaps"]["len"])[g])
    out["dropped"] = rec.get("dropped", 0); out["gap_lost"] = rec.get("gap_lost", 0)
    return out
