"""DESCRIPTIVE tables of the W5b evaluation (POST HOC: none of this is a registered test; the registered reading is analysis/w5_analysis.py -> data/w5_results.md).
Per budget, scene and controller: n cells, how many meet the miss limit, the power limit and both, median tok/s / miss / counter power, and the final pacing mode of each cell (d'B can be bimodal, journal 0059).
Run: python analysis/w5b_descriptive.py data/w5b/eval/results.csv data/w5b/eval_descriptive.md"""
import sys
from pathlib import Path

import pandas as pd

SLO = 0.01
ORDER = ["a", "g'B", "eB", "c'B-T3b", "c'B-T3c", "d'B"]


def table(df, budget):
    s = df[df.budget_w == budget].copy()
    s["miss_ok"] = s.miss_frac <= SLO + 1e-12
    s["pow_ok"] = s.power_w <= budget + 1e-12
    s["feas"] = s.miss_ok & s.pow_ok
    rows = []
    for (scene, c), g in s.groupby(["scene", "controller"]):
        modes = g.final_pacing_mode.fillna("none").value_counts().to_dict()
        rows.append(dict(scene=scene, controller=c, n=len(g), miss_ok=int(g.miss_ok.sum()), power_ok=int(g.pow_ok.sum()), feasible=int(g.feas.sum()),
                         med_tok_s=round(g.bg_tok_s.median(), 2), med_miss_pct=round(100 * g.miss_frac.median(), 2), med_power_w=round(g.power_w.median(), 1),
                         final_pacing_mode=", ".join(f"{k} {v}" for k, v in sorted(modes.items()))))
    t = pd.DataFrame(rows)
    t["o"] = t.controller.map({c: i for i, c in enumerate(ORDER)})
    return t.sort_values(["scene", "o"]).drop(columns="o")


def dbp_modes(df):
    """d'B cells: tok/s by final pacing mode (descriptive bimodality check)."""
    d = df[df.controller == "d'B"].copy()
    d["final_pacing_mode"] = d.final_pacing_mode.fillna("none")
    return d.groupby(["budget_w", "scene", "final_pacing_mode"]).agg(n=("bg_tok_s", "size"), med_tok_s=("bg_tok_s", "median"), min_tok_s=("bg_tok_s", "min"), max_tok_s=("bg_tok_s", "max"), med_miss=("miss_frac", "median")).round(3)


def scatter(df, png):
    """Miss fraction (%) against background tok/s, one point per cell, one panel per scene; colour = arm, filled = 60 W, hollow = 35 W; the dashed line is the 1% miss limit. Descriptive only."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    scenes = sorted(df.scene.unique())
    colors = dict(zip(ORDER, ["#7f7f7f", "#1f77b4", "#2ca02c", "#ff7f0e", "#d62728", "#9467bd"]))
    fig, axes = plt.subplots(1, len(scenes), figsize=(4 * len(scenes), 3.6), squeeze=False)
    for ax, scene in zip(axes[0], scenes):
        for c in ORDER:
            for b, filled in ((60.0, True), (35.0, False)):
                g = df[(df.scene == scene) & (df.controller == c) & (df.budget_w == b)]
                if len(g):
                    ax.scatter(g.bg_tok_s, 100 * g.miss_frac, s=22, facecolors=colors[c] if filled else "none", edgecolors=colors[c], label=f"{c} {b:.0f} W")
        ax.axhline(1.0, ls="--", c="k", lw=0.8)
        ax.set_title(scene); ax.set_xlabel("background tok/s"); ax.set_ylabel("foreground miss (%)")
    h, l = axes[0][0].get_legend_handles_labels()
    fig.legend(h, l, loc="lower center", ncol=6, fontsize=7)
    fig.tight_layout(rect=(0, 0.12, 1, 1))
    fig.savefig(png, dpi=130)
    plt.close(fig)


def main(path, out):
    df = pd.read_csv(path)
    scatter(df, str(Path(out).with_suffix(".png").with_name("eval_miss_vs_toks.png")))
    L = ["# W5b evaluation: DESCRIPTIVE tables (POST HOC, not registered tests)", "",
         f"Source: {Path(path).name}, {len(df)} cells. Feasible = miss <= 1% and counter power <= budget (the registered cell definition). tok/s is the background rate in the measured window; a feasible cell scores its tok/s, an infeasible one 0. final_pacing_mode: governed = the controller's final mode, static = its setting's mode, arm a = unaligned.", ""]
    for b in sorted(df.budget_w.unique(), reverse=True):
        L += [f"## {b:.0f} W ({'PRIMARY family' if b == 60 else 'EXPLORATORY family'})", "", table(df, b).to_string(index=False), ""]
    L += ["## d'B by final pacing mode (descriptive)", "", dbp_modes(df).to_string(), ""]
    Path(out).write_text("\n".join(L), encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
