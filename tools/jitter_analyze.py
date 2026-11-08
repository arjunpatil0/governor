"""v2 sprint 3 analysis (docs/V2_SPRINT3_JITTER.md).   python tools/jitter_analyze.py data/v2/s3/<stamp>_jitter
Per level and arm: tok/s, late-frame %, power, and EXCESS late % = the arm's late % minus the SOLO late % at the same level and repetition (same seed, same frame sequence), median over reps with the reps listed.
Decision rule (fixed in the doc before measuring), applied to the medians over the 3 reps of moderate and heavy: PASS = 14-group (3B) excess <= 1 pp at moderate and <= 2 pp at heavy with tok/s >= the 3B whole-token gate at
the same level; OVERLAP BONUS = 14-group excess < whole-token excess at heavy; FAIL = 14-group excess > 5 pp at moderate. Every late frame of an arm cell is classified by matching its sequence index to the SOLO cell of the
same level and rep: solo-caused (SOLO misses it too), burst-caused (an unannounced burst ran in the gap before it AND decode overlapped it), decode-overlap (decode overlapped it, overlap in ms), other. The slowdown of
frames decode touched is the frame's duration divided by the duration of the SAME frame in the SOLO cell (the cost sequence is identical, so this is a matched ratio). Decode overlap = decode group time (host launch to
host completion, a proxy for GPU activity) inside the frame's execution window. Writes summary.json beside the data and data/v2/s3_jitter.png."""
import csv
import json
import statistics as st
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
LEVELS = ("none", "moderate", "heavy")
ARMS = ("solo", "3b_whole", "3b_g14", "8b_g14")
PERIOD_MS = 1000.0 / 60.0


def load(cell):
    cell = Path(cell)
    r = json.loads((cell / "result.json").read_text())
    f = np.load(cell / "frames.npz")
    keep = f["t_sched"] >= r["t0"] + 5.0
    d = {key: f[key][keep] for key in f.files}
    d["dur_ms"] = (d["t_end"] - d["t_start"]) * 1e3
    d["late"] = d["lat_ms"] > PERIOD_MS
    iv = None
    if (cell / "decode_groups.csv").exists():
        rows = list(csv.DictReader(open(cell / "decode_groups.csv")))
        a = np.array([(float(x["t_launch_s"]), float(x["t_done_s"])) for x in rows])
        iv = a[np.argsort(a[:, 0])]
    d["overlap_ms"] = overlap(d["t_start"], d["t_end"], iv)
    return r, d


def overlap(ts, te, iv):
    ov = np.zeros(len(ts))
    if iv is None:
        return ov
    for i in range(len(ts)):
        k = np.searchsorted(iv[:, 1], ts[i], side="left")
        while k < len(iv) and iv[k, 0] < te[i]:
            ov[i] += max(0.0, min(te[i], iv[k, 1]) - max(ts[i], iv[k, 0]))
            k += 1
    return ov * 1e3


def pct(x, q):
    return float(np.percentile(x, q)) if len(x) else None


def main(d):
    d = Path(d)
    cells = {}
    for c in sorted(d.glob("*_rep*")):
        lvl, arm_rep = c.name.split("_", 1)
        arm, rep = arm_rep.rsplit("_rep", 1)
        cells[(lvl, arm, int(rep))] = c
    table, per_cell = {}, {}
    for lvl in LEVELS:
        for arm in ARMS:
            reps = sorted(r for (l, a, r) in cells if l == lvl and a == arm)
            if not reps:
                continue
            rows = []
            for r in reps:
                res, _ = per_cell.setdefault((lvl, arm, r), load(cells[(lvl, arm, r)]))
                solo = json.loads((cells[(lvl, "solo", r)] / "result.json").read_text())
                rows.append(dict(rep=r, tok=res["bg_tok_s"], late=100 * res["miss_frac"], power=res["power_w"], jpt=res["j_per_token"], rejected=res["power_rejected"], sm=res["sm_mhz_median"],
                                 solo_late=100 * solo["miss_frac"], excess=100 * (res["miss_frac"] - solo["miss_frac"]), p99=res["fg_p99_ms"]))
            table[(lvl, arm)] = dict(rows=rows, tok=st.median(x["tok"] for x in rows), late=st.median(x["late"] for x in rows), power=st.median(x["power"] for x in rows),
                                     excess=st.median(x["excess"] for x in rows), solo_late=st.median(x["solo_late"] for x in rows), rejected=sum(x["rejected"] for x in rows))
    # decision rule
    verdict = {}
    for lvl, limit in (("moderate", 1.0), ("heavy", 2.0)):
        g, w = table.get((lvl, "3b_g14")), table.get((lvl, "3b_whole"))
        if g and w:
            verdict[lvl] = dict(g14_excess=g["excess"], whole_excess=w["excess"], g14_tok=g["tok"], whole_tok=w["tok"], limit_pp=limit, pass_=bool(g["excess"] <= limit and g["tok"] >= w["tok"]))
    bonus = bool("heavy" in verdict and verdict["heavy"]["g14_excess"] < verdict["heavy"]["whole_excess"])
    fail = bool("moderate" in verdict and verdict["moderate"]["g14_excess"] > 5.0)
    # cause breakdown, matched to SOLO by sequence index
    causes, slowdowns = {}, {}
    for (lvl, arm, r), c in cells.items():
        if arm == "solo" or lvl == "none" and False:
            continue
        res, f = per_cell.setdefault((lvl, arm, r), load(c))
        _, s = per_cell.setdefault((lvl, "solo", r), load(cells[(lvl, "solo", r)]))
        solo_late = dict(zip(s["k"].tolist(), s["late"].tolist()))
        solo_dur = dict(zip(s["k"].tolist(), s["dur_ms"].tolist()))
        co = causes.setdefault((lvl, arm), dict(frames=0, late=0, solo=0, burst=0, overlap=0, other=0, overlap_ms=[], solo_late_not_late_here=0))
        sl = slowdowns.setdefault((lvl, arm), [])
        for i, k in enumerate(f["k"].tolist()):
            co["frames"] += 1
            sl_k = solo_late.get(k)
            if f["late"][i]:
                co["late"] += 1
                if sl_k:
                    co["solo"] += 1
                elif f["overlap_ms"][i] > 0 and f["burst"][i]:
                    co["burst"] += 1; co["overlap_ms"].append(float(f["overlap_ms"][i]))
                elif f["overlap_ms"][i] > 0:
                    co["overlap"] += 1; co["overlap_ms"].append(float(f["overlap_ms"][i]))
                else:
                    co["other"] += 1
            elif sl_k:
                co["solo_late_not_late_here"] += 1
            if f["overlap_ms"][i] > 0 and k in solo_dur and solo_dur[k] > 0:
                sl.append(f["dur_ms"][i] / solo_dur[k])
    # print
    f1 = lambda v, nd=2: "n/a" if v is None else f"{v:.{nd}f}"
    print(f"{'level':<9}{'arm':<10}{'tok/s':>7}  {'late %':>7} {'solo late %':>11} {'excess pp':>10}  {'power W':>8}  reps (tok/s | late % | excess)")
    for lvl in LEVELS:
        for arm in ARMS:
            t = table.get((lvl, arm))
            if t:
                print(f"{lvl:<9}{arm:<10}{t['tok']:>7.1f}  {t['late']:>7.2f} {t['solo_late']:>11.2f} {t['excess']:>10.2f}  {t['power']:>8.1f}  " + "  ".join(f"[{x['tok']:.1f} | {x['late']:.2f} | {x['excess']:+.2f}]" for x in t["rows"]) + f"  rejected {t['rejected']}")
    print("DECISION RULE:", json.dumps({k: {kk: (round(vv, 3) if isinstance(vv, float) else vv) for kk, vv in v.items()} for k, v in verdict.items()}), "| OVERLAP BONUS:", bonus, "| FAIL:", fail)
    print("LATE-FRAME CAUSES (pooled over reps; frames in measured windows)")
    print(f"{'level':<9}{'arm':<10}{'frames':>7}{'late':>6}{'solo':>6}{'burst+dec':>10}{'decode':>8}{'other':>7}{'mean ovl ms':>12}{'solo-late-but-ok':>18}  slowdown of touched frames p50/p99 (n)")
    for lvl in LEVELS:
        for arm in ARMS[1:]:
            c = causes.get((lvl, arm))
            if c:
                s = slowdowns[(lvl, arm)]
                print(f"{lvl:<9}{arm:<10}{c['frames']:>7}{c['late']:>6}{c['solo']:>6}{c['burst']:>10}{c['overlap']:>8}{c['other']:>7}{f1(float(np.mean(c['overlap_ms'])) if c['overlap_ms'] else None):>12}{c['solo_late_not_late_here']:>18}  {f1(pct(s, 50))}/{f1(pct(s, 99))} ({len(s)})")
    summary = dict(table={f"{k[0]}|{k[1]}": v for k, v in table.items()}, verdict=verdict, bonus=bonus, fail=fail,
                   causes={f"{k[0]}|{k[1]}": {kk: (vv if kk != "overlap_ms" else [float(np.mean(vv)) if vv else None, len(vv)]) for kk, vv in v.items()} for k, v in causes.items()},
                   slowdown={f"{k[0]}|{k[1]}": dict(p50=pct(v, 50), p99=pct(v, 99), n=len(v)) for k, v in slowdowns.items()})
    (d / "summary.json").write_text(json.dumps(summary, indent=1, default=str), encoding="utf-8")
    plot(table, ROOT / "data" / "v2" / "s3_jitter.png")


def plot(table, out):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(1, 2, figsize=(11, 4))
    x = {lvl: i for i, lvl in enumerate(LEVELS)}
    style = {"3b_whole": ("#8b949e", "o", "3B whole-token gate"), "3b_g14": ("#1f6feb", "s", "3B 14-group gate"), "8b_g14": ("#bf8700", "^", "8B 14-group gate")}
    for arm, (c, m, lab) in style.items():
        xs = [x[l] for l in LEVELS if (l, arm) in table]
        ax[0].plot(xs, [table[(l, arm)]["excess"] for l in LEVELS if (l, arm) in table], m + "-", color=c, label=lab)
        for l in LEVELS:
            if (l, arm) in table:
                ax[0].plot([x[l]] * len(table[(l, arm)]["rows"]), [r["excess"] for r in table[(l, arm)]["rows"]], ".", color=c, alpha=0.5)
        ax[1].plot(xs, [table[(l, arm)]["tok"] for l in LEVELS if (l, arm) in table], m + "-", color=c, label=lab)
    ax[0].axhline(0, color="k", lw=0.5)
    ax[0].set_xticks(range(3)); ax[0].set_xticklabels(LEVELS); ax[0].set_ylabel("excess late frames (pp over SOLO)"); ax[0].set_title("Excess late frames vs jitter level (median, reps as dots)", fontsize=9); ax[0].legend(fontsize=8)
    ax[1].set_xticks(range(3)); ax[1].set_xticklabels(LEVELS); ax[1].set_ylabel("background tok/s"); ax[1].set_title("Throughput vs jitter level", fontsize=9)
    fig.tight_layout()
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=140)


if __name__ == "__main__":
    main(sys.argv[1])
