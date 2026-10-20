#!/usr/bin/env python3
"""power_energy_diagnostic.py - why do the NVML energy counter and 20 Hz power samples disagree? (review finding 1)

Lesson that shaped this script: reading nvmlDeviceGetTotalEnergyConsumption at high rate INFLATES the counter
(~4-6 J of phantom energy per read on this machine), so a 100 Hz energy trace is meaningless. Therefore:

Experiment A (transient): power signals (nvmlDeviceGetPowerUsage, POWER_AVERAGE, POWER_INSTANT) at ~100 Hz, which
  was verified not to disturb anything, and the energy counter read once per second only. 3 s idle (CUDA ctx alive),
  12 s constant fma load, 4 s idle. Shows how fast each power signal follows the load.
Experiment B (counter bias): energy-counter rate with only two reads (start/end) vs mean power samples, in three states
  (no CUDA context / context idle / fma steady), plus a read-rate sweep (1, 5, 20, 100 Hz) during fma steady to
  estimate phantom joules per read.
Output: data/diagnostics/power_energy_<UTC>.csv (experiment A raw), summary json and .png
"""
import csv, ctypes, json, statistics as st, sys, threading, time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pynvml as nv

ROOT = Path(__file__).resolve().parents[1]
DLL = ROOT / "workloads" / "background" / "build" / "bench_kernels.dll"
IDLE_PRE, LOAD, IDLE_POST, HZ = 3.0, 12.0, 4.0, 100


def counter_rate(h, secs, read_hz=None):
    """Energy-counter rate (W) over `secs`: two reads (start/end), or additionally reads at read_hz in between.
    Power polled at 2 Hz alongside (verified not to disturb the counter). Returns (W_counter, W_power_mean, n_extra_reads)."""
    ps, n = [], 0
    e0 = nv.nvmlDeviceGetTotalEnergyConsumption(h); t0 = time.perf_counter()
    while time.perf_counter() - t0 < secs:
        if read_hz:
            nv.nvmlDeviceGetTotalEnergyConsumption(h); n += 1
            ps.append(nv.nvmlDeviceGetPowerUsage(h) / 1000); time.sleep(1.0 / read_hz)
        else:
            ps.append(nv.nvmlDeviceGetPowerUsage(h) / 1000); time.sleep(0.5)
    e1 = nv.nvmlDeviceGetTotalEnergyConsumption(h); dt = time.perf_counter() - t0
    return (e1 - e0) / 1000.0 / dt, st.mean(ps), n / dt


def main():
    nv.nvmlInit(); h = nv.nvmlDeviceGetHandleByIndex(0)
    summary = {"states": {}, "sweep": []}
    print("Experiment B1: counter vs power samples (two energy reads per window)")
    for rep in range(2):
        c, p, _ = counter_rate(h, 8.0)
        summary["states"].setdefault("no_cuda_context_idle", []).append((c, p))
        print(f"  no CUDA context, idle   : counter {c:5.1f} W | power samples {p:5.1f} W")

    dll = ctypes.CDLL(str(DLL)); dll.bench_last_error.restype = ctypes.c_char_p
    sms = ctypes.c_int()
    if dll.bench_init(ctypes.byref(sms)) != 0:
        sys.exit(f"FATAL bench_init: {dll.bench_last_error().decode()} (no CPU fallback)")
    w, g, ws, cs = (ctypes.c_double() for _ in range(4))
    c, p, _ = counter_rate(h, 8.0)
    summary["states"]["cuda_context_idle"] = [(c, p)]
    print(f"  CUDA context, no kernel : counter {c:5.1f} W | power samples {p:5.1f} W")

    # ---------------- Experiment A: transient
    fids = [nv.NVML_FI_DEV_POWER_AVERAGE, nv.NVML_FI_DEV_POWER_INSTANT]
    rows, e_pts, stop, t0 = [], [], threading.Event(), time.perf_counter()

    log_errors = []

    def log():
        nxt_e = 0.0
        try:
            while not stop.is_set():
                now = time.perf_counter() - t0
                fv = nv.nvmlDeviceGetFieldValues(h, fids)
                rows.append((now, nv.nvmlDeviceGetPowerUsage(h), fv[0].value.uiVal, fv[1].value.uiVal,
                             nv.nvmlDeviceGetClockInfo(h, nv.NVML_CLOCK_SM)))
                if now >= nxt_e:  # 1 Hz only: every energy read adds ~4 J of phantom energy
                    e_pts.append((now, nv.nvmlDeviceGetTotalEnergyConsumption(h))); nxt_e += 1.0
                time.sleep(1.0 / HZ)
        except Exception as e:  # noqa: BLE001 - a dead logger must fail the run, not leave an empty array
            log_errors.append(e)
    th = threading.Thread(target=log, daemon=True); th.start()
    time.sleep(IDLE_PRE)
    t_l0 = time.perf_counter() - t0
    dll.bench_run(1, ctypes.c_double(LOAD), *(ctypes.byref(x) for x in (w, g, ws, cs)))
    t_l1 = time.perf_counter() - t0
    time.sleep(IDLE_POST)
    stop.set(); th.join()
    if log_errors or not rows:
        dll.bench_free()
        sys.exit(f"FATAL: logger thread failed or produced no rows: {log_errors[:1]}")

    a = np.array(rows); t, p_api, p_avg, p_inst, sm = a.T
    ep = np.array(e_pts); te = ep[:, 0]; e_rate = np.diff(ep[:, 1]) / 1000.0 / np.diff(te)  # W per 1 s segment (includes ~5 W of read cost)
    print(f"\nExperiment A: load {t_l0:.1f}-{t_l1:.1f} s; power signals {len(a)/t[-1]:.0f} Hz achieved, energy read 1 Hz")
    for nm, sig in (("power_api", p_api), ("avg_field", p_avg), ("inst_field", p_inst)):
        ch = np.flatnonzero(np.diff(sig) != 0) + 1
        d = np.diff(t[ch]) * 1e3
        steady = sig[np.searchsorted(t, t_l1 - 4):np.searchsorted(t, t_l1 - 0.2)].mean() / 1000
        base = sig[np.searchsorted(t, 0.5):np.searchsorted(t, t_l0 - 0.2)].mean() / 1000
        idx = np.flatnonzero((t > t_l0) & (sig / 1000 >= base + 0.9 * (steady - base)))
        lag = t[idx[0]] - t_l0 if len(idx) else float("nan")
        print(f"  {nm:10s} updates every {np.median(d):4.0f} ms (p90 {np.percentile(d,90):4.0f}); idle {base:5.1f} W -> steady {steady:5.1f} W; "
              f"t90 = {lag:.2f} s after load start")
        summary[nm] = dict(update_ms_median=float(np.median(d)), t90_s=float(lag), idle_w=float(base), steady_w=float(steady))
    print("  harness-like windows, sample mean vs steady fma counter rate measured in B2 below (computed after B2)")

    # ---------------- Experiment B2: sweep during steady fma
    th2 = threading.Thread(target=lambda: dll.bench_run(1, ctypes.c_double(75), *(ctypes.byref(x) for x in (w, g, ws, cs))), daemon=True)
    th2.start(); time.sleep(5)
    print("\nExperiment B2: fma steady, counter rate vs energy-read frequency")
    for rep in range(2):
        c, p, _ = counter_rate(h, 8.0)
        summary["states"].setdefault("fma_steady", []).append((c, p))
        print(f"  two reads only          : counter {c:5.1f} W | power samples {p:5.1f} W")
    for hz in (1, 5, 20, 100):
        c, p, rr = counter_rate(h, 6.0, read_hz=hz)
        summary["sweep"].append((rr, c, p))
        print(f"  extra reads {rr:5.1f} Hz     : counter {c:5.1f} W | power samples {p:5.1f} W")
    th2.join(); dll.bench_free()
    sw = np.array(summary["sweep"])
    slope, icpt = np.polyfit(sw[:, 0], sw[:, 1], 1)
    print(f"  linear fit: counter ~= {icpt:.1f} W + {slope:.2f} J/read * read_rate  (phantom energy per extra read)")
    summary["phantom_j_per_read"] = float(slope); summary["fit_intercept_w"] = float(icpt)

    base_fma = np.mean([c for c, _ in summary["states"]["fma_steady"]])
    print("\nHarness-like windows for experiment A (power-sample mean at 20 Hz vs steady counter rate "
          f"{base_fma:.1f} W from two-read windows):")
    for off, length in ((0.5, 1.0), (0.5, 4.0), (1.5, 4.0), (3.0, 4.0)):
        m = (t >= t_l0 + off) & (t < t_l0 + off + length)
        ps = p_api[m][::5].mean() / 1000
        print(f"  +{off:3.1f} s, {length:3.1f} s window: samples {ps:5.1f} W vs counter {base_fma:5.1f} W -> {100*(ps-base_fma)/base_fma:+5.1f}%")

    out = ROOT / "data" / "diagnostics"; out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    with open(out / f"power_energy_{stamp}.csv", "w", newline="") as f:
        wr = csv.writer(f); wr.writerow(["t_s", "power_api_mw", "power_avg_field_mw", "power_inst_field_mw", "sm_mhz"]); wr.writerows(rows)
    (out / f"power_energy_{stamp}.json").write_text(json.dumps(summary, indent=2, default=float))

    import matplotlib; matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(3, 1, figsize=(11, 11), gridspec_kw={"height_ratios": [2.6, 1.6, 1.8]})
    ax[0].plot(t, p_api / 1000, label="nvmlDeviceGetPowerUsage (what run.py samples)", color="tab:red", lw=1.2)
    ax[0].plot(t, p_avg / 1000, label="field POWER_AVERAGE", color="tab:blue", ls="--", lw=1)
    ax[0].plot(t, p_inst / 1000, label="field POWER_INSTANT", color="tab:green", ls=":", lw=1.4)
    ax[0].step(te[1:], e_rate, where="pre", color="black", lw=1.6, label="energy counter, 1 s segments (includes read cost)")
    ax[0].axvspan(t_l0, t_l1, color="gold", alpha=0.15); ax[0].set_ylabel("GPU power (W)"); ax[0].set_xlabel("time (s); shaded = constant fma load")
    ax[0].set_title("A: how fast do the power signals follow a load step?"); ax[0].legend(fontsize=8, loc="center right")
    ax[1].plot(t, sm, color="tab:purple"); ax[1].axvspan(t_l0, t_l1, color="gold", alpha=0.15); ax[1].set_ylabel("SM clock (MHz)"); ax[1].set_xlabel("time (s)")
    ax[2].plot(sw[:, 0], sw[:, 1], "o-", color="black", label="energy counter rate (W)")
    ax[2].axhline(np.mean(sw[:, 2]), color="tab:red", ls="--", label="mean power samples (W)")
    xs = np.linspace(0, sw[:, 0].max(), 10); ax[2].plot(xs, icpt + slope * xs, color="gray", ls=":", label=f"fit: {slope:.1f} J phantom per read")
    ax[2].set_xlabel("extra energy-counter reads per second"); ax[2].set_ylabel("W"); ax[2].legend(fontsize=8)
    ax[2].set_title("B2: reading the counter more often inflates it (fma steady)")
    fig.tight_layout(); png = out / f"power_energy_{stamp}.png"; fig.savefig(png, dpi=110)
    print(f"\nlogged: {out / ('power_energy_' + stamp + '.csv')}\nplot:   {png}")


if __name__ == "__main__":
    main()
