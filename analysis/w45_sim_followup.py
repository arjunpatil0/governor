"""POST-HOC / SENSITIVITY follow-ups to the frozen simulator study (reviewer follow-up 2026-10-22; frozen results data/w45_sim_results.md are NOT changed).
1. Empirical bg token-time jitter (from the L per-token logs) added to the plant; held-out evaluation rerun once under it.
2. Scenario-agnostic best static setting (chosen across all scenarios on the tuning seeds) next to the per-scenario oracle, plus 'e' = aligned global static + idle-triggered clock drop.
3. d' vs c' (aligned) as the primary learned-vs-feedback comparison; Pareto front (tok/s vs power) as the headline, lambda = 0.5 marked.
Writes data/sim_tuned_followup.json, data/w45_sim_followup.csv, data/w45_sim_followup.md, data/w45_sim_pareto.png.   Run: python analysis/w45_sim_followup.py"""
import concurrent.futures as cf
import dataclasses
import json
import sys
import zlib
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "analysis"))
from controllers.common import ALLOWED_CLOCKS  # noqa: E402
from controllers.static import LAMBDA, tune_static, tune_static_global  # noqa: E402
from sim.params import load_params  # noqa: E402
from sim.run import EVAL_SEEDS, TUNING_SEEDS, load_tuned, run_matrix  # noqa: E402
from sim.scenarios import SCENARIOS  # noqa: E402
from w45_sim_report import SLO, holds_slo, paired_diff, pareto_front  # noqa: E402

OUT_TUNED = ROOT / "data" / "sim_tuned_followup.json"
BASE = ("a", "b", "b'", "c", "c'", "d", "d'", "g", "g'", "e")


def _best(rows):
    ok = [r for r in rows if r["feasible"]]
    return max(ok, key=lambda r: r["objective"]) if ok else min(rows, key=lambda r: r["miss_max_seen"])


def _job_global(a):
    P, pacing, clk, jitter = a
    r = tune_static_global(P, pacing, TUNING_SEEDS, SCENARIOS, clocks=(clk,), jitter=jitter)
    return pacing, jitter, r


def _job_scn(a):
    P, scn, clk = a
    r = tune_static(P, scn, "aligned", TUNING_SEEDS, clocks=(clk,), jitter=True)
    return scn, r


def tune_followup(P, workers=8):
    out = dict(meta=dict(seeds=list(TUNING_SEEDS), lam=LAMBDA, note="post-hoc follow-up; chosen on tuning seeds only"), global_={}, static_jit={})
    clocks = ALLOWED_CLOCKS(P)
    with cf.ProcessPoolExecutor(max_workers=workers) as ex:
        glob = list(ex.map(_job_global, [(P, p, c, j) for p in ("unaligned", "aligned") for c in clocks for j in (False, True)]))
        scn = list(ex.map(_job_scn, [(P, s, c) for s in SCENARIOS for c in clocks]))
    for jitter in (False, True):
        for pacing in ("unaligned", "aligned"):
            rows = [dict(r, feasible=r["feasible"]) for p, j, r in glob if p == pacing and j == jitter]
            b = _best(rows)
            out["global_" + ("jit" if jitter else "nojit")] = out.get("global_" + ("jit" if jitter else "nojit"), {})
            out["global_" + ("jit" if jitter else "nojit")]["g" if pacing == "unaligned" else "g'"] = dict(
                action=dataclasses.asdict(b["action"]), tok_s=b["tok_s"], power_w=b["power_w"], miss_max_seen=b["miss_max_seen"], feasible=b["feasible"])
    for s in SCENARIOS:
        b = _best([r for sc, r in scn if sc == s])
        out["static_jit"][s] = {"b'": dict(dataclasses.asdict(b["action"]))}
        out["static_jit"][s]["_meta"] = dict(tok_s=b["tok_s"], power_w=b["power_w"], miss_max_seen=b["miss_max_seen"], feasible=b["feasible"])
    return out


def _variant_tuned(tuned, fu, jitter):
    t = dict(tuned)
    g = fu["global_jit" if jitter else "global_nojit"]
    t["global"] = {k: v["action"] for k, v in g.items()}
    t["static_jit"] = {s: {"b'": {k: v for k, v in d["b'"].items()}} for s, d in fu["static_jit"].items()}
    return t


def _f(df, nd=2):
    return "```\n" + df.round(nd).to_string() + "\n```"


def section(df, label):
    df = df.copy()
    df["objective"] = df.bg_tok_s - LAMBDA * df.power_w
    ctl = [c for c in (*BASE, "bj'") if c in set(df.controller)]
    L = [f"## {label}", ""]
    slo = df.groupby(["scenario", "controller"]).miss_frac.mean().unstack().loc[list(SCENARIOS), ctl]
    hold = pd.DataFrame({c: [holds_slo(df[(df.scenario == s) & (df.controller == c)].miss_frac) for s in SCENARIOS] for c in ctl}, index=list(SCENARIOS))
    L += ["### SLO: mean miss fraction (top) and holds_slo (bottom)", _f(slo, 4), _f(hold), ""]
    L += ["### Pareto headline (median tok/s, median power W; controllers that hold the SLO; `*` = on the Pareto front; objective = tok/s - 0.5 W is ONE marked point)", ""]
    for s in SCENARIOS:
        pts = {}
        for c in ctl:
            sub = df[(df.scenario == s) & (df.controller == c)]
            if holds_slo(sub.miss_frac):
                pts[c] = (float(sub.bg_tok_s.median()), float(sub.power_w.median()))
        front = pareto_front(pts)
        tab = pd.DataFrame([dict(controller=c + ("*" if c in front else ""), tok_s=t, power_w=w, objective_lam0p5=t - LAMBDA * w, j_per_token=float(df[(df.scenario == s) & (df.controller == c)].j_per_token.median()))
                            for c, (t, w) in sorted(pts.items(), key=lambda kv: -kv[1][0])]).set_index("controller")
        best = tab.objective_lam0p5.idxmax() if len(tab) else "none"
        L += [f"#### {s}  (lambda = 0.5 best: {best})", _f(tab, 2), ""]
    L += ["### Paired comparisons on the objective, tok/s and power (median of A - B over seeds where both meet the SLO; 90% bootstrap CI)", ""]
    pairs = [("d'", "c'"), ("c'", "g'"), ("d'", "g'"), ("e", "g'"), ("e", "b'"), ("g'", "b'"), ("c'", "e"), ("d'", "e")] + ([("bj'", "b'")] if "bj'" in ctl else [])
    for a, b in pairs:
        rows = []
        for s in SCENARIOS:
            for m in ("objective", "bg_tok_s", "power_w"):
                rows.append(dict(scenario=s, metric=m, **paired_diff(df, a, b, s, m, seed=zlib.crc32(f"{a}|{b}|{s}|{m}".encode()))))
        L += [f"#### {a} minus {b}" + ("   (PRIMARY learned-vs-feedback comparison)" if (a, b) == ("d'", "c'") else ""), _f(pd.DataFrame(rows).set_index(["scenario", "metric"]), 3), ""]
    return L


def plot(dfs, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axs = plt.subplots(2, len(SCENARIOS), figsize=(3.2 * len(SCENARIOS), 6.4), sharey=False)
    for r, (label, df) in enumerate(dfs.items()):
        for k, s in enumerate(SCENARIOS):
            ax = axs[r][k]
            pts = {}
            for c in df.controller.unique():
                sub = df[(df.scenario == s) & (df.controller == c)]
                if holds_slo(sub.miss_frac):
                    pts[c] = (float(sub.power_w.median()), float(sub.bg_tok_s.median()))
            front = pareto_front({c: (t, w) for c, (w, t) in pts.items()})
            for c, (w, t) in pts.items():
                ax.scatter(w, t, s=40 if c in front else 18, marker="o" if c in front else "x")
                ax.annotate(c, (w, t), fontsize=7, xytext=(3, 3), textcoords="offset points")
            if pts:
                bw, bt = max(pts.values(), key=lambda p: p[1] - LAMBDA * p[0])[0], max(pts.values(), key=lambda p: p[1] - LAMBDA * p[0])[1]
                xs = np.array(ax.get_xlim()); ax.plot(xs, bt + LAMBDA * (xs - bw), "k:", lw=0.8)
            ax.set_title(f"{s} ({label})", fontsize=8); ax.set_xlabel("GPU power (W)", fontsize=7)
            if k == 0:
                ax.set_ylabel("bg tok/s", fontsize=7)
    fig.suptitle("Simulation only: Pareto points of controllers that hold the 1% SLO; dotted line = lambda 0.5 iso-objective through its best point", fontsize=8)
    fig.tight_layout()
    fig.savefig(path, dpi=130)


def main():
    P = load_params(ROOT)
    tuned = load_tuned()
    fu = tune_followup(P)
    OUT_TUNED.write_text(json.dumps(fu, indent=1), encoding="utf-8")
    dfs, csv = {}, []
    for jitter, label in ((False, "plant as frozen (no token jitter)"), (True, "plant with empirical token-time jitter")):
        tv = _variant_tuned(tuned, fu, jitter)
        ctl = BASE + (("bj'",) if jitter else ())
        df = run_matrix(P, ctl, SCENARIOS, EVAL_SEEDS, tv, jitter=jitter)
        dfs[label] = df; csv.append(df)
    pd.concat(csv).to_csv(ROOT / "data" / "w45_sim_followup.csv", index=False)
    L = ["# W4-5 simulator follow-ups (POST-HOC / SENSITIVITY; the frozen results in data/w45_sim_results.md are unchanged)", "",
         "Held-out evaluation seeds 200-229, each configuration evaluated once. Controllers c, c', d, d' and the per-scenario statics b, b' keep their FROZEN constants (tuned without jitter); "
         "the scenario-agnostic statics g, g' and e were chosen on the tuning seeds 100-109 (data/sim_tuned_followup.json), under the jittered plant for the jitter evaluation. "
         "bj' = per-scenario aligned static re-tuned under jitter. Token jitter: inter-token intervals from the L per-token logs / cell median, pooled, mean 1. SIMULATION ONLY.", "",
         "## Chosen settings (tuning seeds)", "", "```", json.dumps({k: fu[k] for k in ("global_nojit", "global_jit")}, indent=1), "```", "",
         "Per-scenario aligned static re-tuned under jitter (bj'):", "", "```", json.dumps(fu["static_jit"], indent=1), "```", ""]
    for label, df in dfs.items():
        L += section(df, label)
    (ROOT / "data" / "w45_sim_followup.md").write_text("\n".join(L), encoding="utf-8")
    plot(dfs, ROOT / "data" / "w45_sim_pareto.png")
    print("written data/w45_sim_followup.md")


if __name__ == "__main__":
    main()
