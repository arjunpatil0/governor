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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    r = check(ap.parse_args().out)
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
