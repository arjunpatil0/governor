"""Experiment G (experiments/w2_colocation_addendum_globaltimer_2026-10-22.md): pure helpers for the pre-checks (i)-(iii).
Pre-check (i) timer resolution, (ii) shared timebase vs host QPC, (iii) instrumentation overhead. No GPU; tested in tests/test_w2_timeline.py."""
import numpy as np


def resolution_ns(reads):
    """Smallest nonzero difference between consecutive %globaltimer reads (ns); NaN if every read is equal."""
    d = np.diff(np.asarray(reads).astype(np.int64))
    d = d[d > 0]
    return float(d.min()) if len(d) else float("nan")


def best_sync(qpc_before, qpc_after, gt_ns):
    """GPU-timer-to-QPC offset (s) such that qpc = gt*1e-9 - offset, from the minimum-round-trip sample; also returns that round trip (s)."""
    qb, qa, gt = (np.asarray(x, dtype=float) for x in (qpc_before, qpc_after, gt_ns))
    rt = qa - qb
    i = int(np.argmin(rt))
    return float(gt[i] * 1e-9 - (qb[i] + qa[i]) / 2.0), float(rt[i])


def block_times_in_window(t0_ns, t1_ns, offset_s, t_launch, t_done, tol_s):
    """Blocks whose [start, end] (converted to QPC seconds) fall outside the host window [t_launch - tol, t_done + tol]. t_launch/t_done: arrays per block or scalars."""
    s = np.asarray(t0_ns, dtype=float) * 1e-9 - offset_s
    e = np.asarray(t1_ns, dtype=float) * 1e-9 - offset_s
    out = (s < np.asarray(t_launch) - tol_s) | (e > np.asarray(t_done) + tol_s)
    n = int(len(s))
    return dict(n=n, n_outside=int(out.sum()), frac_outside=float(out.mean()) if n else float("nan"))


def overhead_check(on_lat_p50_ms, off_lat_p50_ms, on_wait_ms, off_wait_ms, rel_tol=0.05, wait_tol_ms=0.03):
    """Pre-check (iii) acceptance: median latency within 5% (relative to the uninstrumented twin) and the observed wait within 0.03 ms."""
    rel = abs(on_lat_p50_ms - off_lat_p50_ms) / off_lat_p50_ms
    dw = abs(on_wait_ms - off_wait_ms)
    return dict(lat_rel_diff=rel, wait_abs_diff_ms=dw, **{"pass": bool(rel <= rel_tol and dw <= wait_tol_ms)})


# ---- compact storage of the per-block records (raw timestamps would be gigabytes over 140 cells)
_REC_FIELDS = ("t0", "t1", "gmax", "gbeg", "smid", "tag", "blk")


def pack_rec(rec):
    """Per-block records -> smaller arrays: t0 relative to the first start (int64), durations / gaps as uint32 ns, smid uint8, blk uint16."""
    t0 = np.asarray(rec["t0"], dtype=np.uint64)
    base = np.uint64(t0.min()) if len(t0) else np.uint64(0)
    dur = np.asarray(rec["t1"], dtype=np.uint64) - t0
    gbeg_off = np.asarray(rec["gbeg"], dtype=np.uint64) - t0
    gmax = np.asarray(rec["gmax"], dtype=np.uint64)
    if len(t0) and max(int(dur.max()), int(gmax.max()), int(gbeg_off.max())) >= 2 ** 32:
        raise ValueError("a block duration or gap exceeds the 32-bit nanosecond range (4.29 s); refusing to truncate")
    return dict(base=np.array(base, dtype=np.uint64), t0_rel=(t0 - base).astype(np.int64), dur=dur.astype(np.uint32), gmax=gmax.astype(np.uint32),
                gbeg_off=gbeg_off.astype(np.uint32), smid=np.asarray(rec["smid"], dtype=np.uint8), tag=np.asarray(rec["tag"], dtype=np.uint32),
                blk=np.asarray(rec["blk"], dtype=np.uint16), dropped=np.array(int(rec.get("dropped", 0))))


def unpack_rec(p):
    base = np.uint64(p["base"])
    t0 = p["t0_rel"].astype(np.uint64) + base
    return dict(t0=t0, t1=t0 + p["dur"].astype(np.uint64), gmax=p["gmax"].astype(np.uint64), gbeg=t0 + p["gbeg_off"].astype(np.uint64),
                smid=p["smid"].astype(np.uint32), tag=p["tag"].astype(np.uint32), blk=p["blk"].astype(np.uint32), dropped=int(p["dropped"]))
