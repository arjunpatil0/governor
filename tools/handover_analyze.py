"""v2 sprint 2 analysis (docs/V2_SPRINT2_HANDOVER.md).
   python tools/handover_analyze.py --readback <dir> --exp1 <dir> --exp2 <sprint-1-style sweep dir for the 8B> --exp3 <dir>
Exp 1: per configuration and decode state at the moment of the foreground's submit (mid-group = inside a decode group interval, between = not), p50/p99/max of the first-kernel delay in ms. The delay is
the marker kernel's %globaltimer start mapped to QPC with a linear offset between two idle calibrations (the GPU timer drifts about 70 us per second against QPC) minus the host time just before the launch;
an idle round trip is under 10 us, so everything above that is contention. Exp 3: per scene and gate, per-rep values and the median over reps of tok/s, late-frame %, power (energy counter), J/token,
power_rejected, and the decision rule (WIN / NEUTRAL / LOSS; 'within noise' = the median difference is smaller than the larger rep-to-rep range of the two arms). Writes data/v2/s2/summary.json and the plot."""
import argparse
import csv
import json
import statistics as st
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))


def delays_ms(cell):
    m = np.load(Path(cell) / "marker.npz")
    s = m["samples"]
    off = float(m["off0"]) + (float(m["off1"]) - float(m["off0"])) * (s[:, 0] - float(m["q0"])) / (float(m["q1"]) - float(m["q0"]))
    return s[:, 0], (s[:, 1] - off - s[:, 0]) * 1e3


def intervals(cell):
    rows = list(csv.DictReader(open(Path(cell) / "decode_groups.csv")))
    a = np.array([(float(r["t_launch_s"]), float(r["t_done_s"])) for r in rows])
    return a[np.argsort(a[:, 0])]


def classify(t_submit, iv):
    """True where the submit time falls inside a decode group interval (mid-group)."""
    idx = np.searchsorted(iv[:, 0], t_submit, side="right") - 1
    ok = idx >= 0
    inside = np.zeros(len(t_submit), bool)
    inside[ok] = t_submit[ok] <= iv[idx[ok], 1]
    return inside


def pct(x, q):
    return float(np.percentile(x, q)) if len(x) else None


def exp1(d):
    d = Path(d)
    res = {}
    for name in ("G1_free", "G14_free", "G1_gate", "G14_gate"):
        t_all, d_all, mid_all = [], [], []
        late, tok = [], []
        for cell in sorted(d.glob(f"{name}_rep*")):
            t, dl = delays_ms(cell)
            keep = t >= json.loads((cell / "result.json").read_text())["t0"] + 5.0           # measured window only (after the 5 s warm-up)
            t, dl = t[keep], dl[keep]
            mid = classify(t, intervals(cell))
            t_all.append(t); d_all.append(dl); mid_all.append(mid)
            r = json.loads((cell / "result.json").read_text())
            late.append(100 * r["miss_frac"]); tok.append(r["bg_tok_s"])
        dl, mid = np.concatenate(d_all), np.concatenate(mid_all)
        res[name] = dict(n=int(len(dl)), frac_mid_group=float(mid.mean()), all=dict(p50=pct(dl, 50), p99=pct(dl, 99), max=float(dl.max())),
                         mid_group=dict(n=int(mid.sum()), p50=pct(dl[mid], 50), p99=pct(dl[mid], 99), max=float(dl[mid].max()) if mid.any() else None),
                         between=dict(n=int((~mid).sum()), p50=pct(dl[~mid], 50), p99=pct(dl[~mid], 99), max=float(dl[~mid].max()) if (~mid).any() else None),
                         late_pct_median=st.median(late), tok_s_median=st.median(tok))
    return res


def rule(a, b):
    """Decision rule of the doc for one scene. a = whole-token arm, b = 14-group arm; each a dict of per-rep lists."""
    la, lb, ta, tb = st.median(a["late"]), st.median(b["late"]), st.median(a["tok"]), st.median(b["tok"])
    noise_l = max(max(a["late"]) - min(a["late"]), max(b["late"]) - min(b["late"]))
    noise_t = max(max(a["tok"]) - min(a["tok"]), max(b["tok"]) - min(b["tok"]))
    late_better, late_worse = lb < la - noise_l, lb > la + noise_l
    tok_better, tok_worse = tb > ta + noise_t, tb < ta - noise_t
    if (late_better and not tok_worse) or (tok_better and not late_worse):
        v = "WIN"
    elif late_worse and tok_worse:
        v = "LOSS"
    elif not (late_better or late_worse or tok_better or tok_worse):
        v = "NEUTRAL"
    else:
        v = "MIXED (one better and one worse beyond noise; the owner decides)"
    return v, dict(late_a=la, late_b=lb, tok_a=ta, tok_b=tb, noise_late_pct=noise_l, noise_tok_s=noise_t)


def per_frame(cell):
    """Per frame of the measured window: frame duration (t_end - t_start, ms), the decode time overlapping the frame (ms, from the decode group intervals, a host-side proxy for GPU activity that
    includes launch and sync latency), and the slowdown against the solo duration. The solo duration per unit of nominal frame cost is the median of duration / cost over the frames of the same cell
    that no decode interval touched; if no frame is overlap-free the slowdown is None. Returns dict of arrays."""
    cell = Path(cell)
    f = np.load(cell / "frames.npz")
    t0 = json.loads((cell / "result.json").read_text())["t0"]
    keep = f["t_sched"] >= t0 + 5.0
    ts, te, cost = f["t_start"][keep], f["t_end"][keep], f["cost_ms"][keep]
    dur = (te - ts) * 1e3
    iv = intervals(cell)
    ov = np.zeros(len(ts))
    j = 0
    for i in range(len(ts)):
        lo = np.searchsorted(iv[:, 1], ts[i], side="left")        # first interval that ends after the frame starts
        k = lo
        while k < len(iv) and iv[k, 0] < te[i]:
            ov[i] += max(0.0, min(te[i], iv[k, 1]) - max(ts[i], iv[k, 0]))
            k += 1
    ov *= 1e3
    free = ov <= 1e-6
    solo = float(np.median(dur[free] / cost[free])) if free.sum() >= 5 else None
    slow = dur / (solo * cost) if solo else None
    return dict(dur_ms=dur, overlap_ms=ov, cost_ms=cost, solo_ratio=solo, slowdown=slow, late=(f["lat_ms"][keep] > 1000.0 / 60.0))


def frame_summary(cells):
    """Pool the frames of the reps of one arm: fraction of frames touched by decode, mean overlap per frame, slowdown of overlapped frames (median, p99), late share of overlapped / untouched frames."""
    pf = [per_frame(c) for c in cells]
    ov = np.concatenate([p["overlap_ms"] for p in pf])
    late = np.concatenate([p["late"] for p in pf])
    slow = np.concatenate([p["slowdown"] for p in pf if p["slowdown"] is not None]) if any(p["slowdown"] is not None for p in pf) else np.array([])
    touched = ov > 1e-6
    sl_t = np.concatenate([p["slowdown"][p["overlap_ms"] > 1e-6] for p in pf if p["slowdown"] is not None]) if len(slow) else np.array([])
    return dict(frames=int(len(ov)), frac_touched=float(touched.mean()), overlap_ms_mean_all=float(ov.mean()), overlap_ms_mean_touched=float(ov[touched].mean()) if touched.any() else 0.0,
                overlap_ms_max=float(ov.max()), slowdown_touched_p50=pct(sl_t, 50), slowdown_touched_p99=pct(sl_t, 99), solo_ratio_median=st.median([p["solo_ratio"] for p in pf if p["solo_ratio"]]) if any(p["solo_ratio"] for p in pf) else None,
                late_share_touched=float(late[touched].mean()) if touched.any() else None, late_share_untouched=float(late[~touched].mean()) if (~touched).any() else None, late_frames=int(late.sum()),
                late_frames_touched=int((late & touched).sum()))


def exp3(d):
    d = Path(d)
    out, verdicts = {}, {}
    for scene in ("S1", "S5"):
        arms = {}
        for name in ("whole", "g14"):
            rows = [json.loads((c / "result.json").read_text()) for c in sorted(d.glob(f"{scene}_{name}_rep*"))]
            arms[name] = dict(tok=[r["bg_tok_s"] for r in rows], late=[100 * r["miss_frac"] for r in rows], power=[r["power_w"] for r in rows], jpt=[r["j_per_token"] for r in rows],
                              rejected=[r["power_rejected"] for r in rows], sm=[r["sm_mhz_median"] for r in rows], p99=[r["fg_p99_ms"] for r in rows], wait=[st.median(
                                  [float(x["gate_wait_ms"]) for x in csv.DictReader(open(c / "decode_tokens.csv"))]) for c in sorted(d.glob(f"{scene}_{name}_rep*"))])
        for name in ("whole", "g14"):
            arms[name]["frames"] = frame_summary(sorted(d.glob(f"{scene}_{name}_rep*")))
        out[scene] = arms
        verdicts[scene] = rule(arms["whole"], arms["g14"])
    return out, verdicts


def exp2(d):
    import pause_analyze as PA
    meta, res = PA.analyse(d)
    return {n: dict(token_ms=r["median_total_ms"], overhead_pct=r["overhead_pct"], longest_group_ms=r["longest_group_ms_median"], longest_group_p99_ms=r["longest_group_ms_p99"],
                    group_gpu_ms={k: v for k, v in r["group_gpu_ms_median"].items()}) for n, r in res.items()}


def plot(e1, e3, out):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(1, 3, figsize=(13, 4))
    names = ["G1_free", "G14_free", "G1_gate", "G14_gate"]
    x = np.arange(len(names))
    for k, (cls, c) in enumerate((("all", "#1f6feb"), ("mid_group", "#bf8700"), ("between", "#2da44e"))):
        p50 = [e1[n][cls]["p50"] or 0 for n in names]
        p99 = [e1[n][cls]["p99"] or 0 for n in names]
        ax[0].bar(x + (k - 1) * 0.27, p99, 0.25, color=c, alpha=0.35)
        ax[0].bar(x + (k - 1) * 0.27, p50, 0.25, color=c, label=cls.replace("_", "-"))
    ax[0].set_xticks(x); ax[0].set_xticklabels(names, rotation=15, fontsize=8)
    ax[0].set_ylabel("first-kernel delay (ms): dark p50, light p99"); ax[0].legend(fontsize=8); ax[0].set_title("Handover latency of the foreground", fontsize=9)
    for j, (key, lab) in enumerate((("tok", "background tok/s"), ("late", "late frames (%)"))):
        a = ax[j + 1]
        for k, scene in enumerate(("S1", "S5")):
            for i, (arm, c) in enumerate((("whole", "#8b949e"), ("g14", "#1f6feb"))):
                v = e3[scene][arm][key]
                a.bar(k + (i - 0.5) * 0.35, st.median(v), 0.33, color=c, label=("whole-token gate" if arm == "whole" else "14-group gate") if k == 0 else None)
                a.plot([k + (i - 0.5) * 0.35] * len(v), v, "k.", ms=4)
        a.set_xticks([0, 1]); a.set_xticklabels(["S1 (3B)", "S5 (8B)"]); a.set_ylabel(lab); a.set_title(lab + ", median and reps", fontsize=9)
        if j == 0:
            a.legend(fontsize=8)
        else:
            a.set_ylim(0, 1.0)                                       # late frames: every cell is 0.00%, so a 0 to 1% axis (the 1% limit of the evaluation) rather than an auto-scaled hairline
    fig.tight_layout()
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=140)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--readback"); ap.add_argument("--exp1", required=True); ap.add_argument("--exp2"); ap.add_argument("--exp3", required=True)
    a = ap.parse_args()
    summary = {}
    if a.readback:
        summary["readback"] = json.loads((Path(a.readback) / "result.json").read_text()); print("readback:", json.dumps(summary["readback"]))
    e1 = exp1(a.exp1); summary["exp1"] = e1
    print("EXP1 handover latency (ms)")
    print(f"{'config':<10}{'frac mid':>9}  {'all p50/p99':>14}  {'mid-group n,p50/p99/max':>26}  {'between n,p50/p99/max':>26}")
    f = lambda v: "n/a" if v is None else f"{v:.3f}"
    for n, r in e1.items():
        print(f"{n:<10}{r['frac_mid_group']:>9.2f}  {f(r['all']['p50'])+'/'+f(r['all']['p99']):>14}  {str(r['mid_group']['n'])+', '+f(r['mid_group']['p50'])+'/'+f(r['mid_group']['p99'])+'/'+f(r['mid_group']['max']):>26}  "
              f"{str(r['between']['n'])+', '+f(r['between']['p50'])+'/'+f(r['between']['p99'])+'/'+f(r['between']['max']):>26}")
    if a.exp2:
        summary["exp2"] = exp2(a.exp2); print("EXP2 8B:", {n: (round(v['token_ms'], 2), round(v['overhead_pct'], 1), None if v['longest_group_ms'] is None else round(v['longest_group_ms'], 2)) for n, v in summary["exp2"].items()})
    e3, verdicts = exp3(a.exp3); summary["exp3"] = e3; summary["exp3_verdicts"] = {k: [v[0], v[1]] for k, v in verdicts.items()}
    print("EXP3 end to end (median over reps; reps in brackets)")
    for scene in ("S1", "S5"):
        for arm in ("whole", "g14"):
            r = e3[scene][arm]
            print(f"{scene} {arm:<6} tok/s {st.median(r['tok']):6.1f} {[round(x, 1) for x in r['tok']]}  late {st.median(r['late']):6.2f}% {[round(x, 2) for x in r['late']]}  power {st.median(r['power']):5.1f} W  J/tok {st.median(r['jpt']):5.2f}  "
                  f"rejected {sum(r['rejected'])}  sm {st.median(r['sm']):.0f} MHz  p99 {st.median(r['p99']):.1f} ms")
        for arm in ("whole", "g14"):
            fr = e3[scene][arm]["frames"]
            g = lambda v, nd=2: "n/a" if v is None else f"{v:.{nd}f}"
            print(f"   {scene} {arm:<6} frames {fr['frames']}  touched by decode {100 * fr['frac_touched']:.1f}%  overlap per frame: mean {fr['overlap_ms_mean_all']:.2f} ms (touched {fr['overlap_ms_mean_touched']:.2f}, max {fr['overlap_ms_max']:.2f})  "
                  f"slowdown of touched frames p50 {g(fr['slowdown_touched_p50'])} p99 {g(fr['slowdown_touched_p99'])}  late frames {fr['late_frames']} (touched {fr['late_frames_touched']})")
        print(f"   rule for {scene}: {verdicts[scene][0]}  {json.dumps({k: round(v, 3) for k, v in verdicts[scene][1].items()})}")
    (ROOT / "data" / "v2" / "s2" / "summary.json").write_text(json.dumps(summary, indent=1, default=str), encoding="utf-8")
    plot(e1, e3, ROOT / "data" / "v2" / "s2_handover.png")


if __name__ == "__main__":
    main()
