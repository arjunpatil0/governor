#!/usr/bin/env python3
"""Experiment G report: pre-checks (ii-b, iii), P1-P3 (uninstrumented cells), P4-P8 (timeline), per addenda
experiments/w2_colocation_addendum_globaltimer_2026-10-22.md and ..._prerun_2026-10-22.md. Every prediction is reported "held / did not hold"
with the numbers. The pure parts are tested in tests/test_w2_g_timeline.py; this driver only reads a run directory.
Usage: python analysis/w2_g_analysis.py [--dir data/raw/w2_G/<stamp>]   (default: newest; --smoke-dir for a smoke directory)
Writes data/w2_G_results.md (or data/w2_G_smoke_report.md for a smoke directory: not a result)."""
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
import sys  # noqa: E402
sys.path.insert(0, str(ROOT / "analysis")); sys.path.insert(0, str(ROOT / "workloads" / "common"))
from w2_analysis import _tte_points, bin_by_time_to_end, fit_capped_wait  # noqa: E402
from w2_g_timeline import (count_overlaps, launch_table, offset_at, p3_ripple, preempted_fraction, q_and_s, recorded_interval,  # noqa: E402
                           restrict_rec, sliced_mask, witness_mask, concurrency_verdict)
from w2_timeline import g_thr_ns, overhead_check, unpack_rec  # noqa: E402

A_WAIT = {0.5: 0.226, 1: 0.255, 2: 0.287, 8: 0.298}      # A's cell-median observed waits (ms), as quoted in the G addendum P1
P1_TOL_MS = 0.03
P2_RANGE = (0.22, 0.31)
P4_RANGE = (0.5, 0.9)
P5_RANGE = (0.2, 0.3)
P7_MIN = 0.01
P8_MAX_MS = 0.4
SLICE_EXTRA_MS = 2 * 0.243
WITNESS_BLOCKS = 108        # blockIdx < 108 = the first three blocks per SM (addendum 3): gap-free when the kernel runs alone; blocks beyond them show intra-SM arbitration gaps
BLOCK_SET = {"witness": True}
SKIPPED = []
FENCE, FENCE_END = "```" + chr(10), chr(10) + "```"
FG_SIZE = {"g_baseline": 0.1, "g_T1": 1, "g_T4": 4, "g_T1_alone": 1, "g_T4_alone": 4}


def _tab(df, nd=4):
    return FENCE + df.round(nd).to_string(index=False) + FENCE_END if len(df) else "(none)"


def load_rec(path):
    z = np.load(path)
    keys = [k for k in z.files if k not in ("sync0", "sync1", "sms")]
    rec = unpack_rec({k: z[k] for k in keys})
    if BLOCK_SET["witness"]:
        mask, stats = witness_mask(rec, nominal_blocks=WITNESS_BLOCKS)
        rec = restrict_rec(rec, mask); rec["witness_stats"] = stats
    return rec, tuple(z["sync0"]), tuple(z["sync1"])


def _fg_size(cell_id):
    if cell_id in FG_SIZE:
        return FG_SIZE[cell_id]
    return 0.1 if cell_id.startswith("g_R") or cell_id.startswith("g_baseline") else None


def cell_dir(run_dir, r):
    return run_dir / "cells" / f"b{int(r.block):02d}_{int(r.cell_idx):02d}_{r.cell_id}"


def alone_spans(run_dir, df):
    """(block, fg size) -> median on-GPU span (ns) of that block's instrumented fg-alone cell (baseline 0.1 ms; T1_alone; T4_alone)."""
    out = {}
    for _, r in df.iterrows():
        if r.cell_id in ("g_baseline", "g_T1_alone", "g_T4_alone"):
            cd = cell_dir(run_dir, r)
            if (cd / "fg_rec.npz").exists():
                rec, _, _ = load_rec(cd / "fg_rec.npz"); ft = launch_table(rec)
                out[(int(r.block), _fg_size(r.cell_id))] = float(np.median(ft["span_end"] - ft["span_start"]))
    return out


def _ws(rec):
    return rec.get("witness_stats", dict(nominal=0, fallback=0, excluded=0))


def _bpsm(cell_id):
    return 3 if cell_id.endswith("_3bpsm") else 6


def g_thr_by_block(run_dir, df):
    """(block, blocks per SM) -> G_thr from that block's bgalone cell of the same grid (witness blocks)."""
    out = {}
    for _, r in df[df.cell_id.isin(["g_bgalone", "g_bgalone_3bpsm"])].iterrows():
        cd = cell_dir(run_dir, r)
        if (cd / "bg_rec.npz").exists():
            rec, _, _ = load_rec(cd / "bg_rec.npz"); out[(int(r.block), _bpsm(r.cell_id))] = g_thr_ns(rec)
    return out


def timeline_cells(run_dir, df):
    """P4-P8 per (block, instrumented cell with both contexts). Returns (rows, raw) where raw has pooled q/s lists and P8 delays per cell id."""
    alone = alone_spans(run_dir, df); thr = g_thr_by_block(run_dir, df)
    rows, raw = [], {}
    for _, r in df.iterrows():
        cd = cell_dir(run_dir, r)
        if not ((cd / "fg_rec.npz").exists() and (cd / "bg_rec.npz").exists()):
            continue
        b = int(r.block); size = _fg_size(r.cell_id)
        fg, fs0, fs1 = load_rec(cd / "fg_rec.npz"); bg, bs0, bs1 = load_rec(cd / "bg_rec.npz")
        fgw = np.load(cd / "fg_window.npz")
        if not len(fg["t0"]) or not len(bg["t0"]):                    # every launch excluded by the witness rule: nothing to analyse
            SKIPPED.append(f"b{b:02d} {r.cell_id}"); continue
        ft, bt = launch_table(fg), launch_table(bg)
        iv = recorded_interval(bg, fg)
        inside = np.isin(ft["tags"], iv["fg_tags"])
        spans = (ft["span_end"] - ft["span_start"])[inside]
        a_span = alone.get((b, size), np.nan)
        sl = sliced_mask(spans, a_span, SLICE_EXTRA_MS) if np.isfinite(a_span) else np.zeros(len(spans), bool)
        sliced_tags = ft["tags"][inside][sl]
        qs = q_and_s(ft, bt, sliced_tags)
        ov = count_overlaps(fg, bg, fg_tags=iv["fg_tags"])
        g_thr = thr.get((b, _bpsm(r.cell_id)), np.nan)
        pf = preempted_fraction(bg, fg, g_thr) if np.isfinite(g_thr) else dict(fraction=np.nan, fraction_with_fg=np.nan, n_blocks=len(bg["t0"]))
        # P8: arrival -> on-GPU start of the fg kernel (QPC), offset interpolated between the two syncs
        k = ft["tags"].astype(int) - int(fgw["idx0"]); ok = (k >= 0) & (k < len(fgw["arrival"]))
        arr = fgw["arrival"][k[ok]]
        off = np.array([offset_at(t, fs0, fs1) for t in arr])
        delay_ms = (ft["span_start"][ok] * 1e-9 - off - arr) * 1e3
        rows.append(dict(block=b, cell=r.cell_id, n_fg_in_interval=int(inside.sum()), n_bg_launches=iv["n_bg_launches"],
                         interval_s=(iv["end_ns"] - iv["start_ns"]) * 1e-9, fg_share=int(inside.sum()) / max(len(fgw["arrival"]), 1),
                         bg_launches_dropped=int(r.get("rec_dropped_bg", 0) or 0), alone_span_ms=a_span * 1e-6, n_sliced=qs["n_sliced"],
                         q_pooled_ms=qs["q_pooled_ms"], q_fg_ms=qs["q_fg_ms"], q_bg_ms=qs["q_bg_ms"], s_ms=qs["s_ms"], n_neg_s=qs["n_neg_s"],
                         n_overlap=ov["n_overlap"], n_overlap_same_sm=ov["n_overlap_same_sm"], n_overlap_diff_sm=ov["n_overlap_diff_sm"], n_ties=ov["n_ties"],
                         n_fg_blocks=ov["n_fg_blocks"], n_untrusted_fg=ov["n_untrusted_fg"], n_untrusted_bg=int(bt["untrusted"].sum()),
                         g_thr_us=g_thr * 1e-3, preempt_frac=pf["fraction"], preempt_frac_with_fg=pf["fraction_with_fg"],
                         p8_delay_p99_ms=float(np.percentile(delay_ms, 99)) if len(delay_ms) else np.nan,
                         gap_lost=int(fg["gap_lost"]) + int(bg["gap_lost"]),
                         fg_w_nominal=_ws(fg)["nominal"], fg_w_fallback=_ws(fg)["fallback"], fg_w_excluded=_ws(fg)["excluded"],
                         bg_w_nominal=_ws(bg)["nominal"], bg_w_fallback=_ws(bg)["fallback"], bg_w_excluded=_ws(bg)["excluded"]))
        d = raw.setdefault(r.cell_id, dict(q=[], s=[], qf=[], qb=[], delay=[]))
        d["q"] += list(qs["q_fg_raw_ms"]) + list(qs["q_bg_raw_ms"]); d["qf"] += list(qs["q_fg_raw_ms"]); d["qb"] += list(qs["q_bg_raw_ms"])
        d["s"] += list(qs["s_raw_ms"]); d["delay"] += list(delay_ms)
    return pd.DataFrame(rows), raw


def bgalone_rates(run_dir, df):
    """Gaps in the bgalone cell (no fg): other GPU contexts (finding 6). Per block: bg blocks with a gap >= G_thr, gap count, gap length summary."""
    rows = []
    for _, r in df[df.cell_id.isin(["g_bgalone", "g_bgalone_3bpsm"])].iterrows():
        cd = cell_dir(run_dir, r)
        if not (cd / "bg_rec.npz").exists():
            continue
        rec, _, _ = load_rec(cd / "bg_rec.npz"); thr = g_thr_ns(rec)
        gl = rec["gaps"]["len"].astype(float); gi = rec["gaps"]["rec_idx"]
        big = gl >= thr
        rows.append(dict(block=int(r.block), cell=r.cell_id, g_thr_us=thr * 1e-3, bg_blocks=len(rec["t0"]), blocks_with_gap_ge_gthr=len(np.unique(gi[big])),
                         fraction=len(np.unique(gi[big])) / max(len(rec["t0"]), 1), gaps_logged=len(gl), gaps_ge_gthr=int(big.sum()),
                         gap_len_median_us=float(np.median(gl[big])) * 1e-3 if big.any() else np.nan, gap_len_max_us=float(gl.max()) * 1e-3 if len(gl) else np.nan,
                         novf_blocks=int((rec["novf"] > 0).sum())))
    return pd.DataFrame(rows)


def precheck_iii(df):
    """Registered acceptance (addenda 1 and 2): per block, fg-alone median latency g_baseline vs g_baseline_off within 5%, and the observed wait of
    the m=2 cell, instrumented (g_R2 - g_baseline) vs uninstrumented (g_R2_off - g_baseline_off), within 0.03 ms; medians over blocks decide."""
    d = df.set_index(["block", "cell_id"])
    rows = []
    for b in sorted(df.block.unique()):
        try:
            g = lambda c, col: float(d.loc[(b, c), col])
            rows.append(dict(block=b, base_on_p50=g("g_baseline", "lat_p50_ms"), base_off_p50=g("g_baseline_off", "lat_p50_ms"),
                             wait_on=g("g_R2", "lat_mean_ms") - g("g_baseline", "lat_mean_ms"), wait_off=g("g_R2_off", "lat_mean_ms") - g("g_baseline_off", "lat_mean_ms"),
                             slice_on_ms=g("g_R2", "bg_mean_slice_ms"), slice_off_ms=g("g_R2_off", "bg_mean_slice_ms"),
                             gpu_on_ms=g("g_baseline", "fg_gpu_p50_ms"), gpu_off_ms=g("g_baseline_off", "fg_gpu_p50_ms")))
        except KeyError:
            continue
    t = pd.DataFrame(rows)
    if not len(t):
        return t, None
    m = t.median(numeric_only=True)
    return t, overhead_check(m.base_on_p50, m.base_off_p50, m.wait_on, m.wait_off)


def p1_p3(run_dir, df):
    """P1-P3 on the UNINSTRUMENTED R_m_off cells (block baseline = g_baseline_off)."""
    base = df[df.cell_id == "g_baseline_off"].set_index("block").lat_mean_ms
    rows, pts_obs, pts_unst = [], [], []
    for m in (0.5, 1, 2, 8):
        sub = df[df.cell_id == f"g_R{m}_off"]
        w = []
        for _, r in sub.iterrows():
            if int(r.block) not in base.index:
                continue
            w.append(float(r.lat_mean_ms - base[int(r.block)]))
            cd = cell_dir(run_dir, r)
            if (cd / "bg_window.npz").exists():
                for store, flag in ((pts_obs, False), (pts_unst, True)):
                    rr, ww = _tte_points(cd, float(base[int(r.block)]), flag)
                    store.append((m, rr, ww, int(r.block)))
        if w:
            rows.append(dict(m_ms=m, n_blocks=len(w), obs_wait_ms=float(np.median(w)), a_wait_ms=A_WAIT[m], diff_ms=float(np.median(w)) - A_WAIT[m],
                             within_tol=abs(float(np.median(w)) - A_WAIT[m]) <= P1_TOL_MS))
    p1 = pd.DataFrame(rows)
    out = dict(p1=p1, p1_held=bool(len(p1) == 4 and p1.within_tol.all()))
    if pts_obs:
        R = np.concatenate([g[1] for g in pts_obs]); W = np.concatenate([g[2] for g in pts_obs]); B = np.concatenate([[g[3]] * len(g[1]) for g in pts_obs])
        out["p2"] = fit_capped_wait(R, W, B); out["p2_n"] = len(R)
        out["p2_held"] = bool(P2_RANGE[0] <= out["p2"]["tau"] <= P2_RANGE[1])
    if pts_unst:
        R = np.concatenate([g[1] for g in pts_unst]); W = np.concatenate([g[2] for g in pts_unst])
        out["binned"] = bin_by_time_to_end(R, W); out["p3"] = p3_ripple(out["binned"])
    return out


def _verdict(held):
    return "HELD" if held else "DID NOT HOLD"


def build_report(run_dir, witness=True, skip_blocks=()):
    BLOCK_SET["witness"] = witness
    run_dir = Path(run_dir)
    meta = json.loads((run_dir / "meta.json").read_text(encoding="utf-8")); df = pd.read_csv(run_dir / "results.csv")
    if skip_blocks:
        df = df[~df.block.isin(list(skip_blocks))].reset_index(drop=True)
    smoke = bool(meta.get("smoke"))
    L = [f"# Experiment G report{' (SMOKE: not a result)' if smoke else ''}", "",
         f"Source `{run_dir}` | admin {meta['admin']} | AC {meta['ac_plugged']} | ambient {meta['ambient_c']} C | Armoury {meta.get('armoury_mode')} | {meta['gpu']} driver {meta['driver']} | "
         f"yaml {meta['yaml_sha']} | dll {meta['dll_sha']} | git {meta['git_head'][:8]} | blocks {meta['blocks']} | cells {len(df)}" + (f" | Excluded blocks: {list(skip_blocks)}" if skip_blocks else ""),
         "Addenda: experiments/w2_colocation_addendum_globaltimer_2026-10-22.md and ..._prerun_2026-10-22.md (and _witness_ if registered). Each prediction: held / did not hold, with the numbers.",
         f"Block set for gap, run, overlap and preemption analyses: {'WITNESS blocks only (blockIdx < %d, the first three blocks per SM)' % WITNESS_BLOCKS if witness else 'ALL blocks (secondary view; blocks beyond three per SM show intra-SM arbitration gaps even with no other context)'}.", ""]
    t3, chk = precheck_iii(df)
    L += ["## Pre-check (iii): instrumentation overhead (registered acceptance; if it fails the timeline is NOT interpreted)", "", _tab(t3)]
    gate = True
    if chk is None:
        L += ["", "- not evaluable: g_baseline / g_baseline_off / g_R2 / g_R2_off cells missing"]; gate = False
    else:
        m = t3.median(numeric_only=True)
        gate = bool(chk["pass"])
        L += ["", f"- median fg-alone latency, instrumented vs not: relative difference {chk['lat_rel_diff']*100:.1f}% (limit 5%)",
              f"- observed wait of R_2, instrumented {m.wait_on:.4f} ms vs uninstrumented {m.wait_off:.4f} ms: difference {chk['wait_abs_diff_ms']:.4f} ms (limit 0.03)",
              f"- bg mean slice {m.slice_on_ms:.4f} vs {m.slice_off_ms:.4f} ms; fg gpu p50 {m.gpu_on_ms:.4f} vs {m.gpu_off_ms:.4f} ms",
              f"- **pre-check (iii): {'PASS' if gate else 'FAIL: do not interpret the timeline (P4-P8); report the failure'}**"]
    # ---- P1-P3
    r13 = p1_p3(run_dir, df)
    L += ["", "## P1-P3 on the uninstrumented R_m_off cells (fresh seeds; the block baseline is g_baseline_off)", ""]
    L += ["### P1: cell-median observed wait within +/-0.03 ms of A", "", _tab(r13["p1"], 4), "", f"- P1 {_verdict(r13['p1_held'])}"]
    if "p2" in r13:
        p2 = r13["p2"]
        L += ["", f"### P2: capped-wait fit on the observed slice-end axis (n = {r13['p2_n']} requests, all four m pooled)", "",
              f"- tau = {p2['tau']:.3f} ms, 90% block-bootstrap CI [{p2['tau_lo']:.3f}, {p2['tau_hi']:.3f}], offset {p2['offset']:.3f} ms; registered range {P2_RANGE[0]}-{P2_RANGE[1]} ms (A: 0.260)", f"- P2 {_verdict(r13['p2_held'])}"]
    if "p3" in r13:
        p3 = r13["p3"]
        L += ["", "### P3: ripple on the unstretched axis (binned means, A's bins)", "", _tab(r13["binned"], 4), "",
              f"- local minimum 0.35-0.40: {p3['min1_ok']} (drop {p3['drop1_ms']:.3f} ms below the preceding maximum); local minimum 0.80-0.85: {p3['min2_ok']} (drop {p3['drop2_ms']:.3f} ms); required drop >= 0.04 ms (A: 0.300->0.214, 0.364->0.232)",
              f"- P3 {_verdict(p3['held'])}"]
    # ---- timeline
    SKIPPED.clear()
    tl_all, raw_all = timeline_cells(run_dir, df)
    ba = bgalone_rates(run_dir, df)
    # validity gate (addendum 3 section A): (i) bgalone witness preempted fraction < 1% (pooled, per grid); (ii) placement is reported per cell
    gate_w, gate_lines = True, []
    if witness:
        for cid, g in ba.groupby("cell"):
            frac = g.blocks_with_gap_ge_gthr.sum() / max(g.bg_blocks.sum(), 1)
            ok = bool(frac < 0.01); gate_w = gate_w and ok
            gate_lines.append(f"- {cid}: witness preempted fraction {frac*100:.3f}% over {int(g.bg_blocks.sum())} blocks -> {'PASS' if ok else 'FAIL'} (limit 1%)")
        if ba.empty:
            gate_w = False; gate_lines.append("- no bgalone cell: gate (i) cannot be evaluated -> FAIL")
    gate = gate and gate_w
    L += ["", "## Witness validity gate (addendum 3 section A)", ""] + (gate_lines or ["- all-blocks view: the witness gate does not apply (secondary view, arbitration artefact present)"]) +          [f"- gate (i): {'PASS' if gate_w else 'FAIL: P6, P7, q and s are reported but NOT interpreted'}; gate (ii) placement is reported per cell below (nominal / fallback / excluded launches)"]
    ctl = tl_all[tl_all.cell.str.endswith("_3bpsm")] if len(tl_all) else tl_all
    tl = tl_all[~tl_all.cell.str.endswith("_3bpsm")] if len(tl_all) else tl_all
    raw = {k: v for k, v in raw_all.items() if not k.endswith("_3bpsm")}
    L += ["", "## Timeline cells: coverage, trust and results per block (recorded-interval rule, addendum 2 section C)", ""]
    if not len(tl):
        L += ["(no cell had both fg and bg records)"]
    else:
        cov = tl[["block", "cell", "n_fg_in_interval", "n_bg_launches", "interval_s", "fg_share", "bg_launches_dropped", "n_untrusted_fg", "n_untrusted_bg", "gap_lost",
                  "fg_w_nominal", "fg_w_fallback", "fg_w_excluded", "bg_w_nominal", "bg_w_fallback", "bg_w_excluded"]]
        L += ["Coverage and trust (fg_share = share of the cell's measured fg requests wholly inside the recorded interval; untrusted = blocks with gap-log overflow; gap_lost = gaps lost to a full global list):", "", _tab(cov, 3), ""]
        L += ["Per block results:", "", _tab(tl.drop(columns=["n_fg_in_interval", "n_bg_launches", "interval_s", "fg_share", "bg_launches_dropped", "n_untrusted_fg", "n_untrusted_bg", "gap_lost",
                                                                  "fg_w_nominal", "fg_w_fallback", "fg_w_excluded", "bg_w_nominal", "bg_w_fallback", "bg_w_excluded"]), 4), ""]
        verdict_note = "" if gate else " (a validity gate FAILED: shown for completeness, NOT interpreted)"
        # P4/P5: pooled over the cells with sliced spans
        allq = np.array([x for c in raw.values() for x in c["q"]]); alls = np.array([x for c in raw.values() for x in c["s"]])
        L += [f"### P4 quantum q (pooled complete runs of both contexts inside sliced fg spans){verdict_note}", ""]
        per = pd.DataFrame([dict(cell=k, n_runs=len(v["q"]), q_pooled_ms=np.median(v["q"]) if v["q"] else np.nan, q_fg_ms=np.median(v["qf"]) if v["qf"] else np.nan,
                                 q_bg_ms=np.median(v["qb"]) if v["qb"] else np.nan, n_s=len(v["s"]), s_ms=np.median(v["s"]) if v["s"] else np.nan) for k, v in sorted(raw.items())])
        L += [_tab(per, 4), ""]
        if len(allq):
            q = float(np.median(allq)); L += [f"- pooled over all cells: q = {q:.3f} ms from {len(allq)} complete runs; registered range {P4_RANGE[0]}-{P4_RANGE[1]} ms; P4 {_verdict(P4_RANGE[0] <= q <= P4_RANGE[1])}"]
        else:
            L += ["- no sliced fg span with complete runs: P4 cannot be evaluated (reported as such, not as held)"]
        L += ["", f"### P5 switch gap s{verdict_note}", ""]
        if len(alls):
            s = float(np.median(alls)); L += [f"- pooled s = {s:.3f} ms from {len(alls)} transitions; registered range {P5_RANGE[0]}-{P5_RANGE[1]} ms; P5 {_verdict(P5_RANGE[0] <= s <= P5_RANGE[1])}; negative-s transitions (runs overlapping in time): {int(tl.n_neg_s.sum())}"]
        else:
            L += ["- no transitions: P5 cannot be evaluated"]
        agg = tl.groupby("cell")[["n_overlap", "n_overlap_same_sm", "n_overlap_diff_sm", "n_ties", "n_fg_blocks", "n_untrusted_fg"]].sum().reset_index()
        L += ["", f"### P6 no concurrency{verdict_note}", "", _tab(agg, 0), "",
              f"- fg blocks overlapping a bg block by more than 10 us: {int(agg.n_overlap.sum())} of {int(agg.n_fg_blocks.sum())} trusted blocks (untrusted excluded: {int(agg.n_untrusted_fg.sum())}); ties (<= 10 us): {int(agg.n_ties.sum())}; P6 {_verdict(int(agg.n_overlap.sum()) == 0)}"]
        c_ov = int(ctl.n_overlap.sum()) if len(ctl) else None
        cv = concurrency_verdict(int(agg.n_overlap.sum()), c_ov)
        L += ["", "#### Concurrency rule (addendum 3 section B): the 3-blocks-per-SM control g_T4_3bpsm", ""]
        if len(ctl):
            c = ctl[["block", "n_overlap", "n_overlap_same_sm", "n_overlap_diff_sm", "n_ties", "n_fg_blocks", "n_untrusted_fg", "preempt_frac", "interval_s"]]
            L += [_tab(c, 3), ""]
        L += [{"p6_held": "- P6 held in the main cells; the control is shown for completeness.",
               "concurrency_finding": f"- P6 failed in the main cells AND the control overlaps ({c_ov} fg blocks; same-SM {int(ctl.n_overlap_same_sm.sum())}, different-SM {int(ctl.n_overlap_diff_sm.sum())}): concurrency is REPORTED AS A FINDING{verdict_note}.",
               "unexplained": "- P6 failed in the main cells but the arbitration-free control shows NO overlap: the main-cell overlaps are UNEXPLAINED and are NOT reported as concurrency.",
               "control_missing": "- P6 failed in the main cells and the control cell is missing: concurrency cannot be reported as a finding."}[cv["state"]]]
        pf = tl.groupby("cell")[["preempt_frac", "preempt_frac_with_fg"]].mean().reset_index()
        L += ["", f"### P7 mid-kernel preemption of bg blocks (block has a gap >= G_thr; mean over blocks){verdict_note}", "", _tab(pf, 4)]
        t4 = pf[pf.cell == "g_T4"]
        if len(t4):
            f4 = float(t4.preempt_frac.iloc[0]); L += ["", f"- g_T4: {f4*100:.2f}% of recorded bg blocks preempted (registered: >= 1%); P7 {_verdict(f4 >= P7_MIN)}"]
        else:
            L += ["", "- g_T4 missing: P7 cannot be evaluated"]
        p8 = {k: float(np.percentile(v["delay"], 99)) for k, v in raw.items() if k.startswith("g_R") and v["delay"]}
        p8q = {k: [float(np.percentile(v["delay"], q)) for q in (50, 90)] for k, v in raw.items() if k.startswith("g_R") and v["delay"]}
        L += ["", f"### P8 arrival -> on-GPU start delay of the 0.1 ms fg (ms; the registered test is the p99; p50 and p90 added for context, review 2026-10-22 finding 5){verdict_note}", "",
              _tab(pd.DataFrame(dict(cell=list(p8), p50_ms=[p8q[k][0] for k in p8], p90_ms=[p8q[k][1] for k in p8], p99_ms=list(p8.values()))), 4)]
        if p8:
            L += ["", f"- registered: p99 <= {P8_MAX_MS} ms for every m; P8 {_verdict(all(v <= P8_MAX_MS for v in p8.values()))}"]
    if SKIPPED:
        L += ["", f"## Cells skipped because the witness rule excluded every launch: {', '.join(SKIPPED)}"]
    L += ["", "## g_bgalone: gaps with no foreground (other GPU contexts, reported baseline preemption rate; not a prediction)", "", _tab(ba, 4), ""]
    return L, smoke


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--dir"); ap.add_argument("--all-blocks", action="store_true", help="secondary view: do not restrict to the witness blocks")
    ap.add_argument("--skip-blocks", type=int, nargs="*", default=[], help="drop these experiment blocks (sensitivity analysis)"); a = ap.parse_args()
    if a.dir:
        d = Path(a.dir)
    else:
        runs = sorted((ROOT / "data" / "raw" / "w2_G").glob("*/results.csv"))
        if not runs:
            sys.exit("no full-run results under data/raw/w2_G (pass --dir for a smoke directory)")
        d = runs[-1].parent
    L, smoke = build_report(d, witness=not a.all_blocks, skip_blocks=tuple(a.skip_blocks))
    out = ROOT / "data" / (("w2_G_smoke_report" if smoke else "w2_G_results") + ("_allblocks" if a.all_blocks else "") + ("_skip_b" + "".join(map(str, a.skip_blocks)) if a.skip_blocks else "") + ".md")
    out.write_text("\n".join(L), encoding="utf-8"); print("\n".join(L)); print("written:", out)


if __name__ == "__main__":
    main()
