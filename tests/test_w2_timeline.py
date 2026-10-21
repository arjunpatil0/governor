"""Pure-function parts of Experiment G's pre-checks (analysis/w2_timeline.py): timer resolution, host<->GPU timebase, overhead acceptance.
Registered in experiments/w2_colocation_addendum_globaltimer_2026-10-22.md (pre-checks i-iii)."""
import numpy as np
import pytest

from w2_timeline import best_sync, block_times_in_window, overhead_check, resolution_ns


def test_resolution_is_the_smallest_nonzero_difference_of_consecutive_reads():
    reads = np.array([1000, 1000, 1032, 1032, 1096, 1128], dtype=np.uint64)
    assert resolution_ns(reads) == 32


def test_resolution_of_constant_reads_is_nan_not_zero():
    assert np.isnan(resolution_ns(np.array([5, 5, 5], dtype=np.uint64)))


def test_best_sync_uses_the_minimum_round_trip_sample_and_reports_it():
    qb = np.array([10.0, 20.0, 30.0]); qa = np.array([10.004, 20.0001, 30.002])
    gt = np.array([(10.002 + 7.0) * 1e9, (20.00005 + 7.0) * 1e9, (30.001 + 7.0) * 1e9])
    off, rt = best_sync(qb, qa, gt)
    assert off == pytest.approx(7.0, abs=1e-9) and rt == pytest.approx(0.0001)


def test_block_times_in_window_flags_blocks_outside_the_host_launch_complete_window():
    off = 7.0
    t0 = np.array([(100.001 + off) * 1e9, (100.010 + off) * 1e9], dtype=np.uint64)
    t1 = np.array([(100.002 + off) * 1e9, (100.0125 + off) * 1e9], dtype=np.uint64)
    r = block_times_in_window(t0, t1, off, t_launch=100.0, t_done=100.011, tol_s=0.0001)
    assert r["n"] == 2 and r["n_outside"] == 1 and r["frac_outside"] == 0.5


def test_overhead_check_accepts_within_5_percent_and_0p03_ms():
    r = overhead_check(on_lat_p50_ms=1.00, off_lat_p50_ms=1.04, on_wait_ms=0.30, off_wait_ms=0.29)
    assert r["pass"] and r["lat_rel_diff"] == pytest.approx(0.04 / 1.04) and r["wait_abs_diff_ms"] == pytest.approx(0.01)


@pytest.mark.parametrize("on_lat,on_wait", [(1.20, 0.29), (1.00, 0.35)])
def test_overhead_check_fails_on_either_criterion(on_lat, on_wait):
    assert not overhead_check(on_lat, 1.04, on_wait, 0.29)["pass"]


def test_pack_and_unpack_rec_roundtrip_and_shrinks():
    from w2_timeline import pack_rec, unpack_rec
    n = 1000
    rng = np.random.default_rng(1)
    base = 1_700_000_000_000_000_000
    t0 = (base + np.sort(rng.integers(0, 5_000_000_000, n))).astype(np.uint64)
    rec = dict(t0=t0, t1=t0 + rng.integers(1000, 900_000, n).astype(np.uint64), gmax=rng.integers(0, 500_000, n).astype(np.uint64),
               gbeg=None, smid=rng.integers(0, 36, n).astype(np.uint32), tag=rng.integers(0, 50, n).astype(np.uint32),
               blk=rng.integers(0, 216, n).astype(np.uint32), dropped=3)
    rec["gbeg"] = rec["t0"] + (rng.random(n) * (rec["t1"] - rec["t0"])).astype(np.uint64)
    back = unpack_rec(pack_rec(rec))
    for k in ("t0", "t1", "gmax", "gbeg", "smid", "tag", "blk"):
        assert (back[k] == rec[k]).all() and back[k].dtype == rec[k].dtype
    assert back["dropped"] == 3
    packed = pack_rec(rec)
    assert sum(v.nbytes for v in packed.values() if hasattr(v, "nbytes")) < 0.65 * sum(rec[k].nbytes for k in ("t0", "t1", "gmax", "gbeg", "smid", "tag", "blk"))


def test_pack_rec_rejects_a_block_longer_than_the_32_bit_range():
    from w2_timeline import pack_rec
    rec = dict(t0=np.array([0], dtype=np.uint64), t1=np.array([5_000_000_000], dtype=np.uint64), gmax=np.array([1], dtype=np.uint64),
               gbeg=np.array([0], dtype=np.uint64), smid=np.array([0], dtype=np.uint32), tag=np.array([0], dtype=np.uint32),
               blk=np.array([0], dtype=np.uint32), dropped=0)
    with pytest.raises(ValueError):
        pack_rec(rec)
