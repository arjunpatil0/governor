"""W5b tuning blocks T1-T3: pure plan and decision logic, exactly as stated in plan addendum O section 4 (docs/W5B_ADDENDUM_O.md; tests/test_w5b_tune_lib.py).
next_batch(results) is a deterministic function of the stored cell results: it returns the cells still to run (a seeded-random order inside a batch, the discarded cell first), or, when nothing is
missing, the decisions (c0, g'B per budget, c'B constants and pacing mode, d'B margin) and a stop reason if the feasibility gate failed. Resuming = calling it again with the stored results.
Cell results are dicts with miss (fraction INCLUDING abandoned frames), tok_s, power_w and, for foreground-alone cells, c0m (p50 latency ms)."""
import random

C0_GRID = (7, 8, 9, 10, 11)
WORKLOADS = ("llama32_1b", "llama32_3b", "phi35_mini")
SCENES = ("S0", "S1")
BUDGETS = (60.0, 35.0)
SEED = 20261024
MISS_MAX, ARM_A_MIN_MISS, TOK_FRACTION, TOP_N = 0.01, 0.05, 0.20, 8
CB_TARGETS, CB_KIS = (0.5, 0.65, 0.8), (0.05, 0.15)
DB_MARGINS = (0.0, 0.1, 0.2, 0.3, 0.4)
CLOCKS = (900, 1050, 1200, 1350, 1500, 1800, "unlocked")


def settings70():
    pac = [("aligned", g, d) for g in (0.0, 1.0) for d in (0.25, 0.5, 1.0)] + [("unaligned", 0.5, d) for d in (0.1, 0.25, 0.5, 1.0)]
    out = []
    for c in CLOCKS:
        for mode, g, d in pac:
            sid = f"{c}_{'a' if mode == 'aligned' else 'u'}" + (f"_g{g:g}" if mode == "aligned" else "") + f"_d{d:g}"
            out.append(dict(sid=sid, clock=c, mode=mode, guard_ms=g, duty=d))
    return out


def feasible(m, budget_w, bg_alone_tok_s):
    return bool(m["miss"] <= MISS_MAX and m["power_w"] <= budget_w and m["tok_s"] >= TOK_FRACTION * bg_alone_tok_s)


def _shuffled(specs, key):
    specs = sorted(specs, key=lambda s: s["id"])
    random.Random(f"{SEED}:{key}").shuffle(specs)
    return specs


def _static_id(c0, wl, scene, sid):
    return f"st_c{c0}_{wl}_{scene}_{sid}"


def _static_spec(c0, wl, scene, s):
    return dict(id=_static_id(c0, wl, scene, s["sid"]), kind="static", workload=wl, scene=scene, c0=c0, setting=s)


def _missing(specs, results):
    return [s for s in specs if s["id"] not in results]


def next_batch(results):
    dec = {}

    def ans(batch=(), stop=None, key=""):
        return dict(batch=_shuffled(list(batch), key), stop=stop, decisions=dec)

    # ---- T1 (a): the discarded full cell, then (b) the background-alone references
    disc = dict(id="t1_discard", kind="arm_a", workload="llama32_3b", scene="S0", c0=C0_GRID[0], discard=True)
    if disc["id"] not in results:
        return dict(batch=[disc], stop=None, decisions=dec)
    refs = [dict(id=f"t1_bgalone_{w}", kind="bg_alone", workload=w, scene=None, c0=None) for w in WORKLOADS]
    if _missing(refs, results):
        return ans(_missing(refs, results), key="refs")
    bg = {w: results[f"t1_bgalone_{w}"]["tok_s"] for w in WORKLOADS}
    dec["bg_alone_tok_s"] = bg
    sweep_all = settings70()
    # ---- T1 (c) + T2: the c0 search
    chosen, tried = None, []
    for c0 in C0_GRID:
        pre = [dict(id=f"t1_fgalone_c{c0}", kind="fg_alone", workload="llama32_3b", scene=None, c0=c0),
               dict(id=f"t1_arma_c{c0}", kind="arm_a", workload="llama32_3b", scene="S1", c0=c0)]
        if _missing(pre, results):
            return ans(_missing(pre, results), key=f"pre{c0}")
        arm = results[f"t1_arma_c{c0}"]
        rec = dict(c0=c0, c0m=results[f"t1_fgalone_c{c0}"]["c0m"], c0m_unlocked=results[f"t1_fgalone_c{c0}"].get("c0m_unlocked"), arm_a_miss=arm["miss"], swept=False, feasible_statics_60=None, feasible_statics_35=None)
        tried.append(rec)
        if arm["miss"] <= ARM_A_MIN_MISS:
            rec["note"] = "arm a misses <= 5% in S1: the gate fails without a sweep"
            continue
        sweep = [_static_spec(c0, "llama32_3b", "S1", s) for s in sweep_all]
        if _missing(sweep, results):
            return ans(_missing(sweep, results), key=f"sweep{c0}")
        rec["swept"] = True
        for b in BUDGETS:
            rec[f"feasible_statics_{int(b)}"] = sum(1 for s in sweep if feasible(results[s["id"]], b, bg["llama32_3b"]))
        if rec["feasible_statics_60"] > 0:
            chosen = c0
            break
    dec["c0_search"] = tried
    if chosen is None:
        return dict(batch=[], stop="no c0 in {7, 8, 9, 10, 11} meets the HW0 feasibility gate at 60 W: the run stops and the result is reported (no other c0 is invented)", decisions=dec)
    dec["c0"] = chosen
    fa = results[f"t1_fgalone_c{chosen}"]
    dec["c0m"] = fa["c0m"]                                                                      # measured frame time alone at a LOCKED 1800 MHz (the clock that defines nominal c0), addendum O-2
    dec["c0m_unlocked"] = fa.get("c0m_unlocked")
    dec["c0m_basis"] = "locked 1800 MHz p50 latency; c0m_unlocked = the same with the clock unlocked and no background (it can sit below the boost clock when the GPU idles between frames)"
    dec["sm_median_fg_alone"] = dict(locked=fa.get("sm_locked_median"), unlocked=fa.get("sm_unlocked_median"))
    # ---- T3 stage 2: top 8 feasible stage-1 settings per budget
    by_sid = {s["sid"]: s for s in sweep_all}
    top = {}
    for b in BUDGETS:
        rows = [(results[_static_id(chosen, "llama32_3b", "S1", s["sid"])], s["sid"]) for s in sweep_all]
        rows = [(m["tok_s"], sid) for m, sid in rows if feasible(m, b, bg["llama32_3b"])]
        rows.sort(key=lambda r: (-r[0], r[1]))
        top[str(int(b))] = [sid for _, sid in rows[:TOP_N]]
    dec["stage1_top"] = top
    union = sorted(set(top["60"]) | set(top["35"]))
    stage2 = [_static_spec(chosen, w, sc, by_sid[sid]) for sid in union for w in WORKLOADS for sc in SCENES]
    if _missing(stage2, results):
        return ans(_missing(stage2, results), key="stage2")
    gb = {}
    for b in BUDGETS:
        best = None
        for sid in top[str(int(b))]:
            ms = [(results[_static_id(chosen, w, sc, sid)], w) for w in WORKLOADS for sc in SCENES]
            n_ok = sum(1 for m, w in ms if feasible(m, b, bg[w]))
            mean_tok = sum(m["tok_s"] for m, _ in ms) / len(ms)
            if best is None or (n_ok, mean_tok) > (best[0], best[1]):
                best = (n_ok, mean_tok, sid)
        gb[str(int(b))] = None if best is None else dict(setting=by_sid[best[2]], feasible_cells=best[0], of=6, feasible_in_all=best[0] == 6, mean_tok_s=best[1])
    dec["g_b"] = gb
    # ---- c'B constants and d'B margin (60 W cells on the 3 workloads x {S0, S1})
    cb_specs = [dict(id=f"cb_{w}_{sc}_t{t:g}_k{k:g}", kind="cB", workload=w, scene=sc, c0=chosen, params=dict(target=t, ki=k), budget_w=60.0)
                for t in CB_TARGETS for k in CB_KIS for w in WORKLOADS for sc in SCENES]
    if _missing(cb_specs, results):
        return ans(_missing(cb_specs, results), key="tune")
    combos = []
    for t in CB_TARGETS:
        for k in CB_KIS:
            ms = [results[f"cb_{w}_{sc}_t{t:g}_k{k:g}"] for w in WORKLOADS for sc in SCENES]
            combos.append(dict(params=dict(target=t, ki=k), miss=sum(m["miss"] for m in ms) / 6, power_w=sum(m["power_w"] for m in ms) / 6, tok_s=sum(m["tok_s"] for m in ms) / 6))
    ok = [c for c in combos if c["miss"] <= MISS_MAX and c["power_w"] <= 60.0]
    pick = max(ok, key=lambda c: (c["tok_s"], -c["params"]["target"], -c["params"]["ki"])) if ok else min(combos, key=lambda c: (c["miss"], -c["tok_s"]))
    dec["c_b"] = dict(pacing="auto (non-learned switch at 6.57 +- 0.3 ms measured frame time, dwell 5 s; plan addendum O-2)", params=dict(pick["params"], guard0=0.5, gmin=0.3), rule_met=bool(ok), mean_miss=pick["miss"], mean_tok_s=pick["tok_s"], mean_power_w=pick["power_w"], grid=combos)
    dec["d_b"] = "deferred to block T3b (addendum O-1: d'B action-space fix first)"           # DB_MARGINS and the margin rule (addendum O section 2) are applied in T3b
    return dict(batch=[], stop=None, decisions=dec)


def trial_specs():
    """Supervised hardware trial (not part of the plan, not data): one cell of every executor path - background alone, foreground alone, arm a, an aligned static, c'B and d'B (both switch pacing mode inside the cell) - at c0 = 7 on the 3B."""
    st = next(x for x in settings70() if x["sid"] == "1500_a_g1_d1")
    return [dict(id="trial_bgalone", kind="bg_alone", workload="llama32_3b", scene=None, c0=None),
            dict(id="trial_fgalone", kind="fg_alone", workload="llama32_3b", scene=None, c0=7),
            dict(id="trial_arma", kind="arm_a", workload="llama32_3b", scene="S1", c0=7),
            dict(id="trial_static", kind="static", workload="llama32_3b", scene="S1", c0=7, setting=st),
            dict(id="trial_cb", kind="cB", workload="llama32_3b", scene="S1", c0=7, params=dict(target=0.65, ki=0.15), budget_w=60.0),
            dict(id="trial_db", kind="dB", workload="llama32_3b", scene="S1", c0=7, params=dict(margin=0.2), budget_w=60.0)]


def diag_specs():
    """Diagnostic A/B (not data, not the plan; plan addendum O-4). Hypothesis: the Governor loop reads the NVML energy counter every tick (about 10 reads/s) and every extra read adds about 4.2 J of phantom
    energy (journal 0005), i.e. about +42 W on the counter. Arms (same g'B action, 3B, S1, c0 = 7): the static path (energy read twice), the Governor loop WITH its energy reads, the Governor loop WITHOUT energy
    reads, c'B with energy reads, and c'B on the sampled power source (the proposed fix). Each cell logs the energy-counter power, the independent sampled power and the Governor's read rate."""
    st = next(x for x in settings70() if x["sid"] == "1800_a_g0_d1")
    base = dict(workload="llama32_3b", scene="S1", c0=7, setting=st)
    cb = dict(kind="cB", workload="llama32_3b", scene="S1", c0=7, params=dict(target=0.5, ki=0.15), budget_w=60.0)
    return [dict(base, id="diag_static", kind="static"), dict(base, id="diag_gov_static", kind="gov_static", budget_w=60.0, power_source="energy"),
            dict(base, id="diag_gov_static_noenergy", kind="gov_static", budget_w=60.0, gov_no_energy=True),
            dict(cb, id="diag_cb", power_source="energy"), dict(cb, id="diag_cb_sampled", power_source="sampled")]


CB3_TARGETS = (0.35, 0.2)          # addendum O-6: the c'B grid extended below the lowest target of T3b (0.5), same ki values


def _choose_cb_grid(results, entries):
    """c'B constants rule (addendum O section 4) over entries = [(target, ki, id prefix)]: highest mean tok/s among the combinations with mean miss <= 1% and mean power <= 60 W, else the lowest mean miss.
    at_grid_edge: the chosen target is the lowest of the grid (the comparator may be under-tuned)."""
    combos = []
    for t, k, prefix in entries:
        ms = [results[f"{prefix}_{w}_{sc}_t{t:g}_k{k:g}"] for w in WORKLOADS for sc in SCENES]
        combos.append(dict(params=dict(target=t, ki=k), miss=sum(m["miss"] for m in ms) / 6, power_w=sum(m["power_w"] for m in ms) / 6, tok_s=sum(m["tok_s"] for m in ms) / 6))
    ok = [c for c in combos if c["miss"] <= MISS_MAX and c["power_w"] <= 60.0]
    pick = max(ok, key=lambda c: (c["tok_s"], -c["params"]["target"], -c["params"]["ki"])) if ok else min(combos, key=lambda c: (c["miss"], -c["tok_s"]))
    return dict(pacing="auto (non-learned, token-aware switch: period - clean token, +- 0.3 ms, dwell 5 s; plan addendum O-3)", params=dict(pick["params"], guard0=0.5, gmin=0.3), rule_met=bool(ok),
                mean_miss=pick["miss"], mean_tok_s=pick["tok_s"], mean_power_w=pick["power_w"], grid=combos, at_grid_edge=pick["params"]["target"] == min(t for t, _, _ in entries))


def _choose_cb(results, prefix):
    return _choose_cb_grid(results, [(t, k, prefix) for t in CB_TARGETS for k in CB_KIS])


def next_batch_t3b(results, c0):
    """Block T3b (plan addendum O-3): after the action-space fix, the clock clamp and the token-aware c'B threshold, at the chosen c0: one discarded cell, then the d'B margin grid (addendum O section 2:
    5 margins x 3 workloads x {S0, S1} at 60 W = 30 cells) and the c'B constants grid re-run under the final controller (36 cells; the sitting's c'B cells are void: old threshold and the governed-power anomaly).
    Same cell rules as T1-T3. Deterministic and resumable like next_batch."""
    dec = dict(c0=c0)
    disc = dict(id="t3b_discard", kind="arm_a", workload="llama32_3b", scene="S0", c0=c0, discard=True)
    if disc["id"] not in results:
        return dict(batch=[disc], stop=None, decisions=dec)
    db = [dict(id=f"db_{w}_{sc}_m{m:g}", kind="dB", workload=w, scene=sc, c0=c0, params=dict(margin=m), budget_w=60.0) for m in DB_MARGINS for w in WORKLOADS for sc in SCENES]
    cb = [dict(id=f"cb2_{w}_{sc}_t{t:g}_k{k:g}", kind="cB", workload=w, scene=sc, c0=c0, params=dict(target=t, ki=k), budget_w=60.0) for t in CB_TARGETS for k in CB_KIS for w in WORKLOADS for sc in SCENES]
    miss = _missing(db + cb, results)
    if miss:
        return dict(batch=_shuffled(miss, "t3b"), stop=None, decisions=dec)
    margins = []
    for m in DB_MARGINS:
        ms = [results[f"db_{w}_{sc}_m{m:g}"] for w in WORKLOADS for sc in SCENES]
        margins.append(dict(margin=m, mean_miss=sum(x["miss"] for x in ms) / 6, mean_tok_s=sum(x["tok_s"] for x in ms) / 6, mean_power_w=sum(x["power_w"] for x in ms) / 6))
    met = [r for r in margins if r["mean_miss"] <= MISS_MAX]
    dec["d_b"] = dict(margin=min(r["margin"] for r in met) if met else DB_MARGINS[-1], rule_met=bool(met), grid=margins)
    dec["c_b"] = _choose_cb(results, "cb2")
    return dict(batch=[], stop=None, decisions=dec)


def next_batch_t3c(results, c0):
    """Block T3c (plan addendum O-6, decided after T3b and before any evaluation block): the c'B grid extended to the targets 0.35 and 0.2 x ki {0.05, 0.15} on the same 6 workload / scene cells (24 cells,
    ids cb3_*) after one discarded cell; `results` must contain the cb2_* cells of T3b (merged read-only). The UNCHANGED choice rule is applied to the FULL grid (5 targets x 2 ki). One extension only."""
    dec = dict(c0=c0)
    disc = dict(id="t3c_discard", kind="arm_a", workload="llama32_3b", scene="S0", c0=c0, discard=True)
    if disc["id"] not in results:
        return dict(batch=[disc], stop=None, decisions=dec)
    cb = [dict(id=f"cb3_{w}_{sc}_t{t:g}_k{k:g}", kind="cB", workload=w, scene=sc, c0=c0, params=dict(target=t, ki=k), budget_w=60.0) for t in CB3_TARGETS for k in CB_KIS for w in WORKLOADS for sc in SCENES]
    miss = _missing(cb, results)
    if miss:
        return dict(batch=_shuffled(miss, "t3c"), stop=None, decisions=dec)
    entries = [(t, k, "cb3") for t in CB3_TARGETS for k in CB_KIS] + [(t, k, "cb2") for t in CB_TARGETS for k in CB_KIS]
    dec["c_b"] = _choose_cb_grid(results, entries)
    return dict(batch=[], stop=None, decisions=dec)
