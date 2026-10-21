#!/usr/bin/env python3
"""Experiment G pre-checks (i)-(iii) from a `run.py --part G --precheck` directory. Smoke-grade: unlocked clocks, 3 blocks; the registered
acceptance for (iii) is re-evaluated on the full G data. Usage: python analysis/w2_g_prechecks.py [--dir data/raw/w2_G_precheck/<stamp>]
Writes data/w2_G_prechecks.md."""
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from w2_timeline import block_times_in_window, overhead_check, resolution_ns, unpack_rec

ROOT = Path(__file__).resolve().parents[1]
FENCE, FENCE_END = "```" + chr(10), chr(10) + "```"


def _rec(path):
    z = np.load(path)
    r = unpack_rec({k: z[k] for k in ("base", "t0_rel", "dur", "gmax", "gbeg_off", "smid", "tag", "blk", "nreads", "dropped")})
    return r, z["sync0"], z["sync1"]


def check_i_ii_a(d):
    z = np.load(d / "gtprobe.npz")
    res = resolution_ns(z["reads"]); reads = z["reads"].astype(np.int64)
    r = unpack_rec({k: z[k] for k in ("base", "t0_rel", "dur", "gmax", "gbeg_off", "smid", "tag", "blk", "nreads", "dropped")})
    off = (float(z["off"]) + float(z["off2"])) / 2; drift = abs(float(z["off2"]) - float(z["off"]))
    tol = 2 * max(float(z["rt"]), float(z["rt2"])) + 1e-9 * (res if np.isfinite(res) else 0) + drift + 1e-4
    a_l, a_d, b_l, b_d = z["times"]
    out = {}
    for tag, (tl, td) in {0: (a_l, a_d), 1: (b_l, b_d)}.items():
        m = r["tag"] == tag
        out[tag] = block_times_in_window(r["t0"][m], r["t1"][m], off, tl, td, tol)
    return dict(res_ns=res, frac_equal=float(np.mean(np.diff(reads) == 0)), offset_drift_s=drift, rt_s=(float(z["rt"]), float(z["rt2"])),
                tol_s=tol, sms=int(z["sms"]), streams=out)


def check_ii_b(d, df):
    rows = []
    for _, r0 in df.iterrows():
        cd = d / "cells" / f"b{int(r0.block):02d}_{int(r0.cell_idx):02d}_{r0.cell_id}"
        if not (cd / "fg_rec.npz").exists() or not (cd / "bg_rec.npz").exists():
            continue
        fr, fs0, fs1 = _rec(cd / "fg_rec.npz"); br, bs0, bs1 = _rec(cd / "bg_rec.npz")
        fw = np.load(cd / "fg_window.npz")
        off_f = (fs0[0] + fs1[0]) / 2
        drift = max(abs(fs1[0] - fs0[0]), abs(bs1[0] - bs0[0]))
        tol = 2 * max(fs0[1], fs1[1], bs0[1], bs1[1]) + drift + 1e-4
        k = fr["tag"].astype(np.int64) - int(fw["idx0"])
        ok = (k >= 0) & (k < len(fw["t_launch"]))
        w = block_times_in_window(fr["t0"][ok], fr["t1"][ok], off_f, fw["t_launch"][k[ok]], fw["t_complete"][k[ok]], tol)
        rows.append(dict(block=int(r0.block), cell=r0.cell_id, offset_diff_s=float(fs0[0] - bs0[0]), rt_sum_s=float(fs0[1] + bs0[1]), dt_probe_s=float(abs(fs0[2] - bs0[2])),
                         drift_s=float(drift), fg_blocks=w["n"], fg_outside=w["n_outside"], fg_unmatched=int((~ok).sum()), bg_blocks=len(br["t0"]), bg_dropped=br["dropped"]))
    return pd.DataFrame(rows)


def ovh_table(d):
    f = d / "ovh.json"
    return pd.DataFrame(json.loads(f.read_text(encoding="utf-8"))) if f.exists() else pd.DataFrame()


def check_iii(df):
    d = df.set_index(["block", "cell_id"])
    rows = []
    for b in sorted(df.block.unique()):
        g = lambda c, col: float(d.loc[(b, c), col])
        on_wait = g("g_R2", "lat_mean_ms") - g("g_baseline", "lat_mean_ms"); off_wait = g("g_R2_off", "lat_mean_ms") - g("g_baseline_off", "lat_mean_ms")
        rows.append(dict(block=b, base_on_p50=g("g_baseline", "lat_p50_ms"), base_off_p50=g("g_baseline_off", "lat_p50_ms"),
                         r2_on_p50=g("g_R2", "lat_p50_ms"), r2_off_p50=g("g_R2_off", "lat_p50_ms"), wait_on=on_wait, wait_off=off_wait,
                         slice_on_ms=g("g_R2", "bg_mean_slice_ms"), slice_off_ms=g("g_R2_off", "bg_mean_slice_ms"),
                         gpu_on_ms=g("g_baseline", "fg_gpu_p50_ms"), gpu_off_ms=g("g_baseline_off", "fg_gpu_p50_ms")))
    t = pd.DataFrame(rows); m = t.median(numeric_only=True)
    chk = overhead_check(m.base_on_p50, m.base_off_p50, m.wait_on, m.wait_off)
    chk_r2 = overhead_check(m.r2_on_p50, m.r2_off_p50, m.wait_on, m.wait_off)
    return t, m, chk, chk_r2


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--dir")
    a = ap.parse_args()
    d = Path(a.dir) if a.dir else sorted((ROOT / "data" / "raw" / "w2_G_precheck").glob("*/results.csv"))[-1].parent
    meta = json.loads((d / "meta.json").read_text(encoding="utf-8")); df = pd.read_csv(d / "results.csv")
    i = check_i_ii_a(d); b = check_ii_b(d, df); t, m, chk, chk_r2 = check_iii(df); ov = ovh_table(d)
    L = ["# Experiment G pre-checks (i)-(iii), smoke-grade", "",
         f"Source `{d.relative_to(ROOT)}` | admin {meta['admin']} | unlocked clocks unless admin | git {meta['git_head'][:8]} dirty {meta.get('git_dirty')} | dll {meta['dll_sha']} | {meta['gpu']} driver {meta['driver']}",
         "NOT a result and NOT the registered acceptance: clocks were not locked (no admin), 3 blocks. The registered pre-check (iii) is re-evaluated on the full G data; this run only shows the instrumentation works and its rough cost.", "",
         "## (i) %globaltimer resolution", "",
         f"- smallest nonzero difference between consecutive reads in one block: **{i['res_ns']:.0f} ns** (fraction of identical consecutive reads {i['frac_equal']:.3f})", "",
         "## (ii-a) one process, two streams: shared timebase against host QPC", "",
         f"- GPU-timer/QPC offset drift over the test {i['offset_drift_s']*1e6:.1f} us; round trips {i['rt_s'][0]*1e6:.0f} / {i['rt_s'][1]*1e6:.0f} us; tolerance {i['tol_s']*1e6:.0f} us",
         *[f"- stream {'A' if k == 0 else 'B'}: {v['n']} blocks, {v['n_outside']} outside the host launch..done window" for k, v in i["streams"].items()], "",
         "## (ii-b) two processes (fg and bg children): same timebase", "",
         "Per cell with both recordings: the two processes read the GPU timer against QPC at the same instant (dt_probe_s apart); equal timebase if offset_diff_s is within rt_sum_s (the two minimum round trips) plus drift over dt_probe_s; and fg blocks outside their request's host launch..complete window.", "",
         FENCE + b.to_string(index=False) + FENCE_END if len(b) else "(no cell had both recordings)", "",
         "## (iii-a) controlled A/B in one process: plain vs recording kernel, alternating 0.25 s runs x 6, by gap-read stride (iterations between %globaltimer reads) and slice size", "",
         "ratio = median host slice duration (launch..sync) recording / plain. median_read_gap_ns = median over blocks of block duration / reads, the quantity G_thr = 20 x that is built from.", "",
         (FENCE + ov.round(4).to_string(index=False) + FENCE_END) if len(ov) else "(no ovh.json)", "",
         "## (iii-b) harness cells: instrumented vs uninstrumented twin (clocks NOT locked here: the fg-alone cells idle at ~210 MHz, so baseline-based numbers are not meaningful at smoke grade; the R_2 on/off columns are)", "",
         FENCE + t.round(4).to_string(index=False) + FENCE_END, "",
         f"- fg-alone latency p50, instrumented vs not: relative difference {chk['lat_rel_diff']*100:.1f}% (limit 5%)",
         f"- observed wait of R_2 (mean latency minus the same-condition fg-alone mean), instrumented {m.wait_on:.4f} ms vs {m.wait_off:.4f} ms: difference {chk['wait_abs_diff_ms']:.4f} ms (limit 0.03)",
         f"- R_2 latency p50 relative difference {chk_r2['lat_rel_diff']*100:.1f}%; bg mean slice {m.slice_on_ms:.4f} vs {m.slice_off_ms:.4f} ms; fg gpu p50 {m.gpu_on_ms:.4f} vs {m.gpu_off_ms:.4f} ms",
         f"- acceptance at smoke grade: **{'PASS' if chk['pass'] else 'FAIL'}** (fg-alone latency and R_2 wait)", ""]
    out = ROOT / "data" / "w2_G_prechecks.md"
    out.write_text("\n".join(L), encoding="utf-8"); print("\n".join(L)); print("written:", out)


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(ROOT / "analysis"))
    main()
