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
        if ps is not None and ps == ps and m.get("power_w") == m.get("power_w") and m.get("power_w") is not None and abs(m["power_w"] - ps) / max(ps, 1e-9) > 0.15:
            flags.append(f"{cid}: energy-counter power {m['power_w']:.1f} W vs sampled {ps:.1f} W (differ by more than 15%)")
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


DIAG_IDS = ("diag_static", "diag_gov_static", "diag_gov_static_noenergy", "diag_cb")


def diag_gate(out):
    """Gate for block T3b (plan addendum O-3 section 2): the same action through the Governor loop must draw within 15% of the static path, and in every diagnostic cell the energy-counter power must be
    within 15% of the independently sampled power. ok False with the reasons otherwise (also when a diagnostic cell is missing)."""
    out = Path(out)
    reasons, p = [], {}
    for cid in DIAG_IDS:
        f = out / "cells" / cid / "cell.json"
        if not f.exists():
            reasons.append(f"{cid}: cell missing")
            continue
        m = json.loads(f.read_text(encoding="utf-8"))["metrics"]
        p[cid] = m
        w, s = m.get("power_w"), m.get("power_sampled_w")
        if w is None or s is None or w != w or s != s or abs(w - s) / max(s, 1e-9) > 0.15:
            reasons.append(f"{cid}: energy-counter power {w} W vs sampled {s} W (differ by more than 15%, or missing)")
    if "diag_static" in p and "diag_gov_static" in p:
        a, b = p["diag_static"]["power_w"], p["diag_gov_static"]["power_w"]
        if abs(b - a) / max(a, 1e-9) > 0.15:
            reasons.append(f"diag_gov_static: {b:.1f} W through the Governor loop vs {a:.1f} W through the static path (differ by more than 15%)")
    return dict(ok=not reasons, reasons=reasons, power={k: (v.get("power_w"), v.get("power_sampled_w"), v.get("tok_s")) for k, v in p.items()})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--gate", choices=["diag"], default=None, help="diag: check the diagnostic A/B (exit code 0 = T3b may start, 1 = it must not)")
    a = ap.parse_args()
    if a.gate == "diag":
        g = diag_gate(a.out)
        for k, v in g["power"].items():
            print(f"{k}: energy-counter {v[0]} W, sampled {v[1]} W, {v[2]} tok/s")
        print("DIAG GATE:", "PASS - T3b may start" if g["ok"] else "FAIL - T3b must NOT start")
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
