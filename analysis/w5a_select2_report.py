"""Markdown report of data/w5a/selection2.json (written by analysis/w5a_select2.py, plan addendum N). Facts only: every number is read from the JSON.
   python analysis/w5a_select2_report.py --in data/w5a/selection2.json --out data/w5a/selection2.md"""
import argparse
import json
from pathlib import Path


def f(x, d=2):
    return "nan" if x != x else f"{x:.{d}f}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", required=True); ap.add_argument("--out", required=True)
    a = ap.parse_args()
    r = json.loads(Path(a.inp).read_text(encoding="utf-8"))
    s = r["selection"]
    L = ["# W5a model selection RE-RUN — POST HOC (plan addendum N, the only re-run; run 1 = data/w5a/selection.md)", "",
         f"**Selected: {s['selected']}**", ""]
    if s.get("fallback"):
        L += [f"Fallback (fixed in addendum N): {s['fallback']}", ""]
    L += ["## Gates (K = 3, pooled LOWO)", ""] + [f"- {n}: " + ("; ".join(w) if w else "passes all gates") for n, w in {**{k: [] for k in r["candidates"]}, **s["failed_gates"]}.items()]
    L += ["", "## Pooled LOWO, K = 3", "",
          "| cand | false-feasible cells at tau 0.8 (95% CI) | false-infeasible | false-feasible picks / picks (95% CI) | strata with feasible | regret_rel | ln-tok MAE | median rel tok err | power MAE W | cov ln-tok | cov power | latency 1 thr ms | latency default ms |",
          "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for n, c in r["candidates"].items():
        p, l = c["lowo_k3"]["pooled"], c["latency"]
        ci, pci = p["false_feasible_cell_ci95"], p["false_feasible_pick_ci95"]
        L.append(f"| {n} | {f(p['false_feasible_cell_rate'], 3)} ({f(ci[0], 3)}-{f(ci[1], 3)}; {p['feas_class_tau']['false_feasible']} false-feasible cells) | {f(p['false_infeasible_rate'], 3)} | {p['false_feasible_picks']} / {p['picks']} ({f(pci[0])}-{f(pci[1])}) | {p['strata_with_feasible']} of {p['strata_total']} | {f(p['regret_rel'])} | {f(p['mu_mae'])} | {f(p['tok_median_rel_err'])} | {f(p['power_mae'], 1)} | {f(p['coverage']['mu'])} | {f(p['coverage']['power_w'])} | {f(l['one_thread_s'] * 1e3)} | {f(l['default_threads_s'] * 1e3)} |")
    L += ["", "Latency against the old 1 ms bound: " + "; ".join(f"{n} {'passes' if c['latency']['one_thread_s'] < 1e-3 else 'fails'}" for n, c in r["candidates"].items()) + ". New bound (10 ms p99, 1 thread): " + "; ".join(f"{n} {'passes' if c['latency']['one_thread_s'] <= 10e-3 else 'fails'}" for n, c in r["candidates"].items()) + ".", "",
          "## Per fold (K = 3): coverage ln-tok / power, false-feasible cell rate, picks (false-feasible), conformal q (ln units / W)", ""]
    for n, c in r["candidates"].items():
        for w, p in c["lowo_k3"]["per_fold"].items():
            L.append(f"- {n} / held out {w}: {f(p['coverage']['mu'])} / {f(p['coverage']['power_w'])}, {f(p['false_feasible_cell_rate'])}, {p['picks']} ({p['false_feasible_picks']}), q {f(p['conformal_q']['mu'][0])} / {f(p['conformal_q']['power_w'][0], 1)}")
    L += ["", "## K = 1 sensitivity (not used): false-feasible cell rate, picks (ff), coverage ln-tok / power, regret_rel", ""]
    for n, c in r["candidates"].items():
        p = c["lowo_k1"]["pooled"]
        L.append(f"- {n}: {f(p['false_feasible_cell_rate'], 3)}, {p['picks']} ({p['false_feasible_picks']}), {f(p['coverage']['mu'])} / {f(p['coverage']['power_w'])}, {f(p['regret_rel'])}")
    L += ["", "## Leave-one-condition-out (reported only), K = 3: pooled false-feasible cell rate, picks (ff); c14 alone: false-feasible cell rate, picks", ""]
    for n, c in r["candidates"].items():
        p, q = c["loco_k3"]["pooled"], c["loco_k3"]["per_condition"]["c14"]
        L.append(f"- {n}: {f(p['false_feasible_cell_rate'], 3)}, {p['picks']} ({p['false_feasible_picks']}); c14: {f(q['false_feasible_cell_rate'], 3)}, {q['picks']} ({q['false_feasible_picks']})")
    L += ["", "## Secondary (reported only): in-range p99 MAE (ms)", ""] + [f"- {n}: {f(c['lowo_k3']['pooled']['p99_in_range_mae'], 1)} (n = {c['lowo_k3']['pooled']['n_p99_in_range']})" for n, c in r["candidates"].items()]
    Path(a.out).write_text("\n".join(L) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
