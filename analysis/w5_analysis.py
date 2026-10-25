"""Registered W5b analysis of experiments/w5_governor.yaml (committed 2026-10-23): HW1 constraints, HW2 (superiority in S5 + non-inferiority in S0/S2 + HW1 for d'B), HW3, HW7.
Input: a cell table with columns block, scene, controller, budget_w, bg_tok_s, miss_frac, power_w (one row per evaluation cell). SCORE of a cell = bg_tok_s if feasible
(miss_frac <= 0.01 and power_w <= budget_w) else 0: infeasible cells are NOT dropped. Paired by block. Exact one-sided Wilcoxon signed-rank (zero differences = ties drop out, average ranks),
Holm over 3 (HW2) or 5 (HW3), 90% block-bootstrap CI of the median. Every number in the report traces to the input table.
Run: python analysis/w5_analysis.py data/w5/results.csv     (writes data/w5_results.md)"""
import sys
import zlib
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SLO = 0.01
NI_MARGIN = 0.95
PRIMARY_SCENES = ("S0", "S1", "S1d", "S2", "S5")
COMPARATORS = ("c'B-T3b", "g'B", "eB")        # c'B-T3b = PRIMARY c'B comparator (target 0.5, ki 0.15: the registered rule's output on the T3b grid; addendum O-7 amendment 2026-10-25)
SECONDARY = ("c'B-T3c",)                      # c'B-T3c = the same rule after the O-6 extension: reported, never part of the registered reading
MIN_NONTIED = 6                 # with fewer non-tied blocks the exact one-sided p cannot go below 0.05/3 (1/64 = 0.0156 < 0.0167 needs n >= 6)


def cell_scores(df):
    feasible = (df.miss_frac <= SLO + 1e-12) & (df.power_w <= df.budget_w + 1e-12)
    return pd.Series(np.where(feasible, df.bg_tok_s, 0.0), index=df.index)


def wilcoxon_greater_exact(x, y):
    """One-sided exact Wilcoxon signed-rank p for H1: x > y. Zero differences are dropped. Returns (p, n_nontied). Exact conditional distribution over the 2^n sign patterns with average ranks."""
    d = np.asarray(x, float) - np.asarray(y, float)
    d = d[np.abs(d) > 1e-12]
    n = len(d)
    if n == 0:
        return 1.0, 0
    ranks = pd.Series(np.abs(d)).rank(method="average").to_numpy()
    r2 = np.round(2 * ranks).astype(int)
    total = int(r2.sum())
    counts = np.zeros(total + 1)
    counts[0] = 1.0
    for r in r2:
        new = counts.copy()
        new[r:] += counts[:total + 1 - r]
        counts = new
    w_obs = int(round(2 * ranks[d > 0].sum()))
    return float(counts[w_obs:].sum() / 2.0 ** n), n


def holm(pvals, alpha=0.05):
    """Holm step-down; returns the reject decision in the input order."""
    m = len(pvals)
    order = np.argsort(pvals)
    rej = [False] * m
    for k, i in enumerate(order):
        if pvals[i] <= alpha / (m - k):
            rej[i] = True
        else:
            break
    return rej


def bootstrap_ci_median(d, seed=0, level=0.90, n_boot=10000):
    d = np.asarray(d, float)
    rng = np.random.default_rng(seed)
    meds = np.median(rng.choice(d, size=(n_boot, len(d)), replace=True), axis=1)
    return float(np.percentile(meds, 100 * (1 - level) / 2)), float(np.percentile(meds, 100 * (1 + level) / 2))


def ratio_blocks(d, comp):
    """Per-block ratio score(d'B) / score(comparator) over blocks where the comparator scored > 0 (a d'B score of 0 gives ratio 0); returns (ratios, n_excluded)."""
    d, comp = np.asarray(d, float), np.asarray(comp, float)
    m = comp > 0
    return d[m] / comp[m], int((~m).sum())


def _scores(df, budget):
    s = df[df.budget_w == budget].copy()
    s["score"] = cell_scores(s)
    return s.pivot_table(index="block", columns=["scene", "controller"], values="score", aggfunc="first")


def hw1_table(df, budget):
    s = df[df.budget_w == budget].copy()
    s["feasible"] = (s.miss_frac <= SLO + 1e-12) & (s.power_w <= s.budget_w + 1e-12)
    g = s.groupby(["scene", "controller"]).agg(n=("block", "size"), frac_feasible=("feasible", "mean"), mean_miss=("miss_frac", "mean"))
    g["holds"] = (g.frac_feasible >= 0.9) & (g.mean_miss <= SLO + 1e-12)
    return g


def _stable_seed(seed, *parts):
    return zlib.crc32("|".join(map(str, (seed, *parts))).encode())


def superiority(sc, scene, a, comps, seed, alpha=0.05):
    """a vs each comparator in one scene: exact Wilcoxon, Holm over len(comps), CI of the median paired difference."""
    out, ps = {}, []
    for c in comps:
        x, y = sc[(scene, a)].to_numpy(), sc[(scene, c)].to_numpy()
        p, n = wilcoxon_greater_exact(x, y)
        lo, hi = bootstrap_ci_median(x - y, seed=_stable_seed(seed, scene, a, c))
        out[c] = dict(p=p, n_nontied=n, inconclusive=n < MIN_NONTIED, median_diff=float(np.median(x - y)), ci_lo=lo, ci_hi=hi)
        ps.append(p)
    for c, r in zip(comps, holm(ps, alpha)):
        out[c]["holm_reject"] = bool(r)
        out[c]["reject"] = bool(r and out[c]["ci_lo"] > 0 and not out[c]["inconclusive"])
    return out


def _ni(sc, scene, c, seed):
    r, n_ex = ratio_blocks(sc[(scene, "d'B")].to_numpy(), sc[(scene, c)].to_numpy())
    if len(r) == 0:
        return {"median": float("nan"), "lo": float("nan"), "hi": float("nan"), "n": 0, "n_excluded": n_ex, "pass": True}          # comparator scored 0 in every block: nothing to be inferior to
    lo, hi = bootstrap_ci_median(r, seed=_stable_seed(seed, "ni", scene, c))
    return {"median": float(np.median(r)), "lo": lo, "hi": hi, "n": len(r), "n_excluded": n_ex, "pass": bool(lo >= NI_MARGIN)}


def hw2_report(df, budget=60.0, seed=0):
    sc = _scores(df, budget)
    rep = dict(budget=budget, s5=superiority(sc, "S5", "d'B", COMPARATORS, seed), ni={}, hw1={}, secondary={})
    for scene in ("S0", "S2"):
        rep["ni"][scene] = {c: _ni(sc, scene, c, seed) for c in COMPARATORS}
    sec = [c for c in SECONDARY if ("S5", c) in sc.columns]
    if sec:                                                  # secondary comparator(s): same tests, own Holm family, NOT part of earns_place
        rep["secondary"] = dict(s5=superiority(sc, "S5", "d'B", tuple(sec), seed), ni={scene: {c: _ni(sc, scene, c, seed) for c in sec} for scene in ("S0", "S2")})
    h = hw1_table(df, budget)
    for scene in PRIMARY_SCENES:
        rep["hw1"][scene] = bool(h.loc[(scene, "d'B"), "holds"])
    return rep


def hw3_report(df, budget=60.0, seed=0):
    """d'B vs g'B and vs eB on the same score: one Holm family of 5 scenes per comparator."""
    sc = _scores(df, budget)
    out = {}
    for c in ("g'B", "eB"):
        ps, rows = [], {}
        for scene in PRIMARY_SCENES:
            x, y = sc[(scene, "d'B")].to_numpy(), sc[(scene, c)].to_numpy()
            p, n = wilcoxon_greater_exact(x, y)
            lo, hi = bootstrap_ci_median(x - y, seed=_stable_seed(seed, "hw3", scene, c))
            rows[scene] = dict(p=p, n_nontied=n, inconclusive=n < MIN_NONTIED, median_diff=float(np.median(x - y)), ci_lo=lo, ci_hi=hi)
            ps.append(p)
        for scene, r in zip(PRIMARY_SCENES, holm(ps)):
            rows[scene]["reject"] = bool(r and rows[scene]["ci_lo"] > 0 and not rows[scene]["inconclusive"])
        out[c] = rows
    return out


def earns_place(rep):
    return bool(all(r["reject"] for r in rep["s5"].values()) and all(v["pass"] for sc in rep["ni"].values() for v in sc.values()) and all(rep["hw1"].values()))


def secondary_lines(rep):
    """Report lines of the secondary comparator(s) (c'B-T3c): same tests, labelled SECONDARY, not part of the registered reading."""
    sec = rep.get("secondary") or {}
    if not sec:
        return []
    L = ["", "### SECONDARY comparator c'B-T3c (not part of the registered reading; reported for the paper)", ""]
    for c, r in sec["s5"].items():
        L.append(f"- S5 d'B vs {c}: median diff {r['median_diff']:.2f} tok/s, 90% CI [{r['ci_lo']:.2f}, {r['ci_hi']:.2f}], p {r['p']:.5f}, non-tied blocks {r['n_nontied']}, " + ("INCONCLUSIVE, " if r["inconclusive"] else "") + f"REJECT {r['reject']}")
    for scene, d in sec["ni"].items():
        for c, r in d.items():
            L.append(ni_line(scene, c, r))
    return L


def hw7_staleness(tokens, clock_changes, settle_s=1.0, window_s=2.0, min_clean=8):
    """Descriptive staleness check of the clean-token estimate after each accepted clock change (yaml HW7). tokens: t_start, tok_ms, overlapped, est_clean_ms (optional overran).
    error = |est_clean at the first token starting >= t_c + settle - median clean tok_ms in [t_c + settle, t_c + settle + window]| / that median; fewer than min_clean clean tokens = unrecovered."""
    rows = []
    for tc in clock_changes:
        w = tokens[(tokens.t_start >= tc + settle_s) & (tokens.t_start <= tc + settle_s + window_s)]
        clean = w[w.overlapped == 0]
        n = len(clean)
        first = tokens[tokens.t_start >= tc + settle_s].head(1)
        est = float(first.est_clean_ms.iloc[0]) if len(first) else float("nan")
        true = float(clean.tok_ms.median()) if n else float("nan")
        row = dict(t_change=tc, est_clean=est, true_median=true, error=abs(est - true) / true if n else float("nan"), n_clean_window=n, unrecovered=n < min_clean)
        if "overran" in tokens.columns:
            after = tokens[(tokens.t_start >= tc) & (tokens.t_start <= tc + 3.0)]
            row["overrun_frac_3s"], row["overrun_frac_cell"] = float(after.overran.mean()) if len(after) else float("nan"), float(tokens.overran.mean())
        rows.append(row)
    return pd.DataFrame(rows)


def ni_line(scene, c, r):
    """One non-inferiority report line. A pass that rests on a comparator scoring 0 in every block is marked VACUOUS (plan addendum O-4 section 3: reporting only, pass/fail unchanged)."""
    vac = " VACUOUS (comparator scored 0 in every block)" if r["n"] == 0 and r["pass"] else ""
    return f"- {scene} vs {c}: median ratio {r['median']:.3f}, CI [{r['lo']:.3f}, {r['hi']:.3f}], blocks used {r['n']}, excluded (comparator 0) {r['n_excluded']}, pass {r['pass']}{vac}"


def main(path):
    df = pd.read_csv(path)
    L = [f"# W5b confirmatory analysis (analysis/w5_analysis.py on {Path(path).name}); registered in experiments/w5_governor.yaml", ""]
    for b in sorted(df.budget_w.unique()):
        tag = "PRIMARY" if b == 60.0 else "EXPLORATORY"
        L += [f"## Budget {b:.0f} W ({tag})", "", "### HW1 per controller and scene", hw1_table(df, b).round(3).to_string(), ""]
        if b == 60.0:
            rep = hw2_report(df, b)
            L += ["### HW2 (score = tok/s if feasible else 0; paired by block)", "", "S5 superiority of d'B vs c'B-T3b (PRIMARY), g'B, eB (exact Wilcoxon, Holm over 3, 90% bootstrap CI of the median difference):"]
            for c, r in rep["s5"].items():
                L.append(f"- vs {c}: median diff {r['median_diff']:.2f} tok/s, 90% CI [{r['ci_lo']:.2f}, {r['ci_hi']:.2f}], p {r['p']:.5f}, non-tied blocks {r['n_nontied']}, " + ("INCONCLUSIVE, " if r["inconclusive"] else "") + f"Holm-reject {r['holm_reject']}, REJECT {r['reject']}")
            L += ["", f"Non-inferiority (ratio d'B / comparator, 90% CI lower bound >= {NI_MARGIN}; PRIMARY c'B comparator = c'B-T3b):"]
            for scene, d in rep["ni"].items():
                for c, r in d.items():
                    L.append(ni_line(scene, c, r))
            L += secondary_lines(rep)
            L += ["", "HW1 for d'B in every primary scene: " + ", ".join(f"{s} {v}" for s, v in rep["hw1"].items()), "",
                  f"**d'B {'EARNS ITS PLACE' if earns_place(rep) else 'DOES NOT EARN ITS PLACE'}** under the registered reading (S5 win against all three, non-inferiority in S0 and S2 against all three, HW1 in every primary scene).", ""]
            L += ["### HW3 (d'B vs g'B and eB; Holm over the 5 scenes)", ""]
            for c, rows in hw3_report(df, b).items():
                L += [f"d'B vs {c}: " + "; ".join(f"{s} diff {r['median_diff']:.2f} [{r['ci_lo']:.2f}, {r['ci_hi']:.2f}] reject {r['reject']}" for s, r in rows.items()), ""]
    out = ROOT / "data" / "w5_results.md"
    out.write_text("\n".join(L), encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    main(sys.argv[1])
