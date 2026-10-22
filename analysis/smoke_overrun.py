"""Smoke-2 analysis: for each background token, how far past the NEXT frame arrival did it end?
token start = t_end - tok_ms; the arrival that matters is the first frame arrival after the token start; overrun_ms = (t_end - that arrival) * 1000 (> 0: the token was still
running when the frame arrived, i.e. the frame waited behind it). All times on the QPC timeline in seconds. Used by experiments/w4_smoke/smoke.py (step overrun)."""
import numpy as np


def overrun_stats(frame_arrivals_s, tok_end_s, tok_ms, period_ms):
    f = np.asarray(frame_arrivals_s, float)
    te, tm = np.asarray(tok_end_s, float), np.asarray(tok_ms, float)
    nan = float("nan")
    if len(te) == 0:
        return dict(n=0, frac_overrun=nan, overrun_ms_p50=nan, overrun_ms_p90=nan, overrun_ms_p99=nan, overrun_ms_max=nan, tok_ms_p50=nan, tok_ms_p90=nan, tok_ms_p99=nan, tok_ms_max=nan)
    start = te - tm / 1000.0
    idx = np.searchsorted(f, start, side="right")             # first arrival strictly after the token start
    ok = idx < len(f)
    over = (te[ok] - f[idx[ok]]) * 1000.0
    q = lambda x, p: float(np.percentile(x, p)) if len(x) else nan  # noqa: E731
    return dict(n=int(ok.sum()), frac_overrun=float((over > 0).mean()) if len(over) else nan, overrun_ms_p50=q(over, 50), overrun_ms_p90=q(over, 90), overrun_ms_p99=q(over, 99),
                overrun_ms_max=float(over.max()) if len(over) else nan, tok_ms_p50=q(tm, 50), tok_ms_p90=q(tm, 90), tok_ms_p99=q(tm, 99), tok_ms_max=float(tm.max()), period_ms=float(period_ms))
