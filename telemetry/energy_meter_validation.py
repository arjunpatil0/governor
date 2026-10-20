#!/usr/bin/env python3
"""energy_meter_validation.py - check the units of Windows' PDH 'Energy Meter' RAPL counters on this Ryzen.

Protocol: all-core CPU spin for --load-s (60), then idle for --idle-s (60), logging
\\Energy Meter(rapl_package0_pkg)\\Power and \\Energy at --poll seconds.
Run with HWiNFO open (Sensors window, 'CPU Package Power'). The script tells you when to read it
(the stable part of each phase). Afterwards re-run the printout with:
    python telemetry\\energy_meter_validation.py --hwinfo-load <W> --hwinfo-idle <W> --from-csv <file>
Nothing here is assumed: the mW unit is a hypothesis printed next to what the data shows.
"""
import argparse, csv, json, statistics as st, subprocess, sys, time
from datetime import datetime, timezone
from pathlib import Path

import psutil
import win32pdh

DATA = Path(__file__).resolve().parents[1] / "data"
TRIM_S = 20  # drop the first seconds of each phase (ramp / thermal / governor transient)
# AMD publishes cTDP 35-54 W for the Ryzen 9 7940HS (recalled from the product page; verify before citing).
EXPECTED_LOAD_W = (35.0, 54.0)


def collect(load_s, idle_s, poll):
    q = win32pdh.OpenQuery()
    cp = win32pdh.AddCounter(q, r"\Energy Meter(rapl_package0_pkg)\Power")
    ce = win32pdh.AddCounter(q, r"\Energy Meter(rapl_package0_pkg)\Energy")
    rows, t0 = [], time.perf_counter()
    win32pdh.CollectQueryData(q)

    def phase(name, secs):
        start = time.perf_counter(); end = start + secs; announced = False
        print(f"\n=== phase: {name} for {secs:.0f} s ===", flush=True)
        while time.perf_counter() < end:
            time.sleep(poll)
            win32pdh.CollectQueryData(q)
            p = win32pdh.GetFormattedCounterValue(cp, win32pdh.PDH_FMT_DOUBLE)[1]
            e = win32pdh.GetFormattedCounterValue(ce, win32pdh.PDH_FMT_DOUBLE)[1]
            t = time.perf_counter() - t0
            rows.append(dict(t_s=round(t, 3), phase=name, power_raw=p, energy_raw=e))
            if not announced and name != "idle_pre" and time.perf_counter() > start + TRIM_S + 10:
                print(f"  >>> READ HWiNFO 'CPU Package Power' NOW and note it ({name})", flush=True)
                announced = True

    phase("idle_pre", 10.0)  # short pre-idle so the load phase starts from a cool baseline
    procs = [subprocess.Popen([sys.executable, "-c", "while 1: pass"]) for _ in range(psutil.cpu_count())]
    try:
        phase("load", load_s)
    finally:
        for p in procs:
            p.kill()
    phase("idle", idle_s)
    return rows


def summarise(rows, hw_load, hw_idle):
    out = {}
    print("\nphase      n   raw mean   raw median  raw p10..p90   as W if mW   dE/dt per s   dE/dt / raw")
    for name in ("idle_pre", "load", "idle"):
        r = [x for x in rows if x["phase"] == name]
        if not r:
            continue
        t_start = r[0]["t_s"]
        tr = [x for x in r if x["t_s"] - t_start >= TRIM_S] if name != "idle_pre" else r
        p = [x["power_raw"] for x in tr]
        de = tr[-1]["energy_raw"] - tr[0]["energy_raw"]; dt = tr[-1]["t_s"] - tr[0]["t_s"]
        s = sorted(p); lo, hi = s[int(.1 * (len(s) - 1))], s[int(.9 * (len(s) - 1))]
        rate = de / dt if dt else float("nan")
        out[name] = dict(n=len(p), raw_mean=st.mean(p), raw_median=st.median(p), raw_p10=lo, raw_p90=hi,
                         watts_if_mW=st.mean(p) / 1000, energy_rate_per_s=rate, rate_over_raw=rate / st.mean(p))
        print(f"{name:8s} {len(p):4d} {st.mean(p):10.0f} {st.median(p):12.0f}  {lo:6.0f}..{hi:<7.0f} {st.mean(p)/1000:9.2f} W {rate:13.0f} {rate/st.mean(p):12.1f}")
    print("\n(first 20 s of load/idle dropped as transient; idle_pre kept whole)")
    print("dE/dt / raw should be ~constant across phases (the two counters agree with each other). Its absolute value "
          "is the Energy counter's undocumented scale and says nothing about Power's unit; only HWiNFO can check that.")
    ld = out["load"]["watts_if_mW"]
    print("\n--- expected vs observed (assuming Power is in mW) ---")
    print(f"load : observed {ld:.1f} W | AMD cTDP range {EXPECTED_LOAD_W[0]:.0f}-{EXPECTED_LOAD_W[1]:.0f} W "
          f"-> {'inside' if EXPECTED_LOAD_W[0]*0.8 <= ld <= EXPECTED_LOAD_W[1]*1.3 else 'OUTSIDE'} the plausible band (-20%/+30%)")
    print(f"idle : observed {out['idle']['watts_if_mW']:.1f} W | no vendor figure; a laptop APU idling at a few W is typical, not a spec")
    for label, hw in (("load", hw_load), ("idle", hw_idle)):
        if hw:
            obs = out[label]["watts_if_mW"]
            print(f"HWiNFO {label}: {hw:.1f} W vs Energy Meter {obs:.1f} W  ratio {obs/hw:.2f}  "
                  f"({'units look right (mW)' if 0.8 <= obs/hw <= 1.25 else 'MISMATCH - units or scope differ'})")
    if not (hw_load or hw_idle):
        print("HWiNFO values not supplied yet: re-run with --hwinfo-load/--hwinfo-idle and --from-csv <this csv>.")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--load-s", type=float, default=60.0)
    ap.add_argument("--idle-s", type=float, default=60.0)
    ap.add_argument("--poll", type=float, default=0.5)
    ap.add_argument("--hwinfo-load", type=float, help="HWiNFO CPU Package Power (W) read during the load phase")
    ap.add_argument("--hwinfo-idle", type=float, help="HWiNFO CPU Package Power (W) read during the idle phase")
    ap.add_argument("--from-csv", help="re-print the summary from an earlier run instead of measuring")
    a = ap.parse_args()
    DATA.mkdir(exist_ok=True)
    batt = psutil.sensors_battery()
    if a.from_csv:
        rows = [{k: (v if k == "phase" else float(v)) for k, v in r.items()} for r in csv.DictReader(open(a.from_csv))]
        csv_path = Path(a.from_csv)
    else:
        print(f"AC plugged: {None if batt is None else batt.power_plugged}. Close heavy apps; leave the laptop alone for ~{a.load_s + a.idle_s + 10:.0f} s.")
        rows = collect(a.load_s, a.idle_s, a.poll)
        csv_path = DATA / f"energy_meter_validation_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.csv"
        with open(csv_path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["t_s", "phase", "power_raw", "energy_raw"]); w.writeheader(); w.writerows(rows)
    summ = summarise(rows, a.hwinfo_load, a.hwinfo_idle)
    csv_path.with_suffix(".json").write_text(json.dumps(dict(csv=csv_path.name, hwinfo_load_w=a.hwinfo_load,
                                                              hwinfo_idle_w=a.hwinfo_idle, summary=summ), indent=2))
    print(f"\nlogged: {csv_path}")


if __name__ == "__main__":
    main()
