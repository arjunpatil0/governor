"""POST-HOC (exploratory, not registered) report for Experiment G: reviews/2026-10-22_G_results_review.md findings 1(a-d) and 2.
Reads the local rec files of the complete run (witness blocks, recorded-interval fg launches) and writes data/w2_G_posthoc.md. Registered verdicts in
data/w2_G_results.md are NOT changed by anything here. Functions: analysis/w2_g_posthoc.py (tested on synthetic timelines)."""
import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "analysis"))
import w2_g_analysis as ga  # noqa: E402
from w2_analysis import _tte_points  # noqa: E402
from w2_g_posthoc import boundary_distances, fine_tau_fit, overlap_pairs, same_sm_cases, switch_stagger, uniform_boundary_fraction  # noqa: E402
from w2_g_timeline import launch_table, recorded_interval  # noqa: E402

CELLS = ("g_T1", "g_T4", "g_T4_3bpsm")
S_MS, Q_MS = 0.148, 0.374            # registered-analysis medians (data/w2_G_results.md), used as the comparison scales
EDGE_US = 30.0


def _tab(df, nd=3):
    return "```\n" + df.round(nd).to_string(index=False) + "\n```"


def _q(x, qs=(10, 50, 90, 99)):
    x = np.asarray(x, float)
    return {f"p{q}": float(np.percentile(x, q)) if len(x) else np.nan for q in qs} | {"max": float(x.max()) if len(x) else np.nan}


def analyse_cell(run_dir, df, cell, n_ref=1500):
    """Pool one cell over all blocks. Returns dict of arrays/frames."""
    ov_us, dist_us, ref, stag, cases, edge = [], [], [], [], [], []
    n_pairs = n_same = n_fg_launch = 0
    for _, r in df[df.cell_id == cell].iterrows():
        cd = ga.cell_dir(run_dir, r)
        fg, _, _ = ga.load_rec(cd / "fg_rec.npz"); bg, _, _ = ga.load_rec(cd / "bg_rec.npz")
        if not len(fg["t0"]) or not len(bg["t0"]):
            continue
        tags = recorded_interval(bg, fg)["fg_tags"]; n_fg_launch += len(tags)
        p = overlap_pairs(fg, bg, tags)
        n_pairs += len(p["ov_ns"]); ov_us += list(p["ov_ns"] * 1e-3)
        same = p["fg_sm"] == p["bg_sm"]; n_same += int(same.sum())
        if len(p["ov_ns"]):
            dist_us += list(boundary_distances(p, fg, bg) * 1e-3)
        if same.any():
            pos = np.vstack([(p["ov_start"] - p["fg_s"]), (p["fg_e"] - p["ov_end"]), (p["ov_start"] - p["bg_s"]), (p["bg_e"] - p["ov_end"])]) * 1e-3
            edge += list(pos[:, same].min(axis=0) < EDGE_US)
            c = same_sm_cases(p, fg, bg, n=4, seed=int(r.block)); c.insert(0, "block", int(r.block)); cases.append(c)
        ref.append(uniform_boundary_fraction(fg, bg, tags, within_ns=S_MS * 1e6, n=n_ref // 10, seed=int(r.block)))
        t = switch_stagger(fg, bg, tags)
        if len(t):
            t.insert(0, "block", int(r.block)); stag.append(t)
    return dict(ov_us=np.array(ov_us), dist_us=np.array(dist_us), ref_frac=float(np.mean(ref)) if ref else np.nan, n_pairs=n_pairs, n_same=n_same,
                stagger=pd.concat(stag) if stag else pd.DataFrame(), cases=pd.concat(cases) if cases else pd.DataFrame(), edge=np.array(edge, bool), n_fg=n_fg_launch)


def tau_refit(run_dir, df):
    base = df[df.cell_id == "g_baseline_off"].set_index("block").lat_mean_ms
    R, W, B = [], [], []
    for m in (0.5, 1, 2, 8):
        for _, r in df[df.cell_id == f"g_R{m}_off"].iterrows():
            if int(r.block) not in base.index:
                continue
            cd = ga.cell_dir(run_dir, r)
            if (cd / "bg_window.npz").exists():
                rr, ww = _tte_points(cd, float(base[int(r.block)]), False)
                R.append(rr); W.append(ww); B.append(np.full(len(rr), int(r.block)))
    return fine_tau_fit(np.concatenate(R), np.concatenate(W), np.concatenate(B), n_boot=1000, seed=0), len(np.concatenate(R))


def build(run_dir):
    run_dir = Path(run_dir); ga.BLOCK_SET["witness"] = True
    df = pd.read_csv(run_dir / "results.csv")
    L = ["# Experiment G: POST-HOC mechanism analysis (exploratory; NOT registered)", "",
         f"Source `{run_dir}` (witness blocks, recorded-interval fg launches). Review: reviews/2026-10-22_G_results_review.md findings 1(a-d) and 2. "
         "Registered verdicts in data/w2_G_results.md are unchanged (P6 DID NOT HOLD; the 3-bpsm control overlaps, so the registered rule reports it as a finding). "
         "Everything below was chosen AFTER seeing the registered results and is labelled post-hoc.",
         f"Comparison scales from the registered analysis: s = {S_MS} ms (median gap between runs of different contexts), q = {Q_MS} ms (median complete run).", ""]
    res = {c: analyse_cell(run_dir, df, c) for c in CELLS}
    L += ["## 1a. Overlap duration (every fg/bg on-interval pair intersecting by more than 10 us)", ""]
    rows = []
    for c, d in res.items():
        rows.append(dict(cell=c, fg_launches=d["n_fg"], pairs=d["n_pairs"], same_sm=d["n_same"], **{k + "_us": v for k, v in _q(d["ov_us"]).items()}))
    L += [_tab(pd.DataFrame(rows), 1), "", f"- scale: s = {S_MS * 1e3:.0f} us, q = {Q_MS * 1e3:.0f} us", ""]
    L += ["## 1b. Position of overlaps relative to the nearest run boundary (fg or bg merged-run start/end)", ""]
    rows = []
    for c, d in res.items():
        x = d["dist_us"]
        rows.append(dict(cell=c, n=len(x), **{k + "_us": v for k, v in _q(x).items()}, frac_within_s=float((x <= S_MS * 1e3).mean()) if len(x) else np.nan,
                         uniform_ref_within_s=d["ref_frac"]))
    L += [_tab(pd.DataFrame(rows), 3), "",
          "- `frac_within_s`: share of overlaps whose midpoint lies within s of a boundary; `uniform_ref_within_s`: the same share for points placed uniformly inside the fg launch spans. "
          "Overlaps concentrated at boundaries give frac_within_s well above the reference; overlaps spread through runs give about the reference.", ""]
    L += ["## 1c. Per-switch stagger across SMs (switches seen on >= 30 of 36 SMs)", ""]
    rows = []
    for c, d in res.items():
        s = d["stagger"]
        for direction in ("fg->bg", "bg->fg"):
            x = s[s.direction == direction] if len(s) else s
            if not len(x):
                continue
            rows.append(dict(cell=c, direction=direction, switches=len(x), out_end_spread_us_p50=x.out_end_spread_ns.median() * 1e-3, out_end_spread_us_p90=x.out_end_spread_ns.quantile(.9) * 1e-3,
                             in_start_spread_us_p50=x.in_start_spread_ns.median() * 1e-3, in_start_spread_us_p90=x.in_start_spread_ns.quantile(.9) * 1e-3,
                             cluster_overlap_us_p50=x.cluster_overlap_ns.median() * 1e-3, cluster_overlap_us_p90=x.cluster_overlap_ns.quantile(.9) * 1e-3,
                             per_sm_gap_us_p50=x.per_sm_gap_median_ns.median() * 1e-3, per_sm_gap_min_us_p1=x.per_sm_gap_min_ns.quantile(.01) * 1e-3,
                             sm_with_same_sm_overlap=int(x.n_sm_same_sm_overlap.sum()), sm_switches=int(x.n_sm.sum())))
    L += [_tab(pd.DataFrame(rows), 1), "",
          "- `cluster_overlap` = latest outgoing end minus earliest incoming start over the 36 SMs (positive = some SM starts the incoming context before another SM has finished the outgoing one). "
          "`per_sm_gap` = incoming start minus outgoing end on the SAME SM (negative = same-SM overlap). A staggered switch has cluster_overlap > 0 with per-SM gaps >= 0.", ""]
    L += ["## 1d. Same-SM overlaps (two contexts' blocks on one SM at once): edge test and hand-inspection sample", ""]
    rows = []
    for c, d in res.items():
        rows.append(dict(cell=c, same_sm_pairs=d["n_same"], edge_within_30us=int(d["edge"].sum()) if len(d["edge"]) else 0,
                         edge_share=float(d["edge"].mean()) if len(d["edge"]) else np.nan))
    L += [_tab(pd.DataFrame(rows), 3), "", "- edge = the intersection starts or ends within 30 us of the start/end of either block's on-interval (a block-boundary artefact would sit there).", ""]
    for c in ("g_T4_3bpsm", "g_T4"):
        cs = res[c]["cases"]
        if len(cs):
            keep = cs.sort_values(["block"]).head(20)
            L += [f"### {c}: {len(keep)} randomly sampled same-SM overlaps (4 per block, seeded by block)", "", _tab(keep, 1), ""]
    fit, n = tau_refit(run_dir, df)
    L += ["## 2. tau refit on a fine grid (sensitivity; the registered fit and verdict are unchanged)", "",
          f"- registered fit: tau = 0.260 ms on a 0.01 ms grid, bootstrap CI [0.260, 0.260] (degenerate)",
          f"- fine grid ({fit['grid_step'] * 1e3:.1f} us step), same model, n = {n} requests, 1000 block-cluster bootstrap resamples: tau = {fit['tau']:.4f} ms, 90% CI [{fit['tau_lo']:.4f}, {fit['tau_hi']:.4f}], offset {fit['offset']:.4f} ms", ""]
    return L


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--dir"); a = ap.parse_args()
    d = Path(a.dir) if a.dir else sorted((ROOT / "data" / "raw" / "w2_G").glob("*/results.csv"))[-1].parent
    L = build(d)
    out = ROOT / "data" / "w2_G_posthoc.md"; out.write_text("\n".join(L), encoding="utf-8"); print("\n".join(L)); print("written:", out)


if __name__ == "__main__":
    main()
