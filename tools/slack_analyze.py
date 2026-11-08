"""v2 sprint 4 analysis (docs/V2_SPRINT4_LOW_SLACK.md).   python tools/slack_analyze.py data/v2/s4/<stamp>_slack [--sprint3 data/v2/s3/<stamp>_jitter]
Per level (tight, very_tight) and arm: tok/s, late %, excess late over SOLO (same seed), power (flag > 60 W), SOLO median frame time. Decision rule (fixed in the doc before measuring): PASS = the best 3B group arm has
excess <= 1 pp (tight) / <= 2 pp (very tight) with tok/s >= whole token (literal), reported also with the added condition tok/s >= 5 (stricter), 'best' = highest tok/s among the 3B group arms that meet the excess limit;
MARGIN WORKS = guard 1.0 cuts the decode-attributed late frames against guard 0 (3B, 14 groups) without losing more than 15% of tok/s; FAIL = best 3B group arm excess > 5 pp at tight.
Cause of every late frame (matched to the SOLO cell by sequence index): solo-caused; burst+decode (a burst ran in the gap before it and decode overlapped it); early submit (decode overlapped it, no burst, and the overlap is
no more than how early the frame was submitted plus 0.3 ms); decode overlap (any other); other. Slowdown of touched frames = duration / duration of the same frame in the SOLO cell. Writes summary.json and the plot."""
import argparse
import json
import statistics as st
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import jitter_analyze as JA  # noqa: E402

LEVELS = ("tight", "very_tight")
ARMS = ("solo", "3b_whole", "3b_g14_m0", "3b_g14_m1", "8b_g14_m1", "8b_g28_m1")
PERIOD_MS = 1000.0 / 60.0


def parse(name):
    for lvl in LEVELS:
        if name.startswith(lvl + "_"):
            arm, rep = name[len(lvl) + 1:].rsplit("_rep", 1)
            return lvl, arm, int(rep)
    return None


def classify(f, solo_late, i, k):
    if solo_late.get(k):
        return "solo"
    ov, burst = f["overlap_ms"][i], f["burst"][i]
    if ov > 0 and burst:
        return "burst"
    early_ms = max(0.0, (f["t_sched"][i] - f["t_submit"][i]) * 1e3)
    if ov > 0 and ov <= early_ms + 0.3:
        return "early"
    if ov > 0:
        return "overlap"
    return "other"


def main(d, sprint3):
    d = Path(d)
    cells = {}
    for c in sorted(d.iterdir()):
        p = parse(c.name)
        if p and (c / "result.json").exists():
            cells[p] = c
    cache = {}

    def get(key):
        if key not in cache:
            cache[key] = JA.load(cells[key])
        return cache[key]

    table = {}
    for lvl in LEVELS:
        for arm in ARMS:
            reps = sorted(r for (l, a, r) in cells if l == lvl and a == arm)
            if not reps:
                continue
            rows = []
            for r in reps:
                res, f = get((lvl, arm, r))
                solo_res, solo_f = get((lvl, "solo", r))
                rows.append(dict(rep=r, tok=res["bg_tok_s"], late=100 * res["miss_frac"], power=res["power_w"], rejected=res["power_rejected"], sm=res["sm_mhz_median"], solo_late=100 * solo_res["miss_frac"],
                                 excess=100 * (res["miss_frac"] - solo_res["miss_frac"]), solo_med_ms=float(np.median(solo_f["dur_ms"])), c0=res.get("c0"), guard=res.get("guard_ms")))
            table[(lvl, arm)] = dict(rows=rows, tok=st.median(x["tok"] for x in rows), late=st.median(x["late"] for x in rows), excess=st.median(x["excess"] for x in rows),
                                     power=st.median(x["power"] for x in rows), solo_late=st.median(x["solo_late"] for x in rows), solo_med_ms=st.median(x["solo_med_ms"] for x in rows),
                                     rejected=sum(x["rejected"] for x in rows))
    # causes and slowdown
    causes, slow, touched = {}, {}, {}
    for (lvl, arm, r), c in cells.items():
        if arm == "solo":
            continue
        res, f = get((lvl, arm, r))
        _, s = get((lvl, "solo", r))
        solo_late = dict(zip(s["k"].tolist(), s["late"].tolist()))
        solo_dur = dict(zip(s["k"].tolist(), s["dur_ms"].tolist()))
        co = causes.setdefault((lvl, arm), dict(frames=0, late=0, solo=0, burst=0, early=0, overlap=0, other=0, solo_late_ok=0, ovl=[]))
        sl = slow.setdefault((lvl, arm), [])
        tc = touched.setdefault((lvl, arm), [0, 0])
        for i, k in enumerate(f["k"].tolist()):
            co["frames"] += 1
            tc[1] += 1
            if f["late"][i]:
                co["late"] += 1
                cat = classify(f, solo_late, i, k)
                co[cat] += 1
                if cat in ("burst", "early", "overlap"):
                    co["ovl"].append(float(f["overlap_ms"][i]))
            elif solo_late.get(k):
                co["solo_late_ok"] += 1
            if f["overlap_ms"][i] > 0:
                tc[0] += 1
                if solo_dur.get(k, 0) > 0:
                    sl.append(f["dur_ms"][i] / solo_dur[k])
    # decision rule
    verdict = {}
    for lvl, limit in (("tight", 1.0), ("very_tight", 2.0)):
        wh = table.get((lvl, "3b_whole"))
        cands = [(arm, table[(lvl, arm)]) for arm in ("3b_g14_m0", "3b_g14_m1") if (lvl, arm) in table]
        ok = [(a, t) for a, t in cands if t["excess"] <= limit and wh and t["tok"] >= wh["tok"]]
        ok_strict = [(a, t) for a, t in ok if t["tok"] >= 5.0]
        best = max(ok, key=lambda x: x[1]["tok"]) if ok else None
        best_s = max(ok_strict, key=lambda x: x[1]["tok"]) if ok_strict else None
        m0, m1 = table.get((lvl, "3b_g14_m0")), table.get((lvl, "3b_g14_m1"))
        attr = lambda k: (causes[(lvl, k)]["burst"] + causes[(lvl, k)]["early"] + causes[(lvl, k)]["overlap"]) if (lvl, k) in causes else None
        verdict[lvl] = dict(limit_pp=limit, pass_literal=best[0] if best else None, pass_strict=best_s[0] if best_s else None, excess={a: t["excess"] for a, t in cands},
                            decode_attributed_late={"m0": attr("3b_g14_m0"), "m1": attr("3b_g14_m1")},
                            margin_cuts=bool(attr("3b_g14_m1") is not None and attr("3b_g14_m0") is not None and attr("3b_g14_m1") < attr("3b_g14_m0")),
                            toks_kept=(m1["tok"] / m0["tok"]) if m0 and m1 and m0["tok"] > 0 else None)
        verdict[lvl]["margin_works"] = bool(verdict[lvl]["margin_cuts"] and verdict[lvl]["toks_kept"] is not None and verdict[lvl]["toks_kept"] >= 0.85)
    fail = bool("tight" in verdict and cands and min(t["excess"] for _, t in [(a, table[("tight", a)]) for a in ("3b_g14_m0", "3b_g14_m1") if ("tight", a) in table]) > 5.0)
    # print
    print(f"{'level':<11}{'arm':<11}{'tok/s':>7}  {'late %':>7} {'solo late %':>11} {'excess pp':>10}  {'power W':>8}  SOLO median frame ms   reps (tok/s | late % | excess)")
    for lvl in LEVELS:
        for arm in ARMS:
            t = table.get((lvl, arm))
            if t:
                flag = "  >60 W" if t["power"] > 60.0 else ""
                print(f"{lvl:<11}{arm:<11}{t['tok']:>7.1f}  {t['late']:>7.2f} {t['solo_late']:>11.2f} {t['excess']:>10.2f}  {t['power']:>8.1f}{flag:<7} {t['solo_med_ms']:>8.2f}   " + "  ".join(f"[{x['tok']:.1f} | {x['late']:.2f} | {x['excess']:+.2f}]" for x in t["rows"]) + f"  rej {t['rejected']}")
    print("DECISION:", json.dumps({k: {kk: (round(vv, 3) if isinstance(vv, float) else vv) for kk, vv in v.items()} for k, v in verdict.items()}), "| FAIL:", fail)
    print("CAUSES (pooled over reps)")
    print(f"{'level':<11}{'arm':<11}{'frames':>7}{'late':>6}{'solo':>6}{'burst+dec':>10}{'early sub':>10}{'dec ovl':>8}{'other':>6}{'mean ovl ms':>12}{'solo-late-ok':>13}  touched frames, slowdown p50/p99")
    f1 = lambda v: "n/a" if v is None else f"{v:.2f}"
    for lvl in LEVELS:
        for arm in ARMS[1:]:
            c = causes.get((lvl, arm))
            if c:
                s, tc = slow[(lvl, arm)], touched[(lvl, arm)]
                print(f"{lvl:<11}{arm:<11}{c['frames']:>7}{c['late']:>6}{c['solo']:>6}{c['burst']:>10}{c['early']:>10}{c['overlap']:>8}{c['other']:>6}{f1(float(np.mean(c['ovl'])) if c['ovl'] else None):>12}{c['solo_late_ok']:>13}  "
                      f"{tc[0]} ({100 * tc[0] / tc[1]:.1f}%), {f1(JA.pct(s, 50))}/{f1(JA.pct(s, 99))}")
    pts = {}
    if sprint3:
        s3 = Path(sprint3)
        solo_med = st.median(float(np.median(JA.load(c)[1]["dur_ms"])) for c in sorted(s3.glob("moderate_solo_rep*")))
        for arm, key in (("3b_whole", "moderate|3b_whole"), ("3b_g14_m0", "moderate|3b_g14"), ("8b_g14_m0", "moderate|8b_g14")):
            tok = st.median(json.loads((c / "result.json").read_text())["bg_tok_s"] for c in sorted(s3.glob(f"moderate_{key.split('|')[1]}_rep*")))
            pts[arm] = dict(free=PERIOD_MS - solo_med, tok=tok)
        print("sprint-3 moderate points (free ms, tok/s):", {k: (round(v["free"], 2), round(v["tok"], 1)) for k, v in pts.items()})
    summary = dict(table={f"{k[0]}|{k[1]}": v for k, v in table.items()}, verdict=verdict, fail=fail, sprint3_points=pts,
                   causes={f"{k[0]}|{k[1]}": {kk: (vv if kk != "ovl" else [float(np.mean(vv)) if vv else None, len(vv)]) for kk, vv in v.items()} for k, v in causes.items()},
                   slowdown={f"{k[0]}|{k[1]}": dict(p50=JA.pct(v, 50), p99=JA.pct(v, 99), n=len(v), touched_share=touched[k][0] / touched[k][1]) for k, v in slow.items()})
    (d / "summary.json").write_text(json.dumps(summary, indent=1, default=str), encoding="utf-8")
    plot(table, pts, ROOT / "data" / "v2" / "s4_low_slack.png")


def plot(table, pts, out):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(1, 2, figsize=(12, 4.2))
    style = {"3b_whole": ("#8b949e", "o", "3B whole token"), "3b_g14_m0": ("#1f6feb", "s", "3B 14 groups, margin 0"), "3b_g14_m1": ("#0a3069", "D", "3B 14 groups, margin 1.0"),
             "8b_g14_m1": ("#bf8700", "^", "8B 14 groups, margin 1.0"), "8b_g28_m1": ("#8a4600", "v", "8B 28 groups, margin 1.0"), "8b_g14_m0": ("#e3b341", "^", "8B 14 groups, margin 0 (sprint 3)")}
    for arm, (c, m, lab) in style.items():
        pt = []
        for lvl in LEVELS:
            t = table.get((lvl, arm))
            if t:
                pt.append((PERIOD_MS - t["solo_med_ms"], t["tok"], t["excess"]))
        if arm in pts:
            pt.append((pts[arm]["free"], pts[arm]["tok"], None))
        pt.sort()
        ax[0].plot([p[0] for p in pt], [p[1] for p in pt], m + "-", color=c, label=lab)
        pe = [(p[0], p[2]) for p in pt if p[2] is not None]
        if pe:
            ax[1].plot([p[0] for p in pe], [p[1] for p in pe], m + "-", color=c, label=lab)
    ax[0].set_xlabel("free time per frame (ms) = 16.67 - SOLO median frame time"); ax[0].set_ylabel("background tok/s"); ax[0].set_title("Throughput against free time per frame (sprint 3 moderate points at about 9.6 ms)", fontsize=9)
    ax[0].invert_xaxis(); ax[0].legend(fontsize=7)
    ax[1].set_xlabel("free time per frame (ms)"); ax[1].set_ylabel("excess late frames over SOLO (pp)"); ax[1].set_title("Excess late frames against free time per frame", fontsize=9); ax[1].invert_xaxis(); ax[1].axhline(0, color="k", lw=0.5)
    fig.tight_layout()
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=140)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("dir")
    ap.add_argument("--sprint3", default=None)
    a = ap.parse_args()
    main(a.dir, a.sprint3)
