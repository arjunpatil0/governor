#!/usr/bin/env python3
"""W2 analysis: the pre-registered decision rules of experiments/w2_colocation.yaml, as tested functions (tests/test_w2_analysis.py),
plus a command-line driver (see main) that reads a run's results.csv and per-cell logs and writes data/w2_<part>_results.md.
Seeds for every bootstrap are fixed (SEED); multiplicity is Holm within each family named in the yaml."""
import numpy as np
import pandas as pd
from scipy.stats import wilcoxon

from w2_stats import bootstrap_median_ci, equivalence_slope, find_knee, ols_block_bootstrap

SEED = 20261021
ALPHA = 0.05
UNLOCKED_KEY = 10_000          # 'unlocked' sorts above every locked level when comparing knees
HB_TEST_LEVELS = (900, 1200, 1500)   # HB1/HB2 families; the descriptive 1050 MHz level of the B-levels addendum is outside them


def holm(pvals):
    p = np.asarray(pvals, float); order = np.argsort(p); m = len(p); adj = np.empty(m); run = 0.0
    for rank, i in enumerate(order):
        run = max(run, (m - rank) * p[i]); adj[i] = min(1.0, run)
    return adj


def _wilcoxon_greater(d):
    d = np.asarray(d, float)
    if np.all(d == 0):
        return 1.0
    return float(wilcoxon(d, alternative="greater", zero_method="wilcox").pvalue)


# ---- HA1 / HA2 (Experiment A) ---------------------------------------------------------------------------------------
def ha1(cells):
    """cells: block, cell_id, m_ms, cv, pred_ms, obs_ms (obs = mean latency - block baseline mean latency). Supported iff the slope
    equivalence test (OLS WITH intercept, 90% block-bootstrap CI inside [0.8, 1.25]) holds AND >= 70% of cell medians are within +/-25%."""
    r = equivalence_slope(cells.pred_ms, cells.obs_ms, cells.block, seed=SEED)
    med = cells.groupby("cell_id")[["obs_ms", "pred_ms"]].median()
    frac = float(((med.obs_ms - med.pred_ms).abs() <= 0.25 * med.pred_ms).mean())
    r.update(frac_within25=frac, n_cells=int(len(med)), supported=bool(r["equivalent"] and frac >= 0.7))
    return r


def classify_ha1(cells, res):
    """Registered order: preempted_or_concurrent, then scheduler_capped, else other."""
    if res["supported"]:
        return "supported"
    med = cells.groupby(["cell_id", "m_ms", "cv"])[["obs_ms", "pred_ms"]].median().reset_index()
    big = med[med.m_ms >= 2]
    if res["ci_hi"] < 0.8 and float((big.obs_ms / big.pred_ms).median()) < 0.5:
        return "preempted_or_concurrent"
    c0 = med[med.cv == 0].set_index("m_ms")
    if c0.loc[8, "obs_ms"] <= 1.25 * c0.loc[2, "obs_ms"] and c0.loc[8, "pred_ms"] / c0.loc[2, "pred_ms"] >= 3:
        return "scheduler_capped"
    return "other"


def ha2(cells):
    """At each m: one-sided paired Wilcoxon obs(c=1) > obs(c=0) over blocks; Holm over m; supported iff >= 4 of the m values."""
    rows = []
    for m, g in cells.groupby("m_ms"):
        w = g.pivot_table(index="block", columns="cv", values="obs_ms")
        rows.append(dict(m_ms=m, n=len(w), median_diff=float((w[1.0] - w[0.0]).median()), p=_wilcoxon_greater(w[1.0] - w[0.0])))
    t = pd.DataFrame(rows)
    t["p_holm"] = holm(t.p); t["significant"] = t.p_holm < ALPHA
    n = int(t.significant.sum())
    return dict(table=t, n_sig=n, supported=n >= 4)


# ---- SA1 ------------------------------------------------------------------------------------------------------------
def sa1_label(phase_ms, latency_ms, blocks):
    """Slope of fg latency on arrival phase within the slice (ms per ms): -1 = waits out the slice, 0 = phase independent."""
    r = ols_block_bootstrap(phase_ms, latency_ms, blocks, seed=SEED)
    lo, hi = r["ci_lo"], r["ci_hi"]
    label = "phase-independent" if (-0.25 <= lo and hi <= 0.25) else "waits-out-the-slice" if (-1.25 <= lo and hi <= -0.8) else "mixed"
    return dict(label=label, slope=r["slope"], ci_lo=lo, ci_hi=hi)


# ---- HB1 / HB2 (Experiment B) ---------------------------------------------------------------------------------------
def hb1(df, rel_w1):
    """df: block, frame, kind ('fma'|'mem'), level, service_ms (bg off). Ratio service(L)/service(1800) per block vs rel_W1(1800)/rel_W1(L);
    ok iff the 90% bootstrap CI of the median ratio lies within +/-10% (fma) or +/-5% (mem) of the prediction. Supported iff every
    fma frame is ok at L in {900, 1200, 1500}."""
    rows = []
    for (frame, kind), g in df.groupby(["frame", "kind"]):
        ref = g[g.level == 1800].set_index("block").service_ms
        for L in HB_TEST_LEVELS:
            s = g[g.level == L].set_index("block").service_ms
            ratio = (s / ref).dropna().to_numpy()
            lo, hi = bootstrap_median_ci(ratio, seed=SEED)
            pred = rel_w1[kind][1800] / rel_w1[kind][L]
            tol = 0.10 if kind == "fma" else 0.05
            rows.append(dict(frame=frame, kind=kind, level=L, ratio_median=float(np.median(ratio)), ci_lo=lo, ci_hi=hi, pred=pred,
                             tol=tol, ok=bool(pred * (1 - tol) <= lo and hi <= pred * (1 + tol))))
    t = pd.DataFrame(rows)
    return dict(table=t, supported=bool(t[t.kind == "fma"].ok.all()))


def hb2(df, budget_ms, pred_ratio):
    """df: block, level, miss_frac, service_ms for one frame kind / background condition. One-sided paired Wilcoxon miss(L) > miss(1800)
    for L in pred_ratio, Holm over those levels. Supported iff significant at every level whose predicted service (median measured
    service at 1800 x HB1 ratio) exceeds the frame budget."""
    ref = df[df.level == 1800].set_index("block")
    levels = sorted(pred_ratio)
    ps = [_wilcoxon_greater((df[df.level == L].set_index("block").miss_frac - ref.miss_frac).dropna()) for L in levels]
    adj = holm(ps)
    svc1800 = float(ref.service_ms.median())
    must = [L for L in levels if svc1800 * pred_ratio[L] > budget_ms]
    sig = {L: bool(a < ALPHA) for L, a in zip(levels, adj)}
    return dict(table=pd.DataFrame(dict(level=levels, p=ps, p_holm=adj, significant=[sig[L] for L in levels])),
                must_be_significant=must, supported=bool(must) and all(sig[L] for L in must),
                reference_at_ceiling=bool(ref.miss_frac.median() >= 0.99))


def interp_service_ratio(rel_w1, kind, level):
    """Descriptive only (never tested): W1 service-time ratio to 1800 MHz at a level W1 did not measure, by linear interpolation of
    W1's relative throughput between its neighbouring levels."""
    lv = sorted(rel_w1[kind]); lo = max(x for x in lv if x <= level); hi = min(x for x in lv if x >= level)
    rel = rel_w1[kind][lo] if lo == hi else rel_w1[kind][lo] + (level - lo) / (hi - lo) * (rel_w1[kind][hi] - rel_w1[kind][lo])
    return rel_w1[kind][1800] / rel


# ---- HC1 / knees (Experiment C) -------------------------------------------------------------------------------------
def _lvl(x):
    return UNLOCKED_KEY if x == "unlocked" else int(x)


def block_knees(df):
    """Per-block knee level for each variant (graph launch mode): lowest level with relative throughput >= 0.95."""
    g = df[df.graph]
    rows = {}
    for (b, variant), d in g.groupby(["block", "variant"]):
        k = find_knee({_lvl(l): v for l, v in zip(d.level, d.rel_thr)})
        rows.setdefault(b, {})[variant] = UNLOCKED_KEY if k is None else k
    return pd.DataFrame.from_dict(rows, orient="index").sort_index()


def hc1(df):
    """df: block, variant ('int4'|'fp16'), graph, level, rel_thr (vs the same block's unlocked cell). One-sided paired Wilcoxon
    (int4 knee > fp16 knee, zero_method='wilcox'); INCONCLUSIVE if fewer than 6 blocks have a nonzero difference."""
    kt = block_knees(df)
    d = (kt["int4"] - kt["fp16"]).to_numpy(float)
    nz = int((d != 0).sum())
    if nz < 6:
        return dict(knee_table=kt, n_nonzero=nz, status="inconclusive", p=None)
    p = _wilcoxon_greater(d)
    return dict(knee_table=kt, n_nonzero=nz, status="supported" if p < ALPHA else "not supported", p=p)


# ---- glue: results.csv -> inputs of the decision functions -----------------------------------------------------------
import json  # noqa: E402


def _specs(df):
    return df["spec"].map(json.loads)


def a_cells(df, priority="normal", baseline_df=None):
    """Main-grid background cells (duty 1, given fg priority) with obs = mean latency - the same block's baseline cell mean latency."""
    s = _specs(df)
    base_src = df if baseline_df is None else baseline_df
    base = base_src[base_src.cell_id == "baseline"].set_index("block").lat_mean_ms
    keep = (df.cell_id.str.startswith("bg_fma_") | df.cell_id.str.startswith("sa3_high_")) & s.map(lambda x: x["fg"]["priority"] == priority) \
        & s.map(lambda x: x["bg"] is not None and x["bg"]["duty"] == 1.0)
    d = df[keep].copy(); sk = s[keep]
    d["m_ms"] = sk.map(lambda x: x["bg"]["m_ms"]); d["cv"] = sk.map(lambda x: x["bg"]["cv"])
    d["obs_ms"] = d.lat_mean_ms - d.block.map(base); d["pred_ms"] = d.predicted_wait_ms
    return d[["block", "cell_id", "m_ms", "cv", "obs_ms", "pred_ms"]].reset_index(drop=True)


def _level(x):
    return x if x == "unlocked" else int(x)


def b_service_tables(df):
    """hb1: background-off cells at locked levels (block, frame, kind, level, service_ms). hb2_*: per background condition
    (block, frame, level, miss_frac, service_ms) for the locked levels."""
    s = _specs(df)
    d = pd.DataFrame(dict(block=df.block, frame=s.map(lambda x: x["fg"]["frame"]), kind=s.map(lambda x: x["fg"]["kind"]),
                          level=df.sm_mhz.map(_level), bg=s.map(lambda x: x["bg"] is not None),
                          service_ms=df.fg_gpu_p50_ms, miss_frac=df.miss_frac))
    d = d[d.level != "unlocked"].copy(); d["level"] = d.level.astype(int)
    nobg, membg = d[~d.bg], d[d.bg]
    return dict(hb1=nobg[["block", "frame", "kind", "level", "service_ms"]].reset_index(drop=True),
                hb2_nobg=nobg[["block", "frame", "kind", "level", "miss_frac", "service_ms"]].reset_index(drop=True),
                hb2_membg=membg[["block", "frame", "kind", "level", "miss_frac", "service_ms"]].reset_index(drop=True))


def c_rel_thr(df):
    """Relative throughput (tokens/s) vs the same block's unlocked cell of the same variant / launch mode."""
    s = _specs(df)
    d = pd.DataFrame(dict(block=df.block, variant=s.map(lambda x: x["decode"]["variant"]), graph=s.map(lambda x: bool(x["decode"]["graph"])),
                          level=df.sm_mhz.map(_level), tok_s=df.tok_s, energy_j=df.energy_j, tokens=df.tokens))
    ref = d[d.level == "unlocked"].set_index(["block", "variant", "graph"]).tok_s
    d["rel_thr"] = d.tok_s.values / d.set_index(["block", "variant", "graph"]).index.map(ref).values
    d["j_per_token"] = d.energy_j / d.tokens
    return d.reset_index(drop=True)


# ---- command-line driver ---------------------------------------------------------------------------------------------
import re  # noqa: E402
import sys  # noqa: E402
from pathlib import Path  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def load_rel_w1(path=None):
    """W1 median relative throughput by kernel and SM clock, parsed from the committed W1 results table (data/w1_downclock_results.md)."""
    text = Path(path or ROOT / "data" / "w1_downclock_results.md").read_text(encoding="utf-8")
    rel = {"mem": {}, "fma": {}}
    for m in re.finditer(r"^\| (mem|fma) \| (\d+) \| \d+ \| \d+ \| [\d.]+ [A-Za-z/]+ \| ([\d.]+) \[", text, re.M):
        rel[m.group(1)][int(m.group(2))] = float(m.group(3))
    if not rel["fma"] or not rel["mem"]:
        raise ValueError("no relative-throughput rows found in the W1 results file")
    return rel


def _newest(part):
    runs = sorted((ROOT / "data" / "raw" / f"w2_{part}").glob("*/results.csv"))
    if not runs:
        sys.exit(f"no full-run results.csv under data/raw/w2_{part}")
    return runs[-1].parent


def _fmt(df, floatfmt=".3f"):
    try:
        return df.to_markdown(index=False, floatfmt=floatfmt)
    except ImportError:                       # tabulate not installed
        return df.to_string(index=False)


def _md_head(run_dir, title):
    meta = json.loads((run_dir / "meta.json").read_text(encoding="utf-8"))
    return [f"# {title}", "", f"Source: `{run_dir}` | run {meta['utc']} | admin {meta['admin']} | AC {meta['ac_plugged']} | ambient {meta['ambient_c']} C | "
            f"{meta['gpu']} | driver {meta['driver']} | yaml {meta['yaml_sha']} | dll {meta['dll_sha']} | git {meta['git_head'][:8]}",
            f"HAGS: {meta['hags']['line']}. Execution mode: {meta['execution_mode']}.", ""]


def _flags_block(df):
    fl = df[df["flags"].fillna("") != ""][["block", "cell_id", "flags"]]
    return ["", f"## Flags (cells stay in the data): {len(fl)} of {len(df)}", "", fl.to_string(index=False) if len(fl) else "none"]


def report_A(run_dir):
    df = pd.read_csv(run_dir / "results.csv")
    cells = a_cells(df)
    r = ha1(cells); cls = classify_ha1(cells, r); h2 = ha2(cells)
    L = _md_head(run_dir, "W2 Experiment A: residual-wait model") + [
        f"Blocks: {df.block.nunique()}, cells per block: {df.groupby('block').size().iloc[0]}.", "",
        "## HA1", "", f"- slope {r['slope']:.3f}, 90% block-bootstrap CI [{r['ci_lo']:.3f}, {r['ci_hi']:.3f}] (equivalence bounds [0.8, 1.25]): equivalent = {r['equivalent']}",
        f"- intercept {r['intercept']:.3f} ms, 90% CI [{r['int_lo']:.3f}, {r['int_hi']:.3f}]",
        f"- cells within +/-25% of prediction: {r['frac_within25']:.2f} (need >= 0.70)",
        f"- **HA1 {'SUPPORTED' if r['supported'] else 'NOT SUPPORTED'}**; classification: **{cls}**", "",
        "## HA2 (variance raises wait)", "", _fmt(h2["table"]), "", f"**HA2 {'SUPPORTED' if h2['supported'] else 'NOT SUPPORTED'}** ({h2['n_sig']}/6 significant after Holm).", "",
        "## Cell medians over blocks (obs = mean latency - block baseline; pred from realised slices)", "",
        _fmt(cells.groupby(["m_ms", "cv"])[["obs_ms", "pred_ms"]].median().reset_index())]
    L += _flags_block(df)
    return L, "A"


def b_per_cell(df):
    """Per-cell medians over blocks with the completed fraction beside the latency percentiles (percentiles cover completed frames only;
    review 2026-10-21_w2_B_review finding 4)."""
    return df.groupby("cell_id")[["frac_completed", "lat_p50_ms", "lat_p99_ms", "fg_gpu_p50_ms", "miss_frac", "power_counter_w", "sm_clock_med"]].median().reset_index()


def deadline_aware(df, prefix):
    """Descriptive slack reclamation: for cells `<prefix>_<level>`, median power/miss/p99 per level, power saved vs unlocked, and the
    lowest-power level with zero median misses (attrs['best_level']). Never a tested claim."""
    g = df[df.cell_id.str.startswith(prefix + "_")].copy()
    g["level"] = g.cell_id.str[len(prefix) + 1:]
    t = g.groupby("level")[["miss_frac", "power_counter_w", "lat_p99_ms"]].median()
    t["power_saved_vs_unlocked"] = 1 - t.power_counter_w / t.power_counter_w["unlocked"]
    ok = t[t.miss_frac == 0]
    t = t.reset_index(); t.attrs["best_level"] = str(ok.power_counter_w.idxmin()) if len(ok) else None
    return t


def report_B(run_dir):
    df = pd.read_csv(run_dir / "results.csv"); rel = load_rel_w1(); t = b_service_tables(df)
    h1 = hb1(t["hb1"], rel)
    L = _md_head(run_dir, "W2 Experiment B: device-wide clock lock vs foreground") + [
        "## HB1 (reference: locked 1800 MHz)", "", _fmt(h1["table"]), "", f"**HB1 {'SUPPORTED' if h1['supported'] else 'NOT SUPPORTED'}** (all fma frames, all levels).", "",
        "## HB2 (deadline misses vs 1800 MHz; overloaded levels: only miss fraction and service time are interpreted)", ""]
    for bgname in ("nobg", "membg"):
        d = t[f"hb2_{bgname}"]
        for frame, g in d[d.kind == "fma"].groupby("frame"):
            budget = 1000.0 / (120 if "120" in frame else 60)
            ratios = {lv: rel["fma"][1800] / rel["fma"][lv] for lv in HB_TEST_LEVELS}
            r = hb2(g, budget, ratios)
            L += [f"### {frame}, background {bgname}: must be significant at {r['must_be_significant']} -> **{'SUPPORTED' if r['supported'] else 'NOT SUPPORTED'}**{' (UNINFORMATIVE: ceiling, the 1800 MHz reference already misses ~100% of frames, so no level can be worse; the verdict above is the registered rule applied as written)' if r['reference_at_ceiling'] else ''}", "", _fmt(r["table"]), ""]
    d1 = t["hb1"][t["hb1"].level.isin([1050, 1800])]
    rows = []
    for (frame, kind), g in d1.groupby(["frame", "kind"]):
        piv = g.pivot_table(index="block", columns="level", values="service_ms")
        if 1050 in piv and 1800 in piv:
            rows.append(dict(frame=frame, ratio_1050_vs_1800_median=float((piv[1050] / piv[1800]).median()),
                             interpolated_w1_prediction=interp_service_ratio(rel, kind, 1050)))
    if rows:
        L += ["## Descriptive: 1050 MHz (B-levels addendum; outside HB1/HB2; the W1 value is a linear interpolation, not a measurement)", "", _fmt(pd.DataFrame(rows)), ""]
    L += ["## Descriptive: deadline-aware clock locking (slack reclamation; not a tested claim)", ""]
    for pre in ("fma_60hz_nobg", "fma_120hz_nobg", "mem_60hz_nobg"):
        d = deadline_aware(df, pre)
        L += [f"### {pre}: lowest-power level with zero misses = {d.attrs['best_level']}", "", _fmt(d), ""]
    L += ["## Descriptive per cell (medians over blocks)", "",
          "frac_completed is the fraction of frames finished inside the window; latency percentiles cover COMPLETED frames only (survivorship bias in overloaded cells). "
          "fg_gpu_p50_ms is a cudaEvent interval and, while the context is time-sliced, may include switched-out time (see the Nsight Systems trace note); do not read it as service time in co-run cells.", "",
          _fmt(b_per_cell(df))]
    L += _flags_block(df)
    return L, "B"


def _fp16_main_finding(d, level=1050):
    med = d[(d.variant == "fp16") & d.graph].groupby("level")[["rel_thr", "j_per_token"]].median()
    k, u = med.loc[level], med.loc["unlocked"]
    i4 = d[(d.variant == "int4") & d.graph].groupby("level").rel_thr.median()
    return (f"- **Main C finding (fp16 proxy, 14 layers, CUDA graph):** at {level} MHz the proxy keeps {k.rel_thr:.2f} of its unlocked throughput at "
            f"{k.j_per_token:.3f} J/token against {u.j_per_token:.3f} J/token unlocked ({100 * (1 - k.j_per_token / u.j_per_token):.0f}% lower; board-level energy counter, "
            f"W1 addendum caveats apply).\n"
            f"- **Construct validity of the int4 proxy:** HC1 is supported statistically, but the int4 proxy lacks construct validity for Q4 decode: its dequantisation is "
            f"scalar, and its throughput is close to proportional to the clock (relative throughput {i4[1800]:.3f} at 1800 MHz against 1800/2460 = {1800 / 2460:.3f}). "
            f"Only the direction (more ALU work per byte raises the knee) is supported; the magnitude does not transfer. "
            f"**Do not use the int4 knee in any governor claim.** A real engine is measured by the llama.cpp validation addendum.")


def report_C(run_dir):
    df = pd.read_csv(run_dir / "results.csv"); d = c_rel_thr(df)
    h = hc1(d)
    L = _md_head(run_dir, "W2 Experiment C: decode proxy clock knee") + [
        "## Per-block knees (graph launch mode; 10000 = unlocked)", "", _fmt(h["knee_table"].reset_index().rename(columns={"index": "block"}), ".0f"), "",
        f"**HC1 {h['status'].upper()}** (nonzero int4 - fp16 knee differences in {h['n_nonzero']} blocks; p = {h['p']}).", "",
        "## Knee and energy optimum per configuration (medians over blocks)", ""]
    rows = []
    for (variant, graph), g in d.groupby(["variant", "graph"]):
        med = g.groupby("level")[["rel_thr", "j_per_token"]].median()
        knee = find_knee({_lvl(lv): v for lv, v in med.rel_thr.items()})
        opt = med.j_per_token.idxmin()
        rows.append(dict(variant=variant, graph=graph, knee_mhz=("never" if knee is None else "unlocked" if knee == UNLOCKED_KEY else knee),
                         energy_optimum=opt, j_per_token_at_opt=float(med.j_per_token.min())))
    main = _fp16_main_finding(d)
    L += [_fmt(pd.DataFrame(rows)), "", "## Main finding (fp16 proxy, CUDA graph) and the limits of the int4 result", "", main, "",
          "## rel. throughput and J/token by level (medians)", "",
          _fmt(d.groupby(["variant", "graph", "level"])[["rel_thr", "j_per_token"]].median().reset_index())]
    L += _flags_block(df)
    return L, "C"


def _cell_dir(run_dir, r):
    return next((run_dir / "cells").glob(f"b{int(r.block):02d}_{int(r.cell_idx):02d}_*"))


def report_A2(run_dir, a_dir):
    from loadgen import phase_in_slice, slice_stretch
    df2 = pd.read_csv(run_dir / "results.csv"); dfa = pd.read_csv(a_dir / "results.csv")
    L = _md_head(run_dir, "W2 Experiment A secondary: preemption characterisation (descriptive; motivated by the pilot, journal 0011)")
    rows = []
    for _, r in dfa.iterrows():                   # SA1: c = 0, m in {2, 4, 8}, from the A run's cell logs
        sp = json.loads(r.spec)
        if r.part != "A" or sp["bg"] is None or sp["bg"]["cv"] != 0 or sp["bg"]["m_ms"] not in (2, 4, 8):
            continue
        cd = _cell_dir(a_dir, r)
        with np.load(cd / "fg_window.npz") as fgz, np.load(cd / "bg_window.npz") as bgz:
            ph, inside = phase_in_slice(fgz["arrival"], bgz["t_start"], bgz["t_end"])
            lat = (fgz["t_complete"] - fgz["arrival"]) * 1e3
        rows.append((sp["bg"]["m_ms"], ph[inside], lat[inside], int(r.block)))
    L += ["## SA1 phase independence (slope of fg latency on arrival phase, ms/ms; -1 = waits out the slice, 0 = independent)", ""]
    if rows:
        P = np.concatenate([x[1] for x in rows]); LAT = np.concatenate([x[2] for x in rows]); BLK = np.concatenate([[x[3]] * len(x[1]) for x in rows])
        s = sa1_label(P, LAT, BLK)
        L.append(f"- pooled (m in 2, 4, 8): slope {s['slope']:.3f}, 90% CI [{s['ci_lo']:.3f}, {s['ci_hi']:.3f}] -> **{s['label']}**")
        for m in (2, 4, 8):
            sel = [x for x in rows if x[0] == m]
            sm_ = sa1_label(np.concatenate([x[1] for x in sel]), np.concatenate([x[2] for x in sel]), np.concatenate([[x[3]] * len(x[1]) for x in sel]))
            L.append(f"- m = {m} ms: slope {sm_['slope']:.3f}, CI [{sm_['ci_lo']:.3f}, {sm_['ci_hi']:.3f}] -> {sm_['label']}")
    pts = []                                      # SA2: fg sizes 0.1 (A run), 1 and 4 ms (A2 run), c = 0, duty 1, normal priority
    for src, dd in ((a_dir, dfa), (run_dir, df2)):
        for _, r in dd.iterrows():
            sp = json.loads(r.spec)
            if sp["bg"] is None or sp["bg"]["cv"] != 0 or sp["bg"]["duty"] != 1.0 or sp["fg"]["priority"] != "normal" or sp["fg"]["size_ms"] not in (0.1, 1, 4):
                continue
            with np.load(_cell_dir(src, r) / "fg_window.npz") as fgz, np.load(_cell_dir(src, r) / "bg_window.npz") as bgz:
                st, n = slice_stretch(bgz["t_start"], bgz["t_end"], fgz["t_complete"])
            if n >= 5:
                pts.append((r.fg_gpu_p50_ms, float(np.mean(st) * 1e3), int(r.block)))
    L += ["", "## SA2 slice stretch = s0 + k * fg service time", ""]
    if len(pts) >= 6:
        x, y, b = zip(*pts); o = ols_block_bootstrap(np.array(x), np.array(y), np.array(b), seed=SEED)
        L.append(f"- s0 (constant switch cost) = {o['intercept']:.3f} ms, 90% CI [{o['int_lo']:.3f}, {o['int_hi']:.3f}]; k = {o['slope']:.3f}, 90% CI [{o['ci_lo']:.3f}, {o['ci_hi']:.3f}] ({len(pts)} cell-blocks)")
    else:
        L.append("- not enough cells with >= 5 single-completion slices")
    hi = a_cells(df2, priority="high", baseline_df=dfa); no = a_cells(dfa)
    L += ["", "## SA3 priority control (fg HIGH minus NORMAL, observed wait, paired by block index across the two runs; no decision rule)", ""]
    if len(hi):
        m = hi.merge(no, on=["block", "m_ms", "cv"], suffixes=("_high", "_normal"))
        m["diff_ms"] = m.obs_ms_high - m.obs_ms_normal
        L.append(_fmt(m.groupby(["m_ms", "cv"]).diff_ms.agg(["median", "min", "max", "count"]).reset_index()))
    L += ["", "## SA4 foreground size and duty cycle (medians over blocks; slowdown = latency / the fg-alone latency of the same size)", ""]
    sp2 = _specs(df2)
    t4 = pd.DataFrame(dict(cell_id=df2.cell_id, fg_ms=sp2.map(lambda x: x["fg"]["size_ms"]), duty=sp2.map(lambda x: x["bg"]["duty"] if x["bg"] else 0.0),
                           m_ms=sp2.map(lambda x: x["bg"]["m_ms"] if x["bg"] else 0), lat_mean_ms=df2.lat_mean_ms, lat_p99_ms=df2.lat_p99_ms, fg_gpu_p50_ms=df2.fg_gpu_p50_ms))
    t4 = t4[~t4.cell_id.str.startswith("sa3")]
    med = t4.groupby(["cell_id", "fg_ms", "m_ms", "duty"]).median().reset_index()
    alone = med[med.duty == 0].set_index("fg_ms").lat_mean_ms
    med["slowdown"] = med.lat_mean_ms / med.fg_ms.map(alone)
    L += [_fmt(med.sort_values(["fg_ms", "m_ms", "duty"])), "",
          "Reference for 4 and 9 ms foreground: equal sharing predicts slowdown ~ 1 + duty (rough; descriptive only)."]
    L += _flags_block(df2)
    return L, "A2"


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--part", required=True, choices=["A", "A2", "B", "C"])
    ap.add_argument("--dir"); ap.add_argument("--dir-A", dest="dir_a")
    a = ap.parse_args()
    run_dir = Path(a.dir) if a.dir else _newest(a.part)
    if a.part == "A":
        L, tag = report_A(run_dir)
    elif a.part == "B":
        L, tag = report_B(run_dir)
    elif a.part == "C":
        L, tag = report_C(run_dir)
    else:
        L, tag = report_A2(run_dir, Path(a.dir_a) if a.dir_a else _newest("A"))
    out = ROOT / "data" / ("w2_A_secondary_results.md" if tag == "A2" else f"w2_{tag}_results.md")
    out.write_text("\n".join(L), encoding="utf-8")
    print("\n".join(L)); print(f"\nwritten: {out}")


if __name__ == "__main__":
    main()
