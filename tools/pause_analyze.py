"""v2 sprint 1 analysis (docs/V2_SPRINT1_PAUSE_COST.md): from the raw CSVs of tools/pause_bench.py --run to the forecast-vs-measured table, the decision-rule verdict and the plot.
   python tools/pause_analyze.py data/v2/s1_pause/<stamp>
Per configuration (warm-up tokens dropped, reps pooled by token): median total ms per token, overhead against G1 in % (median of the three per-rep medians), per group median GPU ms
(CUDA events), the host gap between groups (next launch minus previous completion, which contains the launch and the hint check), the longest group per token (median and p99), and the
measured per-boundary overhead in microseconds = (total(G) - total(G1)) / (G - 1). Writes summary.json beside the data and data/v2/s1_pause_cost.png."""
import csv
import json
import re
import statistics as st
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FORECAST = {1: (0.0, 10.3), 2: (1.0, 5.4), 4: (2.9, 3.1), 7: (5.8, 2.1), 14: (12.6, 1.5), 28: (26.3, 1.1)}      # (slowdown %, longest group ms), committed in docs/V2_SPRINT1_PAUSE_COST.md before measuring
GO_MAX_GROUP_MS, GO_MAX_OVERHEAD, MARGINAL_MAX_OVERHEAD = 2.5, 15.0, 30.0


def plain_g(name):
    m = re.fullmatch(r"G(\d+)", name)
    return int(m.group(1)) if m else None


def read(p):
    with open(p, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def pct(vals, q):
    s = sorted(vals)
    x = (len(s) - 1) * q / 100.0
    lo = int(x)
    hi = min(lo + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (x - lo)


def analyse(d):
    d = Path(d)
    meta = json.loads((d / "meta.json").read_text())
    reps = meta["reps"]
    res = {}
    for name in meta["configs"]:
        per_rep_med, totals, tok_ids, gmax, gdur, gaps, hint = [], [], [], [], {}, [], []
        for rep in range(1, reps + 1):
            toks = [r for r in read(d / f"{name}_rep{rep}_tokens.csv") if r["warm"] == "0"]
            t = [float(r["total_ms"]) for r in toks]
            per_rep_med.append(st.median(t))
            totals += t
            tok_ids.append([r["token_id"] for r in toks])
            gp = d / f"{name}_rep{rep}_groups.csv"
            rows = read(gp) if gp.exists() else []
            keep = {r["token"] for r in toks}
            by_tok = {}
            for r in rows:
                if r["token"] in keep:
                    by_tok.setdefault(r["token"], []).append(r)
            for tk, rs in by_tok.items():
                rs.sort(key=lambda r: int(r["group"]))
                durs = [float(r["gpu_ms"]) for r in rs]
                gmax.append(max(durs))
                for r in rs:
                    gdur.setdefault(int(r["group"]), []).append(float(r["gpu_ms"]))
                    hint.append(float(r["hint_check_us"]))
                for a, b in zip(rs, rs[1:]):
                    gaps.append((float(b["t_launch_s"]) - float(a["t_done_s"])) * 1e6)
        res[name] = dict(median_total_ms=st.median(totals), p99_total_ms=pct(totals, 99), rep_medians_ms=per_rep_med, n_tokens=len(totals),
                         token_ids_identical_across_reps=all(x == tok_ids[0] for x in tok_ids), longest_group_ms_median=st.median(gmax) if gmax else None,
                         longest_group_ms_p99=pct(gmax, 99) if gmax else None, group_gpu_ms_median={g: st.median(v) for g, v in sorted(gdur.items())},
                         gap_us_median=st.median(gaps) if gaps else None, gap_us_p99=pct(gaps, 99) if gaps else None, hint_check_us_median=st.median(hint) if hint else None)
    base = res["G1"]["median_total_ms"]
    base_reps = res["G1"]["rep_medians_ms"]
    bm = st.median(base_reps)
    for name, r in res.items():
        r["overhead_pct"] = 100.0 * (r["median_total_ms"] - base) / base
        r["overhead_pct_range_over_reps"] = [100.0 * (min(r["rep_medians_ms"]) - bm) / bm, 100.0 * (max(r["rep_medians_ms"]) - bm) / bm]
        g = plain_g(name)
        r["per_boundary_us"] = 1000.0 * (r["median_total_ms"] - base) / (g - 1) if g and g > 1 else None
        fm = re.fullmatch(r"G(\d+)_pause2ms", name)
        if fm:                                           # control: a forced 2 ms pause per boundary must raise the token time by about 2 ms x (G - 1) over the same G without it
            gg = int(fm.group(1))
            r["forced_pause_expected_rise_ms"] = 2.0 * (gg - 1)
            r["forced_pause_measured_rise_ms"] = r["median_total_ms"] - res[f"G{gg}"]["median_total_ms"]
        if g in FORECAST:
            r["forecast_overhead_pct"], r["forecast_longest_group_ms"] = FORECAST[g]
        if g == 1:
            r["longest_group_ms_median"] = r["median_total_ms"]          # one uninterruptible piece: the whole token
    return meta, res


def verdict(res):
    cand = [(plain_g(n), r) for n, r in res.items() if plain_g(n) and r["longest_group_ms_median"] is not None and r["longest_group_ms_median"] <= GO_MAX_GROUP_MS]
    if not cand:
        return "STOP", "no G brings the longest group (median per token) to 2.5 ms or below"
    g, r = min(cand, key=lambda c: c[1]["overhead_pct"])
    o = r["overhead_pct"]
    rule = "GO" if o <= GO_MAX_OVERHEAD else ("MARGINAL" if o <= MARGINAL_MAX_OVERHEAD else "STOP")
    return rule, f"the best G meeting the 2.5 ms group limit is G = {g} (longest group {r['longest_group_ms_median']:.2f} ms) with a per-token overhead of {o:.1f}% against G = 1"


def plot(res, out):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    gs = sorted(plain_g(n) for n in res if plain_g(n))
    fig, ax = plt.subplots(figsize=(7.2, 4.2))
    ax.plot(gs, [res[f"G{g}"]["overhead_pct"] for g in gs], "o-", color="#1f6feb", label="measured overhead vs G = 1 (%)")
    ax.plot([g for g in gs if g in FORECAST], [FORECAST[g][0] for g in gs if g in FORECAST], "s--", color="#8b949e", label="forecast overhead (%)")
    ax.axhline(15, color="#cf222e", lw=0.8, ls=":")
    ax.set_xscale("log", base=2)
    ax.set_xticks(gs)
    ax.set_xticklabels([str(g) for g in gs])
    ax.set_xlabel("groups per token, G")
    ax.set_ylabel("per-token overhead against G = 1 (%)")
    ax2 = ax.twinx()
    ax2.plot(gs, [res[f"G{g}"]["longest_group_ms_median"] for g in gs], "^-", color="#bf8700", label="longest group, median (ms)")
    ax2.axhline(2.5, color="#bf8700", lw=0.8, ls=":")
    ax2.set_ylabel("longest uninterruptible piece (ms)")
    h1, l1 = ax.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax.legend(h1 + h2, l1 + l2, loc="upper center", fontsize=8)
    ax.set_title("Pause cost of layer-group decode, 3B at 1500 MHz (dotted: 15% and 2.5 ms limits)", fontsize=9)
    fig.tight_layout()
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=140)


def main(d):
    meta, res = analyse(d)
    rule, why = verdict(res)
    print(f"{'config':<11}{'tok ms':>8}{'ovh %':>8}{'fcst %':>8}{'longest ms':>12}{'fcst ms':>9}{'gap us':>9}{'us/boundary':>13}")
    nan = float("nan")
    for n, r in res.items():
        print(f"{n:<11}{r['median_total_ms']:>8.2f}{r['overhead_pct']:>8.1f}{r.get('forecast_overhead_pct', nan):>8.1f}{(r['longest_group_ms_median'] or nan):>12.2f}"
              f"{r.get('forecast_longest_group_ms', nan):>9.1f}{(r['gap_us_median'] or nan):>9.0f}{(r['per_boundary_us'] or nan):>13.0f}")
    print("token ids identical across reps:", {n: r["token_ids_identical_across_reps"] for n, r in res.items()})
    for n, r in res.items():
        if "forced_pause_expected_rise_ms" in r:
            print(f"forced-pause control {n}: token time rose {r['forced_pause_measured_rise_ms']:.2f} ms, expected about {r['forced_pause_expected_rise_ms']:.1f} ms (2 ms x (G - 1))")
    print("VERDICT:", rule, "-", why)
    (Path(d) / "summary.json").write_text(json.dumps(dict(meta=meta, results=res, verdict=rule, why=why), indent=1, default=str), encoding="utf-8")
    plot(res, ROOT / "data" / "v2" / "s1_pause_cost.png")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
