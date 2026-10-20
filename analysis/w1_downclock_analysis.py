#!/usr/bin/env python3
"""Analysis for the pre-registered W1 downclock experiment (experiments/w1_downclock.yaml).

Usage: python analysis\\w1_downclock_analysis.py [path\\to\\results.csv]   (default: newest non-smoke run)
Implements exactly the registered tests: paired one-sided Wilcoxon signed-rank across blocks,
Holm correction over the 5 locked levels (separately for H1 and H2), median ratios with IQR,
matched-pairs rank-biserial correlation. Writes data/w1_downclock_results.md.
"""
import json, subprocess, sys
from pathlib import Path

import numpy as np
import pandas as pd
import yaml
from scipy.stats import wilcoxon

ROOT = Path(__file__).resolve().parents[1]
CFG = yaml.safe_load((ROOT / "experiments" / "w1_downclock.yaml").read_text(encoding="utf-8"))
ALPHA = CFG["analysis"]["alpha"]


def newest_results():
    runs = sorted((ROOT / "data" / "raw" / "w1_downclock").glob("*/results.csv"))
    if not runs:
        sys.exit("no full-run results.csv found under data/raw/w1_downclock")
    return runs[-1]


def holm(pvals):
    order = np.argsort(pvals); m = len(pvals); adj = np.empty(m); run = 0.0
    for rank, i in enumerate(order):
        run = max(run, (m - rank) * pvals[i]); adj[i] = min(1.0, run)
    return adj


def rank_biserial(d):
    d = np.asarray(d); d = d[d != 0]
    if len(d) == 0:
        return 0.0
    ranks = pd.Series(np.abs(d)).rank().to_numpy()
    return (ranks[d > 0].sum() - ranks[d < 0].sum()) / ranks.sum()


def paired_test(x, alternative):
    x = np.asarray(x, float)
    if np.all(x == 0):
        return 1.0
    return wilcoxon(x, alternative=alternative, zero_method="wilcox").pvalue


def iqr(s):
    return f"{s.median():.3f} [{s.quantile(.25):.3f}-{s.quantile(.75):.3f}]"


def main():
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else newest_results()
    meta = json.loads((path.parent / "meta.json").read_text(encoding="utf-8"))
    df = pd.read_csv(path)
    df["level"] = df["level"].astype(str)
    locked = [str(x) for x in CFG["design"]["sm_clock_levels_mhz"] if x != "unlocked"]
    base = df[df.level == "unlocked"].set_index(["block", "kernel"])[["throughput", "epw"]]
    df = df.join(base, on=["block", "kernel"], rsuffix="_unl")
    df["rel_thr"] = df.throughput / df.throughput_unl
    df["rel_epw"] = df.epw / df.epw_unl

    L = [f"# W1 downclock results", "",
         f"Source: `{path}` | run {meta['utc']} | admin {meta['admin']} | AC {meta['ac_plugged']} | ambient {meta['ambient_c']} C | "
         f"{meta['gpu']} | driver {meta['driver']} | yaml {meta['yaml_sha']} | git {meta['git_head'][:8]}{' (dirty)' if meta['git_dirty'] else ''}",
         f"Execution mode: {meta['execution_mode']}. Blocks: {df.block.nunique()}. Flagged rows: {int((df["flags"].fillna('') != '').sum())} of {len(df)}.", "",
         "## Per-cell summary (median [IQR] over blocks; ratios are within-block vs the unlocked cell)", "",
         "| kernel | clock | n | SM MHz (med) | throughput | rel. throughput | power W (counter) | energy/work J | rel. energy/work | flags |",
         "|---|---|---|---|---|---|---|---|---|---|"]
    for k in ("mem", "fma"):
        for lv in locked + ["unlocked"]:
            c = df[(df.kernel == k) & (df.level == lv)]
            unit = "GB/s" if k == "mem" else "GFLOP/s"
            wunit = "J/GB" if k == "mem" else "J/GFLOP"
            nfl = int((c["flags"].fillna("") != "").sum())
            L.append(f"| {k} | {lv} | {len(c)} | {c.sm_clock_med.median():.0f} | {c.throughput.median():.1f} {unit} | "
                     f"{iqr(c.rel_thr)} | {c.power_counter_w.median():.1f} | {c.epw.median():.4f} {wunit} | {iqr(c.rel_epw)} | {nfl} |")

    wide_thr = df.pivot_table(index=["block", "level"], columns="kernel", values="rel_thr")
    wide_epw = df.pivot_table(index=["block", "level"], columns="kernel", values="rel_epw")
    h1, h2, h3 = [], [], []
    for lv in locked:
        t = wide_thr.xs(lv, level="level"); e = wide_epw.xs(lv, level="level")
        d1 = (t["mem"] - t["fma"]).dropna()
        h1.append((lv, len(d1), d1.median(), paired_test(d1, "greater"), rank_biserial(d1)))
        d2 = (e["mem"] - 1.0).dropna()
        h2.append((lv, len(d2), e["mem"].median(), paired_test(d2, "less"), rank_biserial(-d2)))
        d3 = (e["mem"] - e["fma"]).dropna()
        h3.append((lv, len(d3), d3.median(), paired_test(d3, "less"), rank_biserial(-d3)))
    a1 = holm([x[3] for x in h1]); a2 = holm([x[3] for x in h2]); a3 = holm([x[3] for x in h3])

    L += ["", "## H1: memory-bound keeps more throughput than compute-bound (one-sided paired Wilcoxon, Holm over 5 levels)", "",
          "| clock | n | median(ratio_mem - ratio_fma) | p | p (Holm) | rank-biserial | significant |", "|---|---|---|---|---|---|---|"]
    for (lv, n, med, p, r), pa in zip(h1, a1):
        L.append(f"| {lv} | {n} | {med:+.3f} | {p:.4f} | {pa:.4f} | {r:+.2f} | {'yes' if pa < ALPHA else 'no'} |")
    n1 = int((a1 < ALPHA).sum())
    L += ["", f"Decision (registered: >= 4 of 5 levels): **H1 {'SUPPORTED' if n1 >= 4 else 'NOT SUPPORTED'}** ({n1}/5 significant).", "",
          "## H2: energy per unit work for memory-bound falls below unlocked (one-sided Wilcoxon on ratio-1 < 0)", "",
          "| clock | n | median rel. energy/work (mem) | p | p (Holm) | rank-biserial | significant |", "|---|---|---|---|---|---|---|"]
    for (lv, n, med, p, r), pa in zip(h2, a2):
        L.append(f"| {lv} | {n} | {med:.3f} | {p:.4f} | {pa:.4f} | {r:+.2f} | {'yes' if pa < ALPHA else 'no'} |")
    n2 = int((a2 < ALPHA).sum())
    L += ["", f"Decision (registered: >= 1 level): **H2 {'SUPPORTED' if n2 >= 1 else 'NOT SUPPORTED'}** ({n2}/5 significant).", "",
          "## Secondary (exploratory): relative energy/work, mem vs fma (paired, one-sided mem < fma)", "",
          "| clock | n | median(rel_epw_mem - rel_epw_fma) | p (Holm) |", "|---|---|---|---|"]
    for (lv, n, med, p, r), pa in zip(h3, a3):
        L.append(f"| {lv} | {n} | {med:+.3f} | {pa:.4f} |")

    L += ["", "## Flags (validity checks; cells stay in the data)", ""]
    fl = df[df["flags"].fillna("") != ""][["block", "kernel", "level", "flags"]]
    L.append(fl.to_string(index=False) if len(fl) else "none")
    cks = df.groupby("kernel").checksum.nunique()
    L += ["", f"Distinct checksums per kernel (registered check: identical across reps): {cks.to_dict()}"]

    # Audit power numbers, with the load and clock they were measured at.
    aud = json.loads((ROOT / "data" / "capability_audit.json").read_text(encoding="utf-8"))
    rows = {r["item"]: r for r in aud["rows"]}
    L += ["", "## The 94 W vs 28.5 W numbers from the capability audit", ""]
    pw = rows.get("NVML power_w"); lk = rows.get("nvidia-smi -lgc/-rgc (SM clock lock)")
    L.append(f"- Current audit file (admin={aud['env']['admin']}, run {aud['env']['timestamp']}): NVML power_w single read under the 4096x4096 fp16 matmul load, "
             f"clock unlocked: **{pw['reading']} W**; clock-lock row: `{lk['reading']}`.")
    old = subprocess.run(["git", "-C", str(ROOT), "show", "7120171:data/capability_audit.json"], capture_output=True, text=True)
    if old.returncode == 0:
        o = json.loads(old.stdout); orows = {r["item"]: r for r in o["rows"]}
        L.append(f"- Earlier non-admin audit (git 7120171, {o['env']['timestamp']}): NVML power_w single read under the same matmul load, unlocked: "
                 f"**{orows['NVML power_w']['reading']} W**, SM clock read {orows['NVML sm_clock_mhz']['reading']} MHz.")
    L.append("- These are single instantaneous NVML reads from different runs, not matched measurements. The matched comparison is the table above.")

    out = ROOT / "data" / "w1_downclock_results.md"
    out.write_text("\n".join(L), encoding="utf-8")
    print("\n".join(L)); print(f"\nwritten: {out}")


if __name__ == "__main__":
    main()
