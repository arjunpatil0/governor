"""GPU integration test of the instrumented (recording) W2 kernels used by Experiment G: skipped when the DLL is not built or CUDA is
unavailable; never falls back to CPU. Addendum: experiments/w2_colocation_addendum_globaltimer_2026-10-22.md."""
import numpy as np
import pytest

from w2lib import DLL


@pytest.fixture(scope="module")
def w():
    if not DLL.exists():
        pytest.skip("w2_kernels.dll not built")
    from w2lib import W2
    try:
        return W2()
    except SystemExit as e:
        pytest.skip(str(e))


def test_gt_resolution_reads_are_nondecreasing_and_resolve_a_tick(w):
    reads = w.gt_resolution(20000)
    assert len(reads) == 20000 and (np.diff(reads.astype(np.int64)) >= 0).all() and reads[-1] > reads[0]


def test_gt_sync_gives_an_offset_and_a_round_trip_under_a_millisecond(w):
    off, rt = w.gt_sync(200)
    assert np.isfinite(off) and 0 < rt < 1e-3


def test_fg_run_rec_records_every_block_of_the_requested_requests(w):
    off, rt = w.gt_sync(100)
    arr = w.now() + 0.05 + np.arange(30) * 0.003
    tl, tc, g, rec = w.fg_run_rec(1, arr, 2000, rec_from=10, cap_blocks=100000)
    blocks = w.sms * 6
    assert len(rec["t0"]) == 20 * blocks and rec["dropped"] == 0
    assert (rec["t1"] >= rec["t0"]).all() and (rec["smid"] < w.sms).all() and (rec["gmax"] <= rec["t1"] - rec["t0"]).all()
    assert set(np.unique(rec["tag"])) == set(range(10, 30)) and set(np.unique(rec["blk"])) == set(range(blocks))
    # every recorded block lies inside its request's host launch..complete window (+ round trip)
    t0s = rec["t0"] * 1e-9 - off; t1s = rec["t1"] * 1e-9 - off
    lo = tl[rec["tag"]] - 2 * rt - 1e-4; hi = tc[rec["tag"]] + 2 * rt + 1e-4
    assert (t0s >= lo).all() and (t1s <= hi).all()


def test_bg_until_rec_respects_the_buffer_cap_and_counts_dropped_slices(w):
    blocks = w.sms * 6
    ts, te, g, rec = w.bg_until_rec([4000], w.now() + 0.15, t_rec0=0.0, cap_blocks=blocks * 5)
    assert len(rec["t0"]) == blocks * 5 and rec["dropped"] == len(ts) - 5 and rec["dropped"] > 0
    assert set(np.unique(rec["tag"])) == set(range(5))


def test_bg_until_rec_starts_recording_at_t_rec0(w):
    t_rec0 = w.now() + 0.1
    ts, te, g, rec = w.bg_until_rec([4000], w.now() + 0.3, t_rec0=t_rec0, cap_blocks=500000)
    first = int(rec["tag"].min())
    assert ts[first] >= t_rec0 and (first == 0 or ts[first - 1] < t_rec0)


def test_two_streams_in_one_process_share_the_timebase(w):
    off, rt = w.gt_sync(100)
    r = w.two_streams_rec(3000, 1000, delay_s=0.002)
    for tag, (tl, td) in {0: (r["a_launch"], r["a_done"]), 1: (r["b_launch"], r["b_done"])}.items():
        m = r["rec"]["tag"] == tag
        assert m.any()
        t0s = r["rec"]["t0"][m] * 1e-9 - off; t1s = r["rec"]["t1"][m] * 1e-9 - off
        assert (t0s >= tl - 2 * rt - 1e-4).all() and (t1s <= td + 2 * rt + 1e-4).all()
