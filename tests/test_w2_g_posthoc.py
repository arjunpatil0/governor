"""Post-hoc (exploratory) mechanism analysis for G: are the fg/bg overlaps a staggered per-SM context switch or genuine concurrency?
Synthetic timelines only. The registered analysis is not touched."""
import numpy as np

from test_w2_g_timeline import make_launches
from w2_g_posthoc import (boundary_distances, fine_tau_fit, overlap_pairs, same_sm_cases, switch_stagger, uniform_boundary_fraction)

US, MS = 1000, 1_000_000


def concat(recs):
    """Concatenate single-launch recs into one rec (gap record indices shifted)."""
    out = {k: [] for k in ("t0", "t1", "tg0", "gmax", "gbeg", "smid", "tag", "blk", "nreads", "ngaps", "novf")}
    gi, go, gl, base = [], [], [], 0
    for r in recs:
        for k in out:
            out[k].append(r[k])
        gi.append(r["gaps"]["rec_idx"].astype(np.int64) + base); go.append(r["gaps"]["off"]); gl.append(r["gaps"]["len"]); base += len(r["t0"])
    res = {k: np.concatenate(v) for k, v in out.items()}
    res["gaps"] = dict(rec_idx=np.concatenate(gi).astype(np.uint32), off=np.concatenate(go), len=np.concatenate(gl))
    res["gap_lost"] = 0; res["dropped"] = 0
    return res


def staggered(n_sm=4, step=100 * US, per_sm_gap=60 * US, run=2000 * US, same_sm_overlap=False):
    """One fg launch (tag 0) and one bg launch (tag 0), one block per SM. On SM i the bg run ends at E_i = 1000us + i*step and the fg run starts
    per_sm_gap later (so no same-SM overlap); a later bg run follows each fg run. Different SMs overlap because the ends are staggered."""
    fg, bg = [], []
    for i in range(n_sm):
        e = 1000 * US + i * step
        f0 = e + (-30 * US if same_sm_overlap else per_sm_gap)
        fg.append(make_launches([(0, [(f0, f0 + run)])], n_blocks=1, smid_offset=i))
        bg.append(make_launches([(0, [(0, e), (f0 + run + per_sm_gap, f0 + run + per_sm_gap + 400 * US)])], n_blocks=1, smid_offset=i))
    return concat(fg), concat(bg)


def test_staggered_switch_gives_different_sm_overlaps_bounded_by_the_stagger():
    fg, bg = staggered()
    p = overlap_pairs(fg, bg, fg_tags=[0])
    assert len(p["ov_ns"]) > 0
    assert (p["fg_sm"] != p["bg_sm"]).all()                          # no same-SM overlap by construction
    assert p["ov_ns"].max() <= 3 * 100 * US + 1                      # bounded by the total stagger (3 steps of 100 us)


def test_overlaps_sit_at_run_boundaries_not_spread_through_runs():
    fg, bg = staggered()
    p = overlap_pairs(fg, bg, fg_tags=[0])
    d = boundary_distances(p, fg, bg)
    assert (d <= 300 * US).all()                                     # within the stagger width of a boundary
    ref = uniform_boundary_fraction(fg, bg, [0], within_ns=300 * US, n=2000, seed=1)
    assert ref < 0.8                                                 # a uniformly placed point is NOT always that close: the concentration is informative


def test_switch_stagger_reports_spreads_and_per_sm_gap():
    fg, bg = staggered()
    t = switch_stagger(fg, bg, [0], min_sm=4)
    out = t[t.direction == "bg->fg"].iloc[0]
    assert out.n_sm == 4
    assert abs(out.out_end_spread_ns - 300 * US) < 1 and abs(out.in_start_spread_ns - 300 * US) < 1
    assert abs(out.per_sm_gap_min_ns - 60 * US) < 1 and out.n_sm_same_sm_overlap == 0
    assert out.cluster_overlap_ns > 0                                # different SMs overlap although every SM switches cleanly


def test_same_sm_overlap_is_listed_with_its_position_in_the_block():
    fg, bg = staggered(same_sm_overlap=True)
    p = overlap_pairs(fg, bg, fg_tags=[0])
    assert (p["fg_sm"] == p["bg_sm"]).any()
    cases = same_sm_cases(p, fg, bg, n=5)
    assert 1 <= len(cases) <= 5 and {"sm", "ov_us", "fg_pos_us", "bg_pos_us", "fg_block_us", "bg_block_us"} <= set(cases.columns)


def test_fine_tau_fit_resolves_below_the_10us_grid():
    rng = np.random.default_rng(0)
    r = rng.uniform(0, 1.0, 40000); b = rng.integers(0, 10, 40000)
    y = 0.035 + np.minimum(r, 0.2634) + rng.normal(0, 0.01, len(r))
    f = fine_tau_fit(r, y, b, n_boot=100, seed=3)
    assert abs(f["tau"] - 0.2634) < 0.003 and f["tau_hi"] > f["tau_lo"]


def test_overlap_roles_flag_overlaps_that_involve_a_block_first_or_last_interval():
    from w2_g_posthoc import overlap_roles
    # bg block on SM 0: intervals (0,1000) [first], (1500,2500) [last]; an interior interval needs 3: add (3000,3400) and make (1500,2500) interior.
    bg = make_launches([(0, [(0, 1000 * US), (1500 * US, 2500 * US), (3000 * US, 3400 * US)])], n_blocks=1, smid_offset=0)
    fg_edge = make_launches([(0, [(600 * US, 900 * US)])], n_blocks=1, smid_offset=0)            # overlaps the bg FIRST interval
    fg_mid = make_launches([(0, [(1800 * US, 2100 * US)])], n_blocks=1, smid_offset=0)           # overlaps the bg INTERIOR interval (fg interval is its own first and last)
    r_edge = overlap_roles(overlap_pairs(fg_edge, bg, [0]), fg_edge, bg)
    r_mid = overlap_roles(overlap_pairs(fg_mid, bg, [0]), fg_mid, bg)
    assert r_edge["bg_role"][0] == "first" and r_mid["bg_role"][0] == "interior"
    assert r_edge["fg_role"][0] == "only"
