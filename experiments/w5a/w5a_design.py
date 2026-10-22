"""W5a cell list (registered in experiments/w5_governor.yaml, stages.W5a_data_collection; committed 2026-10-23).
18 strata = known workloads x 6 absolute foreground conditions (nominal ms of work alone at 1800 MHz: constant 5, 7, 9, 11, 14 and VARYING = the S1 steps x1.0/0.7/1.3/0.7/1.0/1.3 every 10 s on a base of 9 ms).
Per stratum: SM clock {900, 1050, 1200, 1350, 1500, 1800, unlocked} x pacing configuration {aligned: guard {0, 1 ms} x duty {0.25, 0.5, 1}; unaligned: duty {0.1, 0.25, 0.5, 1}} (70 settings).
Selection: every stratum x clock pair once (126 cells), the rest a seeded draw that keeps the clock and pacing marginals balanced and never repeats a setting inside a stratum; total n_total (280).
Sessions: cells are spread over n_sessions (equal size +-1, every stratum in at least two sessions) and ordered at random inside a session. The held-out workload (8B) is refused.
Run: python experiments/w5a/w5a_design.py --seed 20261023 --out data/w5a/cell_list.json     (the file is then frozen by an addendum)"""
import argparse
import json
from pathlib import Path

import numpy as np

CLOCKS = (900, 1050, 1200, 1350, 1500, 1800, "unlocked")
PACING = tuple([dict(pacing_id=f"a_g{g:g}_d{d:g}", mode="aligned", guard_ms=g, duty=d) for g in (0.0, 1.0) for d in (0.25, 0.5, 1.0)]
               + [dict(pacing_id=f"u_d{d:g}", mode="unaligned", guard_ms=0.5, duty=d) for d in (0.1, 0.25, 0.5, 1.0)])
CONDITIONS = tuple([dict(name=f"c{c}", base_ms=float(c), varying=False) for c in (5, 7, 9, 11, 14)] + [dict(name="var9", base_ms=9.0, varying=True)])
STEPS = (1.0, 0.7, 1.3, 0.7, 1.0, 1.3)
HELD_OUT = "8b"


def cond_cost_fn(name):
    c = next(x for x in CONDITIONS if x["name"] == name)
    if not c["varying"]:
        return lambda t_ms, b=c["base_ms"]: b
    return lambda t_ms, b=c["base_ms"]: b * STEPS[min(int(t_ms // 10000.0), len(STEPS) - 1)]


def build_list(workloads, seed, n_total=280, n_sessions=3):
    if any(HELD_OUT in w.lower() for w in workloads):
        raise ValueError("the held-out workload (8B) must never enter W5a")
    rng = np.random.default_rng(seed)
    strata = [(w, c["name"]) for w in workloads for c in CONDITIONS]
    n_clock, n_pace = {str(c): 0 for c in CLOCKS}, {p["pacing_id"]: 0 for p in PACING}
    chosen, used = [], {s: set() for s in strata}

    def take(stratum, clock, p):
        chosen.append((stratum, clock, p))
        used[stratum].add((str(clock), p["pacing_id"]))
        n_clock[str(clock)] += 1
        n_pace[p["pacing_id"]] += 1

    for s in strata:                                                      # every stratum x clock pair once; the pacing configuration balances the pacing marginal
        for clock in CLOCKS:
            take(s, clock, min(PACING, key=lambda p: (n_pace[p["pacing_id"]], rng.random())))
    n_extra = n_total - len(chosen)
    quota = {s: n_extra // len(strata) for s in strata}
    for i in rng.permutation(len(strata))[: n_extra - sum(quota.values())]:
        quota[strata[int(i)]] += 1
    order = [s for s in strata for _ in range(quota[s])]
    for k in rng.permutation(len(order)):                                 # interleave the strata so that the marginal balancing is not biased to the first strata
        s = order[int(k)]
        cands = [(clock, p) for clock in CLOCKS for p in PACING if (str(clock), p["pacing_id"]) not in used[s]]
        scores = [n_clock[str(c)] + n_pace[p["pacing_id"]] + rng.random() * 0.5 for c, p in cands]
        c, p = cands[int(np.argmin(scores))]
        take(s, c, p)
    by_stratum = {}
    for i in rng.permutation(len(chosen)):
        by_stratum.setdefault(chosen[int(i)][0], []).append(int(i))
    session_of, start = {}, 0
    for s in strata:                                                      # round-robin inside a stratum, the cycle continues across strata so the session sizes stay equal +-1
        for j, i in enumerate(by_stratum[s]):
            session_of[i] = (start + j) % n_sessions + 1
        start = (start + len(by_stratum[s])) % n_sessions
    order_in = {k: iter(rng.permutation(sum(1 for v in session_of.values() if v == k)).tolist()) for k in range(1, n_sessions + 1)}
    cells = []
    for i, ((w, cond), clock, p) in enumerate(chosen):
        cells.append(dict(cell_id=f"w5a_{w}_{cond}_{clock}_{p['pacing_id']}", workload=w, condition=cond, clock=clock, pacing_id=p["pacing_id"], mode=p["mode"], guard_ms=p["guard_ms"],
                          duty=p["duty"], session=session_of[i], order=next(order_in[session_of[i]]), seed=int(seed)))
    cells.sort(key=lambda c: (c["session"], c["order"]))
    return cells


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--workloads", default="llama32_1b,llama32_3b,phi35_mini")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    cells = build_list(tuple(a.workloads.split(",")), a.seed)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(dict(seed=a.seed, workloads=a.workloads.split(","), n=len(cells), cells=cells), indent=1), encoding="utf-8")
    print(f"{len(cells)} cells -> {a.out}")
