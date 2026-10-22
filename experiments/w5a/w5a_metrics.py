"""Per-cell metrics of W5a (registered in experiments/w5_governor.yaml): a cell is a warm-up (5 s) plus a measured window (30 s). Used by experiments/w5a/run.py.
frames: list of dicts with t_sched (QPC s) and lat_ms (from the SCHEDULED arrival); tokens: end times (QPC s) and durations (ms) from the token ring; energy in mJ from the NVML energy counter
read at the window start and end."""
import numpy as np


def ctrl_values(cell):
    """Control block [pacing (1 aligned, 0 unaligned duty), duty, guard_ms] for a pacing configuration."""
    return [1.0 if cell["mode"] == "aligned" else 0.0, float(cell["duty"]), float(cell["guard_ms"])]


def summarise_cell(frames, tok_end, tok_ms, t0, warm_s, measure_s, e_start_mj, e_end_mj, period_ms):
    if measure_s <= 0:
        raise ValueError("measure_s must be positive")
    w0, w1 = t0 + warm_s, t0 + warm_s + measure_s
    lat = np.array([f["lat_ms"] for f in frames if f["t_sched"] >= w0 and f["t_sched"] < w1], float)
    te, tm = np.asarray(tok_end, float), np.asarray(tok_ms, float)
    m = (te >= w0) & (te < w1)
    nan = float("nan")
    return dict(frames=int(len(lat)), miss_frac=float((lat > period_ms).mean()) if len(lat) else nan,
                fg_p50_ms=float(np.percentile(lat, 50)) if len(lat) else nan, fg_p99_ms=float(np.percentile(lat, 99)) if len(lat) else nan,
                bg_tokens=int(m.sum()), bg_tok_s=float(m.sum() / measure_s), tok_ms_p50=float(np.median(tm[m])) if m.any() else nan,
                tok_ms_p99=float(np.percentile(tm[m], 99)) if m.any() else nan, power_w=float((e_end_mj - e_start_mj) / 1000.0 / measure_s),
                energy_j=float((e_end_mj - e_start_mj) / 1000.0), j_per_token=float((e_end_mj - e_start_mj) / 1000.0 / m.sum()) if m.any() else nan)


def dirty_paths(porcelain):
    """Paths that make the working tree 'not clean' for a registered run: any tracked change and any untracked file OUTSIDE data/ (the run's own outputs go to data/)."""
    bad = []
    for line in porcelain.splitlines():
        if len(line) < 4:
            continue
        status, path = line[:2], line[3:].strip().strip('"')
        if status == "??" and path.replace("\\", "/").startswith("data/"):
            continue
        bad.append(path)
    return bad
