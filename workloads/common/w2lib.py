"""ctypes wrapper for workloads/background/build/w2_kernels.dll, shared by the W2 pilot, harness and tests.
No CPU fallback: if the DLL or CUDA is missing, init exits with a message (callers that want to skip catch SystemExit)."""
import ctypes
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "analysis"))   # w2_timeline (gt_sync)
DLL = ROOT / "workloads" / "background" / "build" / "w2_kernels.dll"
BPS = 6   # blocks per SM for full-GPU kernels (same as W1 fma)
P = ctypes.POINTER
dbl = lambda a: a.ctypes.data_as(P(ctypes.c_double))
i32 = lambda a: a.ctypes.data_as(P(ctypes.c_int))


class W2:
    def __init__(self):
        if not DLL.exists():
            sys.exit(f"FATAL {DLL} not built (workloads\\background\\build.bat w2_kernels.cu build\\w2_kernels.dll -shared)")
        self.d = ctypes.CDLL(str(DLL))
        self.d.w2_last_error.restype = ctypes.c_char_p
        self.d.w2_qpc_now.restype = ctypes.c_double
        sms = ctypes.c_int()
        if self.d.w2_init(ctypes.byref(sms)) != 0:
            sys.exit(f"FATAL w2_init: {self.d.w2_last_error().decode()} (no CPU fallback)")
        self.sms = sms.value
        for f in ("w2_rec_used", "w2_rec_dropped"):
            getattr(self.d, f).restype = ctypes.c_size_t
        self.d.w2_rec_init.argtypes = [ctypes.c_size_t, ctypes.c_size_t]
        self.d.w2_gap_count.restype = ctypes.c_size_t

    def now(self):
        return self.d.w2_qpc_now()

    def chk(self, rc, what):
        if rc != 0:
            sys.exit(f"FATAL {what}: rc={rc} {self.d.w2_last_error().decode()}")

    def bg_until(self, kind, units, t_stop, cap=200_000, bps=BPS, duty=1.0):
        """Back-to-back slices until QPC time t_stop. duty < 1 inserts a spin-wait idle gap after each slice so busy/(busy+idle) = duty."""
        units = np.ascontiguousarray(units, dtype=np.int32)
        ts, te, g = (np.zeros(cap) for _ in range(3)); n = ctypes.c_int()
        self.chk(self.d.w2_bg_until(kind, i32(units), len(units), bps, ctypes.c_double(t_stop), dbl(ts), dbl(te), dbl(g), cap,
                                    ctypes.byref(n), ctypes.c_double(duty)), "bg_until")
        return ts[:n.value], te[:n.value], g[:n.value]

    def fg_run(self, kind, arrivals, units, bps=BPS):
        arrivals = np.ascontiguousarray(arrivals, dtype=np.float64); n = len(arrivals)
        tl, tc, g = (np.zeros(n) for _ in range(3))
        self.chk(self.d.w2_fg_run(kind, n, dbl(arrivals), int(units), bps, dbl(tl), dbl(tc), dbl(g)), "fg_run")
        return tl, tc, g

    # ---- Experiment G instrumentation (experiments/w2_colocation_addendum_globaltimer_2026-10-22.md); fma kernel only
    def set_gap_stride(self, stride):
        self.chk(self.d.w2_set_gap_stride(int(stride)), "set_gap_stride")

    def rec_init(self, cap_blocks, gap_cap=8_000_000):
        self.chk(self.d.w2_rec_init(int(cap_blocks), int(gap_cap)), "rec_init")

    def rec_fetch(self):
        n = int(self.d.w2_rec_used())
        u64 = lambda: np.zeros(n, dtype=np.uint64); u32 = lambda: np.zeros(n, dtype=np.uint32)
        t0, t1, tg0, gmax, gbeg = u64(), u64(), u64(), u64(), u64(); smid, tag, blk, nreads, ngaps, novf = u32(), u32(), u32(), u32(), u32(), u32()
        ptr = lambda a: a.ctypes.data_as(ctypes.c_void_p)
        self.chk(self.d.w2_rec_fetch(ptr(t0), ptr(t1), ptr(tg0), ptr(gmax), ptr(gbeg), ptr(smid), ptr(tag), ptr(blk), ptr(nreads), ptr(ngaps), ptr(novf)), "rec_fetch")
        total = int(self.d.w2_gap_count()); ng = min(total, 8_000_000)
        gi, go, gl = (np.zeros(ng, dtype=np.uint32) for _ in range(3))
        self.chk(self.d.w2_gap_fetch(ptr(gi), ptr(go), ptr(gl)), "gap_fetch")
        return dict(t0=t0, t1=t1, tg0=tg0, gmax=gmax, gbeg=gbeg, smid=smid, tag=tag, blk=blk, nreads=nreads, ngaps=ngaps, novf=novf,
                    gaps=dict(rec_idx=gi, off=go, len=gl), gap_lost=max(0, total - ng), dropped=int(self.d.w2_rec_dropped()))

    def bg_until_rec(self, units, t_stop, t_rec0, cap_blocks, cap=200_000, bps=BPS, duty=1.0, gap_k=32):
        self.rec_init(cap_blocks)
        units = np.ascontiguousarray(units, dtype=np.int32)
        ts, te, g = (np.zeros(cap) for _ in range(3)); n = ctypes.c_int()
        self.chk(self.d.w2_bg_until_rec(1, i32(units), len(units), bps, ctypes.c_double(t_stop), dbl(ts), dbl(te), dbl(g), cap,
                                        ctypes.byref(n), ctypes.c_double(duty), ctypes.c_double(t_rec0), int(gap_k)), "bg_until_rec")
        return ts[:n.value], te[:n.value], g[:n.value], self.rec_fetch()

    def fg_run_rec(self, kind, arrivals, units, rec_from, cap_blocks, bps=BPS, gap_k=8):
        self.rec_init(cap_blocks)
        arrivals = np.ascontiguousarray(arrivals, dtype=np.float64); n = len(arrivals)
        tl, tc, g = (np.zeros(n) for _ in range(3))
        self.chk(self.d.w2_fg_run_rec(kind, n, dbl(arrivals), int(units), bps, dbl(tl), dbl(tc), dbl(g), int(rec_from), int(gap_k)), "fg_run_rec")
        return tl, tc, g, self.rec_fetch()

    def gt_resolution(self, n=20000):
        out = np.zeros(n, dtype=np.uint64)
        self.chk(self.d.w2_gt_resolution(n, out.ctypes.data_as(ctypes.c_void_p)), "gt_resolution")
        return out

    def gt_sync(self, n=200):
        """(offset_s, round_trip_s): qpc = globaltimer*1e-9 - offset_s, from the minimum-round-trip sample."""
        from w2_timeline import best_sync
        qb, qa = np.zeros(n), np.zeros(n); gt = np.zeros(n, dtype=np.uint64)
        self.chk(self.d.w2_gt_sync(n, dbl(qb), dbl(qa), gt.ctypes.data_as(ctypes.c_void_p)), "gt_sync")
        return best_sync(qb, qa, gt)

    def gt_sync3(self, n=200):
        """(offset_s, round_trip_s, qpc_time_s) of the minimum-round-trip sample."""
        from w2_timeline import best_sync_t
        qb, qa = np.zeros(n), np.zeros(n); gt = np.zeros(n, dtype=np.uint64)
        self.chk(self.d.w2_gt_sync(n, dbl(qb), dbl(qa), gt.ctypes.data_as(ctypes.c_void_p)), "gt_sync")
        return best_sync_t(qb, qa, gt)

    def two_streams_rec(self, units_a, units_b, delay_s):
        self.rec_init(2 * self.sms * BPS)
        t = np.zeros(4)
        self.chk(self.d.w2_two_streams_rec(int(units_a), int(units_b), ctypes.c_double(delay_s), dbl(t)), "two_streams_rec")
        return dict(a_launch=t[0], a_done=t[1], b_launch=t[2], b_done=t[3], rec=self.rec_fetch())


def calibrate(w, kind, probe_units):
    """host duration (ms) of one slice vs units: linear fit a + b*units from constant-unit runs."""
    xs, ys = [], []
    for u in probe_units:
        ts, te, _ = w.bg_until(kind, [u], w.now() + 0.5)
        xs.append(u); ys.append(float(np.median((te - ts)[3:])) * 1e3)
    b, a = np.polyfit(xs, ys, 1)
    return dict(a_ms=float(a), b_ms_per_unit=float(b), probes=dict(zip(map(str, xs), ys)))


def units_for(cal, ms):
    return np.maximum(1, np.rint((np.asarray(ms) - cal["a_ms"]) / cal["b_ms_per_unit"])).astype(np.int32)
