"""End-to-end test of the Experiment G report driver (analysis/w2_g_analysis.py) on a SYNTHETIC run directory: pre-check (iii), P1-P8, coverage,
bgalone gaps. The timelines alternate fg and bg by suspend/resume of resident blocks (several gaps per block), the case a largest-gap-only
record cannot represent. No GPU, no real data."""
import json

import numpy as np
import pandas as pd
import pytest

from test_w2_g_timeline import make_launches
from w2_g_analysis import build_report
from w2_timeline import pack_rec

US, MS = 1000, 1_000_000
OFF = 7.0                      # synthetic GPU-timer-minus-QPC offset (s)
GT0 = int((100.0 + OFF) * 1e9)  # GPU ns of QPC time 100.0 s


def _fix(rec):
    rec["gbeg"] = rec["t0"].copy(); rec["nreads"] = ((rec["t1"] - rec["t0"]) // 2000 + 1).astype(np.uint32)
    return rec


def _save_rec(cd, rec, name):
    syn = [np.array([OFF, 1e-5, 100.0]), np.array([OFF, 1e-5, 110.0])]
    np.savez_compressed(cd / name, sync0=syn[0], sync1=syn[1], sms=36, **pack_rec(_fix(rec)))


def _fg_window(cd, arrivals, lat_ms=0.45, idx0=0):
    np.savez_compressed(cd / "fg_window.npz", arrival=arrivals, t_launch=arrivals, t_complete=arrivals + lat_ms * 1e-3, gpu_ms=np.full(len(arrivals), 0.1), idx0=idx0)


def _bg_window(cd, t0=100.0, t1=104.0, m=2.0e-3):
    s = np.arange(t0, t1, m); np.savez_compressed(cd / "bg_window.npz", t_start=s, t_end=s + m, gpu_ms=np.full(len(s), 2.0))


def _row(block, idx, cid, **kw):
    base = dict(block=block, cell_idx=idx, cell_id=cid, lat_mean_ms=0.40, lat_p50_ms=0.40, bg_mean_slice_ms=2.0, fg_gpu_p50_ms=0.1, rec_dropped_bg=0, rec_dropped_fg=0, flags="")
    base.update(kw); return base


def _small_fg_between_bg(n=40, t_ms=2.0, step_ms=3.0):
    """n fg requests (0.1 ms) each inside its own gap of ONE bg slice (tag 0): bg on-intervals are the complement. Returns (fg launches, bg launch, arrivals)."""
    fg, bg_ons, cur = [], [], 0
    for i in range(n):
        a = int(t_ms * MS + i * step_ms * MS)
        fg.append((i, [(a + 50 * US, a + 150 * US)]))
        bg_ons.append((cur, a + 50 * US - 240 * US)); cur = a + 150 * US + 240 * US
    bg_ons.append((cur, cur + 3 * MS))
    return fg, [(0, bg_ons)], np.array([100.0 + (t_ms + i * step_ms) * 1e-3 for i in range(n)])


def _g(ns):
    return [(t, [(s + GT0, e + GT0) for s, e in ons]) for t, ons in ns]


@pytest.fixture()
def run_dir(tmp_path):
    rows = []
    meta = dict(utc="x", part="G", smoke=True, admin=False, ac_plugged=True, ambient_c=25, armoury_mode="Performance", yaml_sha="y", dll_sha="d",
                git_head="abcdef123456", gpu="g", driver="d", hags={}, blocks=1)
    (tmp_path / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
    cells = tmp_path / "cells"; cells.mkdir()
    idx = 0

    def mk(cid, **kw):
        nonlocal idx
        cd = cells / f"b00_{idx:02d}_{cid}"; cd.mkdir(); rows.append(_row(0, idx, cid, **kw)); idx += 1
        return cd

    fg_l, bg_l, arr = _small_fg_between_bg()
    cd = mk("g_baseline", lat_mean_ms=0.40, lat_p50_ms=0.40)                       # fg alone: no bg
    _save_rec(cd, make_launches(_g([(i, [(50 * US + i * 3 * MS, 150 * US + i * 3 * MS)]) for i in range(40)])), "fg_rec.npz"); _fg_window(cd, arr)
    mk("g_baseline_off", lat_mean_ms=0.40, lat_p50_ms=0.40)
    cd = mk("g_T1_alone"); _save_rec(cd, make_launches(_g([(i, [(i * 20 * MS, i * 20 * MS + 1 * MS)]) for i in range(10)])), "fg_rec.npz"); _fg_window(cd, arr[:10], idx0=0)
    cd = mk("g_T4_alone"); _save_rec(cd, make_launches(_g([(i, [(i * 20 * MS, i * 20 * MS + 4 * MS)]) for i in range(10)])), "fg_rec.npz"); _fg_window(cd, arr[:10], idx0=0)
    # bgalone: 3 bg slices of 4 ms with one 240 us gap each (another GPU context)
    cd = mk("g_bgalone"); _save_rec(cd, make_launches(_g([(k, [(k * 5 * MS, k * 5 * MS + 2 * MS), (k * 5 * MS + 2 * MS + 240 * US, k * 5 * MS + 4 * MS)]) for k in range(3)])), "bg_rec.npz")
    for m in (0.5, 1, 2, 8):
        a_wait = {0.5: 0.226, 1: 0.255, 2: 0.287, 8: 0.298}[m]
        cd = mk(f"g_R{m}", lat_mean_ms=0.40 + a_wait, bg_mean_slice_ms=2.0)
        _save_rec(cd, make_launches(_g(fg_l)), "fg_rec.npz"); _save_rec(cd, make_launches(_g(bg_l), smid_offset=0), "bg_rec.npz"); _fg_window(cd, arr)
        cd = mk(f"g_R{m}_off", lat_mean_ms=0.40 + a_wait, bg_mean_slice_ms=2.0)
        rng = np.random.default_rng(int(m * 10)); a = 100.0 + np.sort(rng.uniform(0.2, 3.5, 2000)); _fg_window(cd, a, lat_ms=0.4 + a_wait); _bg_window(cd)
    # T4: 4 ms fg that alternates with the bg slice (q = 0.5 ms, s = 0.24 ms); many requests so P4/P5 have data
    t4_fg, t4_bg = [], []
    for k in range(8):
        f, b = [], []
        t = 10 * MS + k * 40 * MS; bo = [(t - 2 * MS, t)]; fo = []; t += 240 * US
        for i in range(5):
            fo.append((t, t + 500 * US)); t += 740 * US
            if i < 4:
                bo.append((t, t + 500 * US)); t += 740 * US
        bo.append((t, t + 2 * MS)); t4_fg.append((k, fo)); t4_bg.append((k, bo))
    cd = mk("g_T4"); _save_rec(cd, make_launches(_g(t4_fg)), "fg_rec.npz"); _save_rec(cd, make_launches(_g(t4_bg)), "bg_rec.npz"); _fg_window(cd, np.array([100.0 + (10 + 40 * k) * 1e-3 for k in range(8)]), lat_ms=4.0)
    cd = mk("g_T1"); _save_rec(cd, make_launches(_g(t4_fg)), "fg_rec.npz"); _save_rec(cd, make_launches(_g(t4_bg)), "bg_rec.npz"); _fg_window(cd, np.array([100.0 + (10 + 40 * k) * 1e-3 for k in range(8)]), lat_ms=4.0)
    pd.DataFrame(rows).to_csv(tmp_path / "results.csv", index=False)
    return tmp_path


def test_report_on_synthetic_alternation_holds_p4_p5_p6_and_flags_the_precheck(run_dir):
    text = "\n".join(build_report(run_dir)[0])
    assert "pre-check (iii): PASS" in text
    assert "P1 HELD" in text
    assert "P6 HELD" in text and "fg blocks overlapping a bg block by more than 10 us: 0 of" in text
    assert "P4 HELD" in text and "P5 HELD" in text            # q = 0.5 ms, s = 0.24 ms by construction
    assert "g_bgalone" in text and "gaps with no foreground" in text


def test_report_marks_the_timeline_uninterpreted_when_precheck_iii_fails(run_dir):
    df = pd.read_csv(run_dir / "results.csv")
    df.loc[df.cell_id == "g_baseline", "lat_p50_ms"] = 0.60            # +50% latency from instrumentation
    df.to_csv(run_dir / "results.csv", index=False)
    text = "\n".join(build_report(run_dir)[0])
    assert "pre-check (iii): FAIL" in text and "NOT interpreted" in text


def test_report_detects_concurrency_in_the_timeline(run_dir):
    # make the T4 background run straight through the fg (no suspension): that is concurrency, P6 must not hold
    t4_bg = [(k, [(10 * MS + k * 40 * MS - 2 * MS + GT0, 10 * MS + k * 40 * MS + 6 * MS + GT0)]) for k in range(8)]
    cd = next((run_dir / "cells").glob("b00_*_g_T4"))
    _save_rec(cd, make_launches(t4_bg), "bg_rec.npz")
    text = "\n".join(build_report(run_dir)[0])
    assert "P6 DID NOT HOLD" in text
