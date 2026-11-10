"""Pure metric functions for sprint R1 (definitions from docs/R1_PREREG.md).

Percentiles use numpy.percentile with method='linear' (PERCENTILE_METHOD). A hitch is a frame strictly longer than 1.5 x the period, i.e. > 25.0 ms at 60 fps.
low1_fps = 1000 / mean of the slowest 1% of frame times, where the 1% is ceil(n/100) frames (at least 1; integer arithmetic, so 700 frames give 7, not 8).
Predictability (see predictability()): the prereg says "the cadence of the previous N frames"; N frames give N-1 intervals, so the prediction for frame i is
start[i-1] + (start[i-1] - start[i-N]) / (N-1), and the first predicted frame is index N, which is why N+1 frames are the minimum."""
import csv
import io
import math
from pathlib import Path

import numpy as np

PERCENTILE_METHOD = "linear"
PERIOD_MS = 1000.0 / 60.0
HITCH_MS = 25.0
BASELINE_PERIOD_MS = 16.67        # the prereg's literal baseline: "previous start plus 16.67 ms"
PRED_N = 8
SENSITIVITY_N = (4, 16)
PASS_P95_MS = 1.5
PASS_MEDIAN_IDLE_MS = 3.0


def _pct(a, q):
    return float(np.percentile(a, q, method=PERCENTILE_METHOD))


def frame_metrics(frames_ms, period_ms=PERIOD_MS):
    a = np.asarray(frames_ms, dtype=float)
    if a.size == 0:
        raise ValueError("no frame times")
    if not np.all(np.isfinite(a)) or np.any(a < 0):
        raise ValueError("frame times must be finite and non-negative")
    n = int(a.size)
    thr = round(1.5 * period_ms, 9)
    k = max(1, -(-n // 100))                                   # ceil(n / 100) without float error
    slowest = np.sort(a)[-k:]
    return {"p50": _pct(a, 50), "p99": _pct(a, 99), "low1_fps": 1000.0 / float(np.mean(slowest)), "hitch_share": 100.0 * float(np.sum(a > thr)) / n,
            "n": n, "hitch_threshold_ms": thr, "percentile_method": PERCENTILE_METHOD}


def cell_frame_metrics(frames, t_open, t_close, qpc_hz):
    """Window selection on QPC time (seconds = counter / qpc_hz in [t_open, t_close)), dominant swapchain of the window; dropped frames stay.
    -> dict(frame=frame_metrics, gpu_busy_ms_median, n_dropped, swapchain, frames=<selected Frame list>)"""
    from tools.realgame.presentmon import dominant_swapchain, frames_of_swapchain, to_seconds
    win = [f for f in frames if t_open <= to_seconds(f.t_cpu_start, qpc_hz) < t_close]
    if not win:
        raise ValueError(f"no PresentMon frames inside the window [{t_open}, {t_close})")
    sc = dominant_swapchain(win)
    win = frames_of_swapchain(win, sc)
    return {"frame": frame_metrics([f.frame_ms for f in win]), "gpu_busy_ms_median": float(np.median([f.gpu_busy_ms for f in win])),
            "n_dropped": sum(1 for f in win if not f.displayed), "swapchain": sc, "frames": win}


def count_tokens(tokens_csv, t_start, t_end):
    """Rows with kind == 'token' and t_start <= t_tok_end_s < t_end."""
    text = tokens_csv.read_text() if isinstance(tokens_csv, Path) else str(tokens_csv)
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames or not {"t_tok_end_s", "dur_ms", "kind"} <= set(reader.fieldnames):
        raise ValueError(f"tokens csv needs columns t_tok_end_s,dur_ms,kind; got {reader.fieldnames}")
    return sum(1 for r in reader if r["kind"] == "token" and t_start <= float(r["t_tok_end_s"]) < t_end)


def token_rate(tokens_csv, t_start, t_end):
    if not t_end > t_start:
        raise ValueError("t_end must be greater than t_start")
    return count_tokens(tokens_csv, t_start, t_end) / (t_end - t_start)


def _token_rows(tokens_csv):
    text = tokens_csv.read_text() if isinstance(tokens_csv, Path) else str(tokens_csv)
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames or not {"t_tok_end_s", "dur_ms", "kind"} <= set(reader.fieldnames):
        raise ValueError(f"tokens csv needs columns t_tok_end_s,dur_ms,kind; got {reader.fieldnames}")
    return [(float(r["t_tok_end_s"]), float(r["dur_ms"]), r["kind"]) for r in reader]


def count_resets(tokens_csv, t_start, t_end):
    """Rows with kind == 'reset' that overlap [t_start, t_end): a reset row's time is its end, its start is time - dur_ms."""
    return sum(1 for t, dur, kind in _token_rows(tokens_csv) if kind == "reset" and t - dur / 1000.0 < t_end and t >= t_start)


def max_token_gap(tokens_csv, t_start, t_end):
    """Largest gap in seconds between consecutive token ends (kind == 'token') inside [t_start, t_end), the window edges included
    (t_start -> first token, last token -> t_end), so that tokens stopping mid-window cannot pass. Fewer than 2 tokens: the whole window length."""
    ts = sorted(t for t, _, kind in _token_rows(tokens_csv) if kind == "token" and t_start <= t < t_end)
    if len(ts) < 2:
        return t_end - t_start
    pts = [t_start, *ts, t_end]
    return round(max(b - a for a, b in zip(pts, pts[1:])), 9)


def _err_stats(e):
    e = np.asarray(e, dtype=float)
    return {"p50": _pct(e, 50), "p95": _pct(e, 95), "p99": _pct(e, 99), "max": float(e.max()), "n": int(e.size)}


def _series_errors(series, N, baseline_ms=None):
    """Absolute errors in ms for frames N..len-1 of a series in seconds: cadence prediction, and (if baseline_ms) 'previous + baseline'."""
    s = np.asarray(series, dtype=float)
    idx = np.arange(N, len(s))
    pred = s[idx - 1] + (s[idx - 1] - s[idx - N]) / (N - 1)
    cad = np.abs(s[idx] - pred) * 1000.0
    base = np.abs(s[idx] - (s[idx - 1] + BASELINE_PERIOD_MS / 1000.0)) * 1000.0         # baseline: previous start + 16.67 ms (the prereg literal)
    return cad, base


def predictability_pooled(frame_lists, N, qpc_hz):
    """frame_lists: one list of Frame per cell (window-selected, one swapchain). Errors are computed within each cell and pooled."""
    if N < 2:
        raise ValueError("N must be at least 2 (N frames give N-1 intervals)")
    from tools.realgame.presentmon import to_seconds
    se, ee, sb, eb, idle = [], [], [], [], []
    for frames in frame_lists:
        if len(frames) < N + 1:
            raise ValueError(f"need at least N+1 = {N + 1} frames, got {len(frames)}")
        start = [to_seconds(f.t_cpu_start, qpc_hz) + f.gpu_latency_ms / 1000.0 for f in frames]       # GPU start proxy = CPU start + GPU latency
        end = [s + f.gpu_busy_ms / 1000.0 for s, f in zip(start, frames)]                            # end of GPU work = start + GPU busy
        a, b = _series_errors(start, N)
        c, d = _series_errors(end, N)
        se.append(a); sb.append(b); ee.append(c); eb.append(d)
        idle += [f.frame_ms - f.gpu_busy_ms for f in frames]
    se, ee, sb, eb = (np.concatenate(x) for x in (se, ee, sb, eb))
    idle_a = np.asarray(idle)
    out = {"N": N, "n_cells": len(frame_lists), "n_predictions": int(se.size), "start": _err_stats(se), "end": _err_stats(ee), "baseline_start": _err_stats(sb),
           "baseline_end": _err_stats(eb), "idle": {"p50": _pct(idle_a, 50), "p95": _pct(idle_a, 95), "p99": _pct(idle_a, 99), "min": float(idle_a.min()),
                                                    "max": float(idle_a.max()), "mean": float(idle_a.mean()), "n": int(idle_a.size)}}
    out["conditions"] = {"start_p95_ok": out["start"]["p95"] <= PASS_P95_MS, "end_p95_ok": out["end"]["p95"] <= PASS_P95_MS,
                         "median_idle_ok": out["idle"]["p50"] >= PASS_MEDIAN_IDLE_MS}
    out["pass"] = bool(all(out["conditions"].values()))
    return out


def predictability(frames, N=PRED_N, qpc_hz=None):
    """Cadence predictor over the previous N frames. N frames give N-1 intervals, so the prediction for frame i is start[i-1] + (start[i-1] - start[i-N]) / (N-1)
    (the mean of those N-1 intervals added to the previous start; the prereg's "mean interval over the window"). The baseline is "previous start + 16.67 ms" (literal 16.67 ms,
    not 1000/60). N = 8 decides; N = 4 and 16 are sensitivity checks. Errors are computed within each cell and pooled."""
    if qpc_hz is None:
        raise ValueError("qpc_hz is required (CPUStartQPC is a raw counter)")
    return predictability_pooled([frames], N, qpc_hz)


def predictability_report(frame_lists, qpc_hz):
    """N = 8 decides (primary); N = 4 and 16 are sensitivity checks that decide nothing."""
    return {"primary": predictability_pooled(frame_lists, PRED_N, qpc_hz), "sensitivity": {n: predictability_pooled(frame_lists, n, qpc_hz) for n in SENSITIVITY_N}}
