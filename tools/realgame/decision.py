"""The R1 decision rule, implemented as written in docs/R1_PREREG.md (thresholds are constants below and are not to be tuned).

Inputs (all plain numbers; hitch is a share in percent):
  solo  : per rep a pair (opening SOLO cell, closing SOLO cell), each dict(p99=ms, hitch=%)
  arms  : dict arm -> per-rep list of dict(p99, hitch, toks); None (or absent) = arm not measured. Needs UNGATED. PRIO_IDLE, IGPU and DUTY50 are optional;
          DUTY50 is reference only and never enters a branch.
  llm_alone_toks, predictability_pass, prio_readbacks (every read-back of the PRIO_IDLE cells), idle_class.

Interpretations (the prereg is silent; each is also stated in the reasons or the report):
  * Values are rounded to 9 decimals before a threshold comparison so that float noise cannot flip "exactly 5%".
  * Noise relative difference = |SOLO1 - SOLO2| / mean(SOLO1, SOLO2); drift = (closing - opening), signed, relative to the same mean.
  * A "within limits" claim (branches 1, 2, 3) needs the noise precondition. The negative condition of branch 4 ("neither is within limits") uses the definition (a to c) without it.
  * UNGATED validity: tok/s strictly above 25% of the LLM-alone reference in every rep's cell AND no gap between consecutive token ends inside the window above 1 s
    (window edges included, see metrics.max_token_gap); each UNGATED cell dict must carry tokens_csv (path), t_open and t_close for the gap check, else ValueError.
    Otherwise the result is the pseudo-branch VOID (the prereg says the sweep is voided).
  * IGPU dropped (arm absent or None; amendment 11): nothing is forced to OPEN; branches 2, 3 and 4 are evaluated on PRIO_IDLE alone, result['igpu_tested'] is False and a reason says
    'IGPU option not tested'.
  * PRIO_IDLE is valid only if at least one read-back was recorded and all equal the idle class.
"""
import numpy as np

from tools.realgame import metrics

WORSEN_WITHIN, HITCH_WITHIN = 5.0, 0.5
WORSEN_REP_MAX, HITCH_REP_MAX = 10.0, 1.0
WORSEN_HARM, HITCH_HARM = 15.0, 2.0
NOISE_P99_PCT, NOISE_HITCH_PP, SOLO_HITCH_MAX = 2.5, 0.25, 1.0
PRIO_TOKS_RATIO, IGPU_TOKS_MIN = 0.70, 15.0
UNGATED_MIN_SHARE = 0.25
UNGATED_MAX_TOKEN_GAP_S = 1.0
BOOT_N, BOOT_SEED = 10000, 89770043
BRANCHES = ("NO_PROBLEM", "SIMPLE_FIX", "FIX_TOO_SLOW", "BUILD_THE_GATE", "OPEN")


def _r(x):
    return round(float(x), 9)


def _mean(xs):
    return _r(sum(xs) / len(xs))


def paired(solo, cells):
    """Per rep: p99 worsening (%) and hitch increase (pp) against the mean of that rep's two SOLO cells."""
    if len(solo) != len(cells):
        raise ValueError(f"{len(cells)} arm cells against {len(solo)} SOLO pairs: reps must match")
    out = []
    for (s1, s2), c in zip(solo, cells):
        ref_p99, ref_h = (s1["p99"] + s2["p99"]) / 2.0, (s1["hitch"] + s2["hitch"]) / 2.0
        out.append({"worsening_pct": _r((c["p99"] - ref_p99) / ref_p99 * 100.0), "hitch_pp": _r(c["hitch"] - ref_h), "toks": c.get("toks")})
    return out


def within_limits(p):
    return bool(_mean([x["worsening_pct"] for x in p]) < WORSEN_WITHIN and _mean([x["hitch_pp"] for x in p]) < HITCH_WITHIN
                and not any(x["worsening_pct"] >= WORSEN_REP_MAX or x["hitch_pp"] >= HITCH_REP_MAX for x in p))


def harmful(p):
    return bool(_mean([x["worsening_pct"] for x in p]) >= WORSEN_HARM and _mean([x["hitch_pp"] for x in p]) >= HITCH_HARM)


def noise_precondition(solo):
    """Noise precondition. The "SOLO hitch share below 1% in every rep" condition is applied to each SOLO cell (both the opening and the closing one), i.e. as implemented to the
    maximum of the rep's two SOLO hitch shares: max(s1, s2) < 1.0 for every rep."""
    rel = [abs(s1["p99"] - s2["p99"]) / ((s1["p99"] + s2["p99"]) / 2.0) * 100.0 for s1, s2 in solo]
    hd = [abs(s1["hitch"] - s2["hitch"]) for s1, s2 in solo]
    drift_p = [(s2["p99"] - s1["p99"]) / ((s1["p99"] + s2["p99"]) / 2.0) * 100.0 for s1, s2 in solo]
    drift_h = [s2["hitch"] - s1["hitch"] for s1, s2 in solo]
    solo_h_ok = all(max(s1["hitch"], s2["hitch"]) < SOLO_HITCH_MAX for s1, s2 in solo)
    p_mean, h_mean = _mean(rel), _mean(hd)
    return {"ok": bool(p_mean < NOISE_P99_PCT and h_mean < NOISE_HITCH_PP and solo_h_ok), "mean_abs_p99_diff_pct": p_mean, "mean_abs_hitch_diff_pp": h_mean,
            "solo_hitch_below_1pct_every_rep": solo_h_ok, "drift_p99_pct_mean": _mean(drift_p), "drift_hitch_pp_mean": _mean(drift_h),
            "drift_p99_pct_per_rep": [_r(x) for x in drift_p], "drift_hitch_pp_per_rep": [_r(x) for x in drift_h]}


def rep_noise_check(solo1_metrics, solo2_metrics):
    """Per-rep noise check (amendment 14), applied when a rep's closing SOLO finishes. Each argument is a dict with p99 (ms) and the hitch share in percent under 'hitch' or
    'hitch_share'. The rep FAILS if |p99a - p99b| / mean(p99) >= 2.5 %, or |hitch_a - hitch_b| >= 0.25 pp, or either SOLO hitch share is >= 1 % (values rounded to 9 decimals
    first, as elsewhere). -> (ok, reasons); reasons lists every clause that failed."""
    def hit(m):
        return m["hitch"] if "hitch" in m else m["hitch_share"]
    p1, p2, h1, h2 = float(solo1_metrics["p99"]), float(solo2_metrics["p99"]), float(hit(solo1_metrics)), float(hit(solo2_metrics))
    rel, hd = _r(abs(p1 - p2) / ((p1 + p2) / 2.0) * 100.0), _r(abs(h1 - h2))
    reasons = []
    if rel >= NOISE_P99_PCT:
        reasons.append(f"SOLO p99 difference {rel:.3f} % of the mean is not below {NOISE_P99_PCT} %")
    if hd >= NOISE_HITCH_PP:
        reasons.append(f"SOLO hitch-share difference {hd:.3f} pp is not below {NOISE_HITCH_PP} pp")
    for name, h in (("opening", h1), ("closing", h2)):
        if _r(h) >= SOLO_HITCH_MAX:
            reasons.append(f"{name} SOLO hitch share {_r(h):.3f} % is not below {SOLO_HITCH_MAX} %")
    return (not reasons), reasons


def summarize(values, seed=BOOT_SEED, n_boot=BOOT_N):
    """mean, median, worst rep (max) and a seeded percentile bootstrap (2.5 and 97.5 %) of the mean: for information only, it gates nothing."""
    v = np.asarray(values, dtype=float)
    rng = np.random.default_rng(seed)
    means = v[rng.integers(0, len(v), size=(n_boot, len(v)))].mean(axis=1)
    return {"mean": float(v.mean()), "median": float(np.median(v)), "worst": float(v.max()), "boot_lo": float(np.percentile(means, 2.5)),
            "boot_hi": float(np.percentile(means, 97.5)), "boot_n": n_boot, "boot_seed": seed, "values": [float(x) for x in v]}


def _arm_eval(solo, cells, noise_ok):
    p = paired(solo, cells)
    w, h = [x["worsening_pct"] for x in p], [x["hitch_pp"] for x in p]
    toks = [c.get("toks") for c in cells]
    wl = within_limits(p)
    return {"within_limits": wl, "within_claim": bool(wl and noise_ok), "harmful": harmful(p), "mean_worsening_pct": _mean(w), "mean_hitch_pp": _mean(h),
            "worsening_pct_stats": summarize(w), "hitch_pp_stats": summarize(h), "paired": p, "toks_mean": None if None in toks else _mean(toks)}


def evaluate(solo, arms, llm_alone_toks, predictability_pass, prio_readbacks, idle_class, seed=BOOT_SEED):
    if not arms.get("UNGATED"):
        raise ValueError("UNGATED cells are required")
    if not solo:
        raise ValueError("SOLO pairs are required")
    noise = noise_precondition(solo)
    ev = {n: _arm_eval(solo, cells, noise["ok"]) for n, cells in arms.items() if cells}
    if "DUTY50" in ev:
        ev["DUTY50"]["reference_only"] = True          # reported, never enters a branch
    reasons = []

    # validity
    ung_toks = [c["toks"] for c in arms["UNGATED"]]
    gaps = []
    for c in arms["UNGATED"]:
        if not c.get("tokens_csv") or c.get("t_open") is None or c.get("t_close") is None:
            raise ValueError("UNGATED validity needs the token CSV path (tokens_csv, t_open, t_close) of every UNGATED cell")
        gaps.append(metrics.max_token_gap(c["tokens_csv"], c["t_open"], c["t_close"]))
    ung_valid = all(t > UNGATED_MIN_SHARE * llm_alone_toks for t in ung_toks) and all(g <= UNGATED_MAX_TOKEN_GAP_S for g in gaps)
    prio_present = "PRIO_IDLE" in ev
    prio_valid = bool(prio_present and len(prio_readbacks) > 0 and all(r == idle_class for r in prio_readbacks))
    if prio_present and not prio_valid:
        ev["PRIO_IDLE"]["within_claim"] = False
        ev["PRIO_IDLE"]["void"] = True
        reasons.append(f"PRIO_IDLE void: read-backs {list(prio_readbacks)} are not all the idle class {idle_class}; it counts as not within limits and cannot support BUILD_THE_GATE")
    igpu_measured = "IGPU" in ev
    if not igpu_measured:
        reasons.append("IGPU option not tested: the IGPU arm was dropped (amendment 11), the branches are evaluated on PRIO_IDLE alone")
    result = {"noise": noise, "arms": ev, "ungated_valid": ung_valid, "ungated_max_token_gap_s": max(gaps), "prio_idle_valid": prio_valid, "igpu_measured": igpu_measured,
              "igpu_tested": igpu_measured, "llm_alone_toks": llm_alone_toks,
              "predictability_pass": bool(predictability_pass), "fix": None, "fixes": []}

    def done(branch, why):
        reasons.append(why)
        result.update(branch=branch, reasons=reasons)
        return result

    if not ung_valid:
        return done("VOID", f"sweep voided: UNGATED tok/s {ung_toks} is not above {UNGATED_MIN_SHARE:.0%} of the LLM-alone reference {llm_alone_toks} in every rep, or a token gap in {gaps} exceeds {UNGATED_MAX_TOKEN_GAP_S} s (gap check)")
    U = ev["UNGATED"]
    if U["within_claim"]:
        return done("NO_PROBLEM", "UNGATED is within limits and the noise precondition holds (this preset and this game only)")
    if U["within_limits"] and not noise["ok"]:
        reasons.append("UNGATED looks within limits but the noise precondition fails, so no within-limits claim is allowed")

    def qualifies(name):
        e = ev.get(name)
        if not e or not e["within_claim"]:
            return False
        if name == "PRIO_IDLE":
            ratios = [c["toks"] / u["toks"] for c, u in zip(arms["PRIO_IDLE"], arms["UNGATED"])]
            e["toks_ratio_to_ungated_mean"] = _mean(ratios)
            return e["toks_ratio_to_ungated_mean"] >= PRIO_TOKS_RATIO
        return e["toks_mean"] >= IGPU_TOKS_MIN

    result["fixes"] = [n for n in ("PRIO_IDLE", "IGPU") if qualifies(n)]
    if result["fixes"]:
        result["fix"] = max(result["fixes"], key=lambda n: ev[n]["toks_mean"])
        return done("SIMPLE_FIX", f"{' and '.join(result['fixes'])} within limits with enough throughput; the fix is {result['fix']} (higher tok/s)")
    any_within = [n for n in ("PRIO_IDLE", "IGPU") if n in ev and ev[n]["within_claim"]]
    if U["harmful"] and any_within:
        return done("FIX_TOO_SLOW", f"UNGATED is harmful and {' and '.join(any_within)} is within limits but misses its throughput condition")
    nominal_within = [n for n in ("PRIO_IDLE", "IGPU") if n in ev and ev[n]["within_limits"] and not ev[n].get("void")]
    gate = {"ungated_harmful": U["harmful"], "prio_idle_valid": prio_valid, "neither_within_limits": not nominal_within,
            "predictability_pass": bool(predictability_pass)}
    if all(gate.values()):
        return done("BUILD_THE_GATE", "UNGATED harmful, PRIO_IDLE valid, neither measured fix within limits" + ("" if igpu_measured else " (IGPU option not tested)") + ", predictability passes")
    return done("OPEN", "no earlier branch holds; unmet BUILD_THE_GATE conditions: " + (", ".join(k for k, v in gate.items() if not v) or "none"))


def decide(solo, arms, llm_alone_toks, predictability_pass, prio_readbacks, idle_class, seed=BOOT_SEED):
    r = evaluate(solo, arms, llm_alone_toks, predictability_pass, prio_readbacks, idle_class, seed)
    return r["branch"], r["reasons"]
