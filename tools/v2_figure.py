"""Headline figure of v2: tok/s and excess late frames against the free GPU time per frame, every end-to-end condition of sprints 2 to 4.
   python tools/v2_figure.py [--out docs/figures/v2_cliff_vs_smooth.png]
Generated from the committed data only (data/v2/s2, s3, s4); it reads result.json, frames.npz and the summary.json files and runs nothing on the GPU.
x = 16.67 ms minus the SOLO median frame time (launch to completion) of the same foreground and jitter level.
Sprint 2 had no SOLO cell; its foreground is the sprint-3 level 'none' foreground (scene S1; the S5 foreground is the S1 loop), so the sprint-3 'none' SOLO median is used for it and its excess late is its late % minus that SOLO's late %."""
import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
PERIOD_MS = 1000.0 / 60.0
S2 = ROOT / "data/v2/s2/20261107T223927Z_exp3_end_to_end"
S3 = ROOT / "data/v2/s3/20261108T100246Z_jitter"
S4 = ROOT / "data/v2/s4/20261108T105802Z_slack"
WARM_S = 5.0
SHAPE = {"none": "o", "moderate": "s", "heavy": "^"}
ARMS = {"3b_whole": ("3B whole token", "#7a7a7a"), "3b_g14": ("3B 14 groups", "#0072b2"), "8b_whole": ("8B whole token", "#b0b0b0"),
        "8b_g14": ("8B 14 groups", "#d55e00"), "8b_g28": ("8B 28 groups", "#009e73")}


def solo_median_ms(cells):
    """Median frame time (launch to completion, measured window) pooled over the SOLO cells."""
    v = []
    for c in cells:
        r = json.loads((c / "result.json").read_text())
        f = np.load(c / "frames.npz")
        keep = f["t_sched"] >= r["t0"] + WARM_S
        v.append((f["t_end"][keep] - f["t_start"][keep]) * 1e3)
    return float(np.median(np.concatenate(v)))


def points():
    """list of dict(arm, level, sprint, free, tok, excess, guard)"""
    pts = []
    s3 = json.loads((S3 / "summary.json").read_text())["table"]
    free3 = {lv: PERIOD_MS - solo_median_ms(sorted(S3.glob(f"{lv}_solo_rep*"))) for lv in SHAPE}
    for key, v in s3.items():
        lv, arm = key.split("|")
        if arm != "solo":
            pts.append(dict(arm=arm, level=lv, sprint=3, free=free3[lv], tok=v["tok"], excess=v["excess"], guard=0.0))
    solo_late_none = s3["none|solo"]["late"]
    for scene, arms in (("S1", (("whole", "3b_whole"), ("g14", "3b_g14"))), ("S5", (("whole", "8b_whole"), ("g14", "8b_g14")))):
        for kind, arm in arms:
            rs = [json.loads((c / "result.json").read_text()) for c in sorted(S2.glob(f"{scene}_{kind}_rep*"))]
            pts.append(dict(arm=arm, level="none", sprint=2, free=free3["none"], tok=float(np.mean([r["bg_tok_s"] for r in rs])),
                            excess=float(np.mean([100 * r["miss_frac"] for r in rs])) - solo_late_none, guard=0.0))
    s4 = json.loads((S4 / "summary.json").read_text())["table"]
    amap = {"3b_whole": "3b_whole", "3b_g14_m0": "3b_g14", "3b_g14_m1": "3b_g14", "8b_g14_m1": "8b_g14", "8b_g28_m1": "8b_g28"}
    for key, v in s4.items():
        lv, arm = key.split("|", 1)
        if arm != "solo":
            pts.append(dict(arm=amap[arm], level="moderate", sprint=4, free=PERIOD_MS - v["solo_med_ms"], tok=v["tok"], excess=v["excess"], guard=1.0 if arm.endswith("_m1") else 0.0))
    return pts


def main(out):
    pts = points()
    fig, ax = plt.subplots(1, 2, figsize=(12.5, 4.8), gridspec_kw=dict(width_ratios=[2.1, 1]))
    for a, (yk, ylab) in zip(ax, (("tok", "background decode throughput (tok/s)"), ("excess", "excess late frames over SOLO (pp)"))):
        for arm, (name, col) in ARMS.items():
            # the line joins the moderate-jitter points of sprints 3 and 4 (the one level measured at every free time); 8B arms at guard 1.0 in sprint 4, 3B at guard 0
            line = sorted([p for p in pts if p["arm"] == arm and p["level"] == "moderate" and (p["guard"] == 0.0 or arm.startswith("8b"))], key=lambda p: p["free"])
            if len(line) > 1:
                a.plot([p["free"] for p in line], [p[yk] for p in line], "--", color=col, lw=1.2, alpha=0.7, zorder=1)
        g1 = sorted([p for p in pts if p["arm"] == "3b_g14" and p["guard"] == 1.0], key=lambda p: p["free"])
        a.plot([p["free"] for p in g1], [p[yk] for p in g1], ":", color=ARMS["3b_g14"][1], lw=1.2, zorder=1)
        for p in pts:
            col = ARMS[p["arm"]][1]
            a.scatter(p["free"], p[yk], marker=SHAPE[p["level"]], s=46, facecolor="white" if p["guard"] == 1.0 else col, edgecolor=col, linewidth=1.4, zorder=3, alpha=0.9)
        a.set_xlabel("free GPU time per frame (ms)" + (" = 16.67 - SOLO median frame time" if yk == "tok" else ""))
        a.set_ylabel(ylab)
        a.invert_xaxis()
        a.grid(alpha=0.25)
    ax[0].set_title("Throughput against free time per frame", fontsize=10)
    ax[1].set_title("Excess late frames against free time per frame", fontsize=10)
    ax[1].axhline(0, color="k", lw=0.6)
    ax[1].axhspan(-0.3, 0.3, color="0.85", zorder=0)
    ax[1].text(0.02, 0.97, "grey band: +/-0.3 pp, noise", transform=ax[1].transAxes, ha="left", va="top", fontsize=7.5, color="0.35")
    handles = [plt.Line2D([], [], color=c, lw=2, label=n) for n, c in ARMS.values()]
    handles += [plt.Line2D([], [], color="k", marker=m, ls="", markerfacecolor="k", label=f"jitter {lv}") for lv, m in SHAPE.items()]
    handles += [plt.Line2D([], [], color="k", marker="s", ls="", markerfacecolor="white", label="guard 1.0 ms (open marker)")]
    ax[0].legend(handles=handles, fontsize=7.5, loc="upper right", ncol=2)
    fig.tight_layout()
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=170)
    for p in sorted(pts, key=lambda p: (p["sprint"], p["level"], p["arm"], p["guard"])):
        print(f"s{p['sprint']} {p['level']:9s} {p['arm']:9s} guard {p['guard']:.1f}  free {p['free']:.2f} ms  tok/s {p['tok']:6.2f}  excess {p['excess']:+.2f} pp")
    print("saved", out)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", default=str(ROOT / "docs/figures/v2_cliff_vs_smooth.png"))
    main(ap.parse_args().out)
