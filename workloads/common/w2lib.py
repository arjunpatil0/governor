"""ctypes wrapper for workloads/background/build/w2_kernels.dll, shared by the W2 pilot, harness and tests.
No CPU fallback: if the DLL or CUDA is missing, init exits with a message (callers that want to skip catch SystemExit)."""
import ctypes
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
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
