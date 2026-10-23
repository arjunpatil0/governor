"""Markdown report of data/w5a/selection.json (written by analysis/w5a_select.py). Facts only: every number is read from the JSON.
   python analysis/w5a_select_report.py --in data/w5a/selection.json --out data/w5a/selection.md"""
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
    L = ["# W5a model selection result (analysis/w5a_select.py, protocol = plan addendum L)", "",
         f"**Selected: {r['selection']['selected']}**  ({r['selection'].get('note', '')})", "", "## Gates (K = 3, pooled LOWO)", ""]
    for n, why in r["selection"]["failed_gates"].items():
        L.append(f"- {n}: " + "; ".join(why))
    L += ["", "## Pooled LOWO, K = 3", "", "| cand | false-feasible picks | picks | regret_rel | tok MAE | power MAE W | p99 err ms (p99 of abs err) | cov tok | cov power | cov p99 | latency ms |", "|---|---|---|---|---|---|---|---|---|---|---|"]
    for n, c in r["candidates"].items():
        p = c["lowo_k3"]["pooled"]
        L.append(f"| {n} | {p['false_feasible_picks']} | {p['picks']} | {f(p['regret_rel'])} | {f(p['tok_mae'], 1)} | {f(p['power_mae'], 1)} | {f(p['p99_err'], 0)} | {f(p['coverage']['tok_s'])} | {f(p['coverage']['power_w'])} | {f(p['coverage']['p99'])} | {f(c['latency_p99_s'] * 1e3)} |")
    L += ["", "## Per fold (K = 3): tok MAE / power MAE / picks (false-feasible) / regret_rel / coverage tok, power, p99", ""]
    for n, c in r["candidates"].items():
        for w, p in c["lowo_k3"]["per_fold"].items():
            cv = p["coverage"]
            L.append(f"- {n} / held out {w}: {f(p['tok_mae'], 1)} / {f(p['power_mae'], 1)} / {p['picks']} ({p['false_feasible_picks']}) / {f(p['regret_rel'])} / {f(cv['tok_s'])}, {f(cv['power_w'])}, {f(cv['p99'])}")
    L += ["", "## Miss classification at the SLO (pooled LOWO K = 3): false-feasible / false-infeasible, share of all test cells", ""]
    for n, c in r["candidates"].items():
        m = c["lowo_k3"]["pooled"]["miss_class"]
        L.append(f"- {n}: {f(m['false_feasible_share_of_all'], 3)} / {f(m['false_infeasible_share_of_all'], 3)}  (false-feasible among predicted-feasible {f(m['false_feasible_of_predicted_feasible'], 3)}; n = {m['n']})")
    L += ["", "## Sensitivity K = 1 (not used for selection): false-feasible picks / picks, regret_rel, tok MAE, power MAE", ""]
    for n, c in r["candidates"].items():
        p = c["lowo_k1"]["pooled"]
        L.append(f"- {n}: {p['false_feasible_picks']} / {p['picks']}, {f(p['regret_rel'])}, {f(p['tok_mae'], 1)}, {f(p['power_mae'], 1)}")
    L += ["", "## Leave-one-condition-out (reported only), K = 3: pooled tok MAE / power MAE / p99 err / picks (ff); c14 alone", ""]
    for n, c in r["candidates"].items():
        p, q = c["loco_k3"]["pooled"], c["loco_k3"]["per_condition"]["c14"]
        L.append(f"- {n}: {f(p['tok_mae'], 1)} / {f(p['power_mae'], 1)} / {f(p['p99_err'], 0)} / {p['picks']} ({p['false_feasible_picks']}); c14: tok {f(q['tok_mae'], 1)}, power {f(q['power_mae'], 1)}, p99 err {f(q['p99_err'], 0)}, picks {q['picks']} ({q['false_feasible_picks']})")
    L += ["", "## Implementation notes — these five choices were made while implementing run 1 WITHOUT registration (reviewer 2026-10-23); addendum N adopts or reverts each", ""] + [f"- {x}" for x in r["notes"]]
    L += ["- Also unregistered: the regret margin was an absolute +0.10 (a ratio rule is degenerate near 0); intervals were RMS of inner out-of-fold residuals; GP was subset-of-data with seed 0; CUSUM was not evaluated offline."]
    Path(a.out).write_text("\n".join(L) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
