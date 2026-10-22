"""Experiment G analysis (analysis/w2_g_timeline.py), tested on SYNTHETIC timelines before any G data exists (the yaml requires the analysis
to be committed before the first full run). Definitions: experiments/w2_colocation_addendum_globaltimer_prerun_2026-10-22.md sections A-C.
The key synthetic case is fg/bg ALTERNATION by suspend/resume of fully resident single-wave blocks: no block starts between runs, the
alternation exists only as several gaps inside each block, which a largest-gap-only record cannot represent."""
import numpy as np
import pytest

from w2_g_timeline import (block_on_intervals, count_overlaps, gap_contains_fg, launch_table, merge_intervals, offset_at, p3_ripple,
                           preempted_fraction, q_and_s, recorded_interval, sliced_mask)

US = 1000          # ns
MS = 1_000_000


def make_launches(launches, n_blocks=8, jitter_ns=0, seed=1, smid_offset=0):
    """launches: list of (tag, [(on_start_ns, on_end_ns), ...]) -> rec dict. Every block of a launch follows the same on-intervals (a context
    switch suspends all resident blocks together); the gaps between on-intervals are logged exactly as the kernel would (> 20 us)."""
    rng = np.random.default_rng(seed)
    t0, t1, tg0, tag, smid, blk, ngaps, novf = [], [], [], [], [], [], [], []
    gi, goff, glen = [], [], []
    for tg, ons in launches:
        for b in range(n_blocks):
            j = lambda: int(rng.integers(-jitter_ns, jitter_ns + 1)) if jitter_ns else 0
            ons_b = [(s + j(), e + j()) for s, e in ons]
            idx = len(t0)
            t0.append(ons_b[0][0]); t1.append(ons_b[-1][1]); tg0.append(ons_b[0][0]); tag.append(tg); smid.append(b + smid_offset); blk.append(b)
            n = 0
            for (s0, e0), (s1, e1) in zip(ons_b[:-1], ons_b[1:]):
                if s1 - e0 > 20 * US:
                    gi.append(idx); goff.append(e0 - ons_b[0][0]); glen.append(s1 - e0); n += 1
            ngaps.append(n); novf.append(0)
    z = lambda a, dt: np.array(a, dtype=dt)
    return dict(t0=z(t0, np.uint64), t1=z(t1, np.uint64), tg0=z(tg0, np.uint64), gmax=np.zeros(len(t0), np.uint64), gbeg=np.zeros(len(t0), np.uint64),
                smid=z(smid, np.uint32), tag=z(tag, np.uint32), blk=z(blk, np.uint32), nreads=np.full(len(t0), 100, np.uint32), ngaps=z(ngaps, np.uint32),
                novf=z(novf, np.uint32), gaps=dict(rec_idx=z(gi, np.uint32), off=z(goff, np.uint32), len=z(glen, np.uint32)), gap_lost=0, dropped=0)


def alternating(n_fg=3, q=500 * US, s=240 * US, t_start=10 * MS):
    """One bg slice (tag 0) resident the whole time; fg requests alternate with it: bg first run, then fg/bg/fg/... each run q long, switch gap s.
    Returns (fg_launches, bg_launches) for make_launches."""
    t = t_start - 2 * MS
    bg_ons = [(t, t_start)]                       # bg run before the fg arrives (first run)
    fg_ons, t = [], t_start + s
    for i in range(n_fg):
        fg_ons.append((t, t + q)); t += q + s
        if i < n_fg - 1:
            bg_ons.append((t, t + q)); t += q + s
    bg_ons.append((t, t + 2 * MS))                # last bg run, after the fg is done
    return [(0, fg_ons)], [(0, bg_ons)]


# ---------------------------------------------------------------- intervals
def test_block_on_intervals_are_the_block_span_minus_its_logged_gaps():
    rec = make_launches([(0, [(0, 100_000), (150_000, 300_000), (360_000, 1_000_000)])], n_blocks=1)
    blk, s, e = block_on_intervals(rec)
    assert list(s) == [0, 150_000, 360_000] and list(e) == [100_000, 300_000, 1_000_000] and set(blk) == {0}


def test_block_on_intervals_without_gaps_is_one_interval_per_block():
    rec = make_launches([(0, [(5_000, 90_000)]), (1, [(100_000, 200_000)])], n_blocks=3)
    blk, s, e = block_on_intervals(rec)
    assert len(s) == 6 and (e > s).all()


def test_merge_intervals_joins_pieces_closer_than_the_merge_gap_and_keeps_distant_ones():
    s = np.array([0, 100_000, 130_000, 500_000]); e = np.array([100_000, 110_000, 400_000, 600_000])
    ms, me = merge_intervals(s, e, merge_ns=20_000)
    assert list(ms) == [0, 500_000] and list(me) == [400_000, 600_000]
    ms, me = merge_intervals(np.array([0, 110_000]), np.array([100_000, 200_000]), merge_ns=5_000)
    assert len(ms) == 2


# ---------------------------------------------------------------- the alternation case (largest-gap-only could not represent it)
def test_alternation_gives_several_gaps_per_block_and_runs_per_launch():
    fg_l, bg_l = alternating(n_fg=4)
    fg, bg = make_launches(fg_l), make_launches(bg_l)
    assert fg["ngaps"].max() == 3 and bg["ngaps"].max() == 4          # one gap per switch; a single largest-gap record would keep 1 of them
    ft, bt = launch_table(fg), launch_table(bg)
    assert len(ft["runs"][0][0]) == 4 and len(bt["runs"][0][0]) == 5   # fg: 4 runs; bg: first, 3 inner, last


def test_q_and_s_recover_the_quantum_and_switch_gap_from_gap_on_intervals():
    fg_l, bg_l = [], []
    for k in range(6):                      # six sliced fg requests, each its own bg slice (tag k)
        f, b = alternating(n_fg=5, q=500 * US, s=240 * US, t_start=10 * MS + k * 40 * MS)
        fg_l += [(k, f[0][1])]; bg_l += [(k, b[0][1])]
    fg, bg = launch_table(make_launches(fg_l, jitter_ns=500)), launch_table(make_launches(bg_l, jitter_ns=500, smid_offset=100))
    r = q_and_s(fg, bg, sliced_tags=np.arange(6))
    assert r["q_pooled_ms"] == pytest.approx(0.5, abs=0.01) and r["q_fg_ms"] == pytest.approx(0.5, abs=0.01) and r["q_bg_ms"] == pytest.approx(0.5, abs=0.01)
    assert r["s_ms"] == pytest.approx(0.24, abs=0.01) and r["n_neg_s"] == 0
    assert r["n_sliced"] == 6 and r["n_runs_fg"] == 6 * 3 and r["n_runs_bg"] == 6 * 4 and r["n_transitions"] == 6 * 8


def test_unequal_quanta_are_reported_separately():
    f, b = alternating(n_fg=5, q=400 * US, s=240 * US)
    fg = launch_table(make_launches(f)); bg = launch_table(make_launches(b))
    r = q_and_s(fg, bg, sliced_tags=np.array([0]))
    assert r["q_fg_ms"] == pytest.approx(0.4, abs=0.01) and r["q_bg_ms"] == pytest.approx(0.4, abs=0.01)


def test_a_launch_with_fewer_than_three_runs_contributes_no_complete_run():
    f, b = alternating(n_fg=2)
    r = q_and_s(launch_table(make_launches(f)), launch_table(make_launches(b)), sliced_tags=np.array([0]))
    assert r["n_runs_fg"] == 0           # 2 fg runs: first and last only


# ---------------------------------------------------------------- P6 overlap (concurrency) vs alternation
def test_alternation_has_zero_overlaps_even_though_block_intervals_intersect():
    fg_l, bg_l = alternating(n_fg=4)
    fg, bg = make_launches(fg_l), make_launches(bg_l, smid_offset=0)
    r = count_overlaps(fg, bg)
    assert r["n_overlap"] == 0 and r["n_fg_blocks"] == 8 and r["n_untrusted_fg"] == 0
    # whole-span intersection is NOT overlap: the bg block's [start, end] contains the fg blocks, which is what a largest-gap-only check would call concurrency
    assert int(fg["t0"].min()) > int(bg["t0"].min()) and int(fg["t1"].max()) < int(bg["t1"].max())


def test_concurrent_execution_is_detected_and_split_by_sm():
    fg = make_launches([(0, [(100 * US, 900 * US)])], n_blocks=4)                   # fg runs 100..900 us on SMs 0-3
    bg = make_launches([(0, [(0, 500 * US), (600 * US, 2000 * US)])], n_blocks=4)    # bg runs 0..500 and 600..: overlaps the fg
    r = count_overlaps(fg, bg)
    assert r["n_overlap"] == 4 and r["n_overlap_same_sm"] == 4
    bg2 = make_launches([(0, [(0, 500 * US), (600 * US, 2000 * US)])], n_blocks=4, smid_offset=50)
    r2 = count_overlaps(fg, bg2)
    assert r2["n_overlap"] == 4 and r2["n_overlap_same_sm"] == 0 and r2["n_overlap_diff_sm"] == 4


def test_overlaps_of_10_us_or_less_are_ties_not_overlaps():
    fg = make_launches([(0, [(500 * US, 900 * US)])], n_blocks=2)
    bg = make_launches([(0, [(0, 505 * US), (900 * US, 2000 * US)])], n_blocks=2)    # 5 us intersection
    r = count_overlaps(fg, bg)
    assert r["n_overlap"] == 0 and r["n_ties"] == 2


def test_blocks_with_overflow_are_untrusted_and_excluded():
    fg = make_launches([(0, [(100 * US, 900 * US)])], n_blocks=4)
    fg["novf"][1] = 3                                                                  # block 1 lost gaps
    bg = make_launches([(0, [(0, 2000 * US)])], n_blocks=4)                            # bg runs straight through: every fg block overlaps
    r = count_overlaps(fg, bg)
    assert r["n_untrusted_fg"] == 1 and r["n_overlap"] == 3


# ---------------------------------------------------------------- sliced spans, recorded interval, P7, P8, offsets, P3
def test_sliced_mask_uses_alone_span_plus_two_switch_gaps():
    spans = np.array([0.30, 0.78, 0.90, 1.5]) * MS
    m = sliced_mask(spans, alone_span_ns=0.30 * MS, extra_ms=2 * 0.243)
    assert list(m) == [False, False, True, True]


def test_recorded_interval_keeps_only_fg_launches_wholly_inside_the_recorded_bg_interval():
    bg = make_launches([(0, [(10 * MS, 20 * MS)]), (1, [(20 * MS, 30 * MS)])])
    fg = make_launches([(0, [(5 * MS, 6 * MS)]), (1, [(12 * MS, 13 * MS)]), (2, [(29 * MS, 31 * MS)]), (3, [(25 * MS, 26 * MS)])])
    iv = recorded_interval(bg, fg)
    assert iv["start_ns"] == 10 * MS and iv["end_ns"] == 30 * MS
    assert sorted(iv["fg_tags"]) == [1, 3] and iv["n_bg_launches"] == 2


def test_preempted_fraction_counts_bg_blocks_with_a_gap_of_at_least_g_thr_and_whether_fg_ran_inside():
    fg_l, bg_l = alternating(n_fg=3)
    fg, bg = make_launches(fg_l), make_launches(bg_l)
    frac = preempted_fraction(bg, fg, g_thr_ns=41 * US)
    assert frac["fraction"] == 1.0 and frac["fraction_with_fg"] == 1.0 and frac["n_blocks"] == 8
    none = preempted_fraction(make_launches([(0, [(0, 3 * MS)])]), fg, g_thr_ns=41 * US)
    assert none["fraction"] == 0.0


def test_gap_contains_fg_uses_more_than_10_us_of_intersection():
    fs = np.array([100_000]); fe = np.array([200_000])
    assert list(gap_contains_fg(np.array([90_000, 195_000, 300_000]), np.array([150_000, 210_000, 400_000]), fs, fe, tol_ns=10_000)) == [True, False, False]


def test_offset_at_interpolates_between_the_two_sync_points():
    s0 = (7.0, 1e-5, 100.0); s1 = (7.001, 1e-5, 110.0)
    assert offset_at(105.0, s0, s1) == pytest.approx(7.0005)
    assert offset_at(100.0, s0, s1) == pytest.approx(7.0)


def test_p3_ripple_needs_two_local_minima_at_least_0p04_below_the_preceding_maximum():
    import pandas as pd
    lo = np.round(np.arange(0.0, 1.0, 0.05), 2)
    w = np.full(len(lo), 0.28)
    w[np.isclose(lo, 0.30)] = 0.30; w[np.isclose(lo, 0.35)] = 0.214; w[np.isclose(lo, 0.65)] = 0.364; w[np.isclose(lo, 0.80)] = 0.232
    df = pd.DataFrame(dict(lo=lo, hi=lo + 0.05, n=100, mean_wait_ms=w))
    r = p3_ripple(df)
    assert r["held"] and r["drop1_ms"] == pytest.approx(0.30 - 0.214, abs=1e-9) and r["drop2_ms"] == pytest.approx(0.364 - 0.232, abs=1e-9)
    flat = df.assign(mean_wait_ms=0.28)
    assert not p3_ripple(flat)["held"]
