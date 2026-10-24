"""Morning check of a W5b tuning sitting (tests/test_w5b_morning.py).   python experiments/w5b/morning.py --out data/w5b/tuning
Prints counts, the c0 search, the decisions, incidents and per-cell flags (thermal/power-brake bits, clock not applied, abandoned frames, ring drops, temperature >= 83 C) and checks the manifest."""
import argparse
import hashlib
import json
from pathlib import Path


def check(out):
    out = Path(out)
    problems, flags, n, clamp = [], [], 0, [0, 0]
    for p in sorted((out / "cells").glob("*/cell.json")) if (out / "cells").exists() else []:
        d = json.loads(p.read_text(encoding="utf-8"))
        m, cid = d["metrics"], d["id"]
        n += 1
        if m.get("thermal_reason_bits"):
            flags.append(f"{cid}: thermal/power-brake reason bits {m['thermal_reason_bits']:#x}")
        if m.get("clock_ok") is False:
            flags.append(f"{cid}: clock_ok False")
        if m.get("abandoned"):
            flags.append(f"{cid}: abandoned frames {m['abandoned']}")
        if m.get("ring_dropped"):
            flags.append(f"{cid}: ring_dropped {m['ring_dropped']}")
        if (m.get("temp_after_c") or 0) >= 83:
            flags.append(f"{cid}: temp_after_c {m['temp_after_c']}")
        ps = m.get("power_sampled_w")
        if ps is not None and ps == ps and m.get("power_w") == m.get("power_w") and m.get("power_w") is not None and abs(m["power_w"] - ps) / max(ps, 1e-9) > 0.15 and not cid.startswith("diag_"):
            problems.append(f"{cid}: energy-counter power {m['power_w']:.1f} W vs sampled {ps:.1f} W (differ by more than 15%: the cell's power is not credible)")
        if (m.get("gov_reads") or 0) > 0 and not cid.startswith("diag_"):
            problems.append(f"{cid}: the Governor loop read the energy counter {m['gov_reads']} times (plan addendum O-5: governed cells never read it; the cell's start/end power and its controllers' power signal are not comparable)")
        r0 = m.get("c0m_over_nominal")
        if r0 is not None and not (0.85 <= r0 <= 1.15):
            flags.append(f"{cid}: c0m at a locked 1800 MHz is {r0:.2f} x nominal c0 (expected about 1.0: the FMA calibration may be off)")
        if m.get("clamp_events"):
            clamp[0] += m["clamp_events"]; clamp[1] += 1
        em = m.get("exec_mode")
        if m.get("executor") == "hw" and d["spec"].get("kind") not in ("fg_alone",) and (not em or len(set(em.split("offloaded=")[1].split()[0].split("/"))) != 1):
            flags.append(f"{cid}: exec_mode not full offload ({em})")
    for p in sorted((out / "cells").glob("*/incident.json")) if (out / "cells").exists() else []:
        problems.append(f"incident file {p.parent.name}: {p.read_text(encoding='utf-8')[:200]}")
    dec = None
    if not (out / "decisions.json").exists():
        problems.append("decisions.json missing: the sitting did not finish (re-run the same command to resume)")
    else:
        dec = json.loads((out / "decisions.json").read_text(encoding="utf-8"))
        if dec.get("stop"):
            problems.append(f"stop report: {dec['stop']}")
    mp = out / "manifest.json"
    if not mp.exists():
        problems.append("manifest.json missing")
    else:
        man = {k.replace(chr(92), "/"): v for k, v in json.loads(mp.read_text(encoding="utf-8")).items()}
        for k, v in man.items():
            f = out / k
            if not f.exists() or hashlib.sha256(f.read_bytes()).hexdigest() != v:
                problems.append(f"manifest mismatch: {k}")
    meta = json.loads((out / "meta.json").read_text(encoding="utf-8")) if (out / "meta.json").exists() else {}
    return dict(cells=n, clamp_events=clamp[0], cells_with_clamp=clamp[1], problems=problems, flags=flags, decisions=dec, meta={k: meta.get(k) for k in ("armoury_mode", "battery_charge_mode", "boot_utc", "uptime_s", "sitting_start_utc", "chrome_running", "exe_sha256", "git_head")})


DIAG_IDS = ("diag_static", "diag_gov_static", "diag_gov_static_noenergy", "diag_cb", "diag_cb_sampled")
PHANTOM_J_PER_READ = 4.2          # journal 0005: ~4.2 J per extra read in THAT state. STATE-DEPENDENT (diag 2026-10-24: ~7.5 J/read in the g'B state, ~2.7 J/read in the c'B state; addendum O-5): a prediction constant of O-4, not a law
TOL_REL = 0.15                    # agreement between two measurements of the same power
TOL_PRED_REL, TOL_PRED_ABS_W = 0.35, 5.0     # observed inflation vs 4.2 J x reads/s


def diag_gate(out):
    """Gate for block T3b, pre-registered in plan addendum O-4 (docs/W5B_ADDENDUM_O4.md).
    PREDICTION (phantom energy): on the arms whose Governor loop reads the energy counter (diag_gov_static, diag_cb) the counter power exceeds the independent sampled mean by 4.2 J x (reads/s) within
    max(35%, 5 W), and exceeds the static arm by the same amount (diag_gov_static); the no-reads arm matches the static arm within 15%; the sampled mean is not inflated (all arms within 15% of the static arm's
    sampled mean, c'B arms excepted: a controller may change the load); the fix arm (diag_cb_sampled) has counter power within 15% of its sampled mean.
    VERDICTS: CONFIRMED_PHANTOM (prediction holds) -> power_source 'sampled'; NO_ANOMALY (every arm's counter agrees with its sampled mean and the Governor arm matches the static arm) -> 'energy';
    anything else -> STOP (a new problem). Writes power_source.json next to the cells and returns the printable lines."""
    out = Path(out)
    reasons, p = [], {}
    for cid in DIAG_IDS:
        f = out / "cells" / cid / "cell.json"
        if not f.exists():
            reasons.append(f"{cid}: cell missing")
            continue
        p[cid] = json.loads(f.read_text(encoding="utf-8"))["metrics"]
    res = dict(ok=False, verdict="STOP", power_source=None, reasons=reasons, lines=[], predicted_inflation_w=None, observed_inflation_w=None)
    for cid, m in p.items():
        for key in ("power_w", "power_sampled_w"):
            v = m.get(key)
            if v is None or v != v:
                reasons.append(f"{cid}: {key} missing (a simulator cell, or the sampler did not run)")
    if reasons:
        return res
    E = {k: float(v["power_w"]) for k, v in p.items()}
    M = {k: float(v["power_sampled_w"]) for k, v in p.items()}
    R = {k: float(v.get("gov_reads_per_s") or 0.0) for k, v in p.items()}
    pred = PHANTOM_J_PER_READ * R["diag_gov_static"]
    obs = E["diag_gov_static"] - E["diag_static"]
    res.update(predicted_inflation_w=pred, observed_inflation_w=obs)
    for k in DIAG_IDS:
        res["lines"].append(f"{k}: energy-counter {E[k]:.1f} W | sampled mean {M[k]:.1f} W | counter - sampled {E[k] - M[k]:+.1f} W | governor energy reads/s {R[k]:.1f} | {p[k].get('tok_s', float('nan')):.1f} tok/s")
    tol = lambda x: max(TOL_PRED_REL * x, TOL_PRED_ABS_W)       # noqa: E731
    pred_c = PHANTOM_J_PER_READ * R["diag_cb"]
    res["lines"].append(f"predicted phantom inflation 4.2 J x {R['diag_gov_static']:.1f} reads/s = {pred:.1f} W; observed (governor arm - static arm) = {obs:+.1f} W; observed (counter - sampled, governor arm) = {E['diag_gov_static'] - M['diag_gov_static']:+.1f} W; "
                        f"c'B arm: predicted {pred_c:.1f} W, observed (counter - sampled) {E['diag_cb'] - M['diag_cb']:+.1f} W")
    agree = {k: abs(E[k] - M[k]) / max(M[k], 1e-9) <= TOL_REL for k in DIAG_IDS}
    gov_matches_static = abs(E["diag_gov_static"] - E["diag_static"]) / max(E["diag_static"], 1e-9) <= TOL_REL
    if all(agree.values()) and gov_matches_static:
        res.update(ok=True, verdict="NO_ANOMALY", power_source="energy")
    else:
        bad = []
        if not agree["diag_static"]:
            bad.append("diag_static: the static arm's counter and sampled power disagree (no reference)")
        if abs(E["diag_gov_static_noenergy"] - E["diag_static"]) / max(E["diag_static"], 1e-9) > TOL_REL:
            bad.append("diag_gov_static_noenergy: the Governor arm WITHOUT energy reads is also off the static arm: not the phantom energy, a new problem")
        for k in ("diag_gov_static", "diag_gov_static_noenergy"):
            if abs(M[k] - M["diag_static"]) / max(M["diag_static"], 1e-9) > TOL_REL:
                bad.append(f"{k}: the SAMPLED power is inflated against the static arm: the load is real or the sampled source is also affected")
        if abs((E["diag_gov_static"] - M["diag_gov_static"]) - pred) > tol(pred) or abs(obs - pred) > tol(pred):
            bad.append(f"diag_gov_static: inflation {obs:+.1f} W (counter - static) / {E['diag_gov_static'] - M['diag_gov_static']:+.1f} W (counter - sampled) does not match the prediction {pred:.1f} W")
        if abs((E["diag_cb"] - M["diag_cb"]) - pred_c) > tol(pred_c):
            bad.append(f"diag_cb: inflation {E['diag_cb'] - M['diag_cb']:+.1f} W does not match the prediction {pred_c:.1f} W")
        if not agree["diag_cb_sampled"]:
            bad.append("diag_cb_sampled: the proposed fix arm's counter power still disagrees with its sampled power")
        if bad:
            res["reasons"] = bad
        else:
            res.update(ok=True, verdict="CONFIRMED_PHANTOM", power_source="sampled")
    if res["ok"]:                                              # both passing verdicts: the same action must make the same tokens on the Governor path (the diagnosis claims the phantom power starved the background)
        ts, tn = float(p["diag_static"].get("tok_s") or 0.0), float(p["diag_gov_static_noenergy"].get("tok_s") or 0.0)
        if not (max(ts, tn) < 1.0 or abs(tn - ts) / max(ts, 1e-9) <= TOL_REL):
            res.update(ok=False, verdict="STOP", power_source=None)
            res["reasons"] = list(res["reasons"]) + [f"diag_gov_static_noenergy: {tn:.1f} tok/s vs {ts:.1f} tok/s on the static path (differ by more than 15%): throughput differs on the Governor path for reasons other than power"]
    res["lines"].append(f"diag_cb vs diag_cb_sampled: {p['diag_cb'].get('tok_s', float('nan')):.1f} tok/s (energy source) vs {p['diag_cb_sampled'].get('tok_s', float('nan')):.1f} tok/s (sampled source) - reported, not gated: "
                        "the direct evidence whether the fix restores the background")
    (out / "power_source.json").write_text(json.dumps(dict(power_source=res["power_source"], verdict=res["verdict"], predicted_inflation_w=pred, observed_inflation_w=obs, reasons=res["reasons"]), indent=1), encoding="utf-8")
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--gate", choices=["diag"], default=None, help="diag: check the diagnostic A/B (exit code 0 = T3b may start, 1 = it must not)")
    a = ap.parse_args()
    if a.gate == "diag":
        g = diag_gate(a.out)
        for line in g["lines"]:
            print(line)
        print("DIAG GATE:", g["verdict"], "-", ("T3b runs with the power source '%s'" % g["power_source"]) if g["ok"] else "T3b must NOT start")
        for x in g["reasons"]:
            print("  reason:", x)
        raise SystemExit(0 if g["ok"] else 1)
    r = check(a.out)
    print(f"cells {r['cells']}  problems {len(r['problems'])}  flags {len(r['flags'])}")
    print("meta", r["meta"])
    print(f"INFO live clock clamped to the model range {r['clamp_events']} times in {r['cells_with_clamp']} governed cells (expected when the clock is unlocked: it reads about 2475 MHz)")
    d = r["decisions"]
    if d:
        print("c0", d.get("c0"), "c0m", d.get("c0m"), "stop", d.get("stop"))
        for t in d.get("c0_search", []):
            print("  c0 search", t)
        print("g_b", {b: (g and g["setting"]["sid"]) for b, g in (d.get("g_b") or {}).items()})
        print("c_b", d.get("c_b", {}).get("pacing"), d.get("c_b", {}).get("params"), "rule_met", d.get("c_b", {}).get("rule_met"))
        print("d_b", d.get("d_b"))
    for x in r["problems"]:
        print("PROBLEM", x)
    for x in r["flags"]:
        print("FLAG", x)


if __name__ == "__main__":
    main()
