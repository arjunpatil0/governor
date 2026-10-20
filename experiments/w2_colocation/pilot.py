#!/usr/bin/env python3
"""W2 pilot (NOT a result; journal 0008). Feasibility + calibration only, before w2_colocation.yaml is registered.
It may fix kernel unit counts and show whether the design is runnable; it must not be used to set hypotheses or thresholds.
Unlocked clock, no admin needed. Output: data/pilot/w2/<UTC>/ (pilot.json + csv). Run: python experiments\\w2_colocation\\pilot.py
Parts: P0 env/HAGS/timer, P1 slice calibration, P2 slice generator accuracy, P3 isolated foreground, P4 frame sizing,
       P5 two-process co-run feasibility (one cell), P6 decode proxy timing.
"""
import argparse, ctypes, json, subprocess, sys, tempfile, time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import psutil
import pynvml as nv

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "telemetry")); sys.path.insert(0, str(ROOT / "workloads" / "common"))
from loadgen import gamma_slice_durations, latencies, parse_hags, poisson_arrivals, residual_wait  # noqa: E402
from provenance import check_run_provenance  # noqa: E402

from w2lib import BPS, W2, calibrate, dbl, units_for  # noqa: E402  (shared wrapper; DLL path lives there)
DLL = ROOT / "workloads" / "background" / "build" / "w2_kernels.dll"
P = ctypes.POINTER


def pct(a, q):
    return float(np.percentile(a, q))


def role_bg(args):
    w = W2(); u = np.load(args.units)
    ts, te, g = w.bg_until(args.kind, u, args.t_stop)
    np.savetxt(args.out, np.c_[ts, te, g], delimiter=",", header="t_start,t_end,gpu_ms", comments="")


def role_fg(args):
    w = W2()
    a = poisson_arrivals(args.rate, args.n, args.seed, t0=args.t_begin)
    tl, tc, g = w.fg_run(args.kind, a, args.units_fg, bps=args.bps)
    np.savetxt(args.out, np.c_[a, tl, tc, g], delimiter=",", header="arrival,t_launch,t_complete,gpu_ms", comments="")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--role"); ap.add_argument("--units"); ap.add_argument("--kind", type=int); ap.add_argument("--t_stop", type=float)
    ap.add_argument("--out"); ap.add_argument("--rate", type=float); ap.add_argument("--n", type=int); ap.add_argument("--seed", type=int)
    ap.add_argument("--t_begin", type=float); ap.add_argument("--bps", type=int, default=BPS)
    ap.add_argument("--units_n", dest="units_fg", type=int)
    a = ap.parse_args()
    if a.role == "bg":
        return role_bg(a)
    if a.role == "fg":
        return role_fg(a)

    git_head = check_run_provenance(ROOT, smoke=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = ROOT / "data" / "pilot" / "w2" / stamp; out.mkdir(parents=True)
    nv.nvmlInit(); h = nv.nvmlDeviceGetHandleByIndex(0)
    snap = lambda: dict(temp_c=nv.nvmlDeviceGetTemperature(h, nv.NVML_TEMPERATURE_GPU),
                        sm_mhz=nv.nvmlDeviceGetClockInfo(h, nv.NVML_CLOCK_SM), mem_mhz=nv.nvmlDeviceGetClockInfo(h, nv.NVML_CLOCK_MEM))
    R = dict(utc=stamp, git_head=git_head, pilot=True, execution_mode="CUDA native kernels via w2_kernels.dll (no CPU fallback)")
    w = W2(); R["sm_count"] = w.sms

    # ---- P0
    dxd = Path(tempfile.gettempdir()) / f"dxdiag_pilot_{stamp}.txt"
    subprocess.run(["dxdiag", "/t", str(dxd)], check=True)
    for _ in range(60):
        if dxd.exists() and dxd.stat().st_size > 1000: break
        time.sleep(1)
    time.sleep(2)
    R["hags"] = parse_hags(dxd.read_text(errors="ignore"))
    skew = [abs(w.d.w2_qpc_now() - time.perf_counter()) for _ in range(1000)]
    R["qpc_vs_perf_counter_max_skew_us"] = max(skew) * 1e6
    R["env_start"] = snap(); print("P0", R["hags"], f"timer skew max {R['qpc_vs_perf_counter_max_skew_us']:.1f} us", R["env_start"])
    w.bg_until(1, [20000], w.d.w2_qpc_now() + 5)   # warm-up to boost clocks

    # ---- P1 calibration (host-visible slice duration vs units)
    cal = {"fma": calibrate(w, 1, [2000, 8000, 32000, 64000]), "mem": calibrate(w, 0, [200, 800, 2000, 4096, 8192])}
    R["calibration"] = cal; print("P1", {k: (round(v["a_ms"], 4), round(v["b_ms_per_unit"], 6)) for k, v in cal.items()})

    # ---- P2 slice generator accuracy: nominal vs realised, rho, gaps
    P2 = []
    for kind, nm in ((1, "fma"), (0, "mem")):
        for m in (0.25, 1.0, 4.0):
            for cv in (0.0, 1.0):
                dur = gamma_slice_durations(4000, m, cv, seed=11)
                u = units_for(cal[nm], dur)
                ts, te, g = w.bg_until(kind, u, w.d.w2_qpc_now() + 3.0, bps=BPS)
                r = residual_wait(ts, te); d = (te - ts) * 1e3
                P2.append(dict(kind=nm, nominal_mean_ms=m, nominal_cv=cv, n=int(len(d)), realised_mean_ms=float(d.mean()), realised_cv=float(d.std() / d.mean()),
                               gpu_mean_ms=float(g.mean()), rho=r["rho"], gap_mean_us=r["gap_mean_s"] * 1e6, gap_p99_us=r["gap_p99_s"] * 1e6,
                               residual_ms=r["residual_s"] * 1e3, predicted_ms=r["predicted_s"] * 1e3))
                print("P2", {k: (round(v, 4) if isinstance(v, float) else v) for k, v in P2[-1].items()})
    R["P2_slices"] = P2

    # ---- P3 isolated foreground (no background): service floor and timer overhead
    P3 = {}
    for nm, kind in (("fma", 1), ("mem", 0)):
        for ms in (0.1, 1.0):
            u = int(units_for(cal[nm], ms))
            a_ = poisson_arrivals(200.0, 2000, seed=3, t0=w.d.w2_qpc_now() + 0.5)
            tl, tc, g = w.fg_run(kind, a_, u)
            lat = latencies(a_, tc) * 1e3
            P3[f"{nm}_{ms}ms"] = dict(units=u, lat_p50_ms=pct(lat, 50), lat_p99_ms=pct(lat, 99), lat_max_ms=float(lat.max()), gpu_p50_ms=pct(g, 50),
                                     launch_delay_p50_us=pct((tl - a_) * 1e6, 50), launch_delay_p99_us=pct((tl - a_) * 1e6, 99), overhead_p50_ms=pct(lat - g, 50))
            print("P3", nm, ms, {k: round(v, 4) for k, v in P3[f"{nm}_{ms}ms"].items()})
    R["P3_fg_isolated"] = P3

    # ---- P4 frame sizing: unlocked service time vs frame budget (60 Hz = 16.67 ms, 120 Hz = 8.33 ms)
    P4 = {}
    for nm, kind in (("fma", 1), ("mem", 0)):
        for hz, tgt in ((60, 9.0), (120, 4.5)):
            u = int(units_for(cal[nm], tgt))
            a_ = w.d.w2_qpc_now() + 0.5 + np.arange(300) / hz
            tl, tc, g = w.fg_run(kind, a_, u)
            lat = latencies(a_, tc) * 1e3
            P4[f"{nm}_{hz}Hz"] = dict(units=u, target_ms=tgt, budget_ms=1000 / hz, service_p50_ms=pct(g, 50), lat_p50_ms=pct(lat, 50), lat_p99_ms=pct(lat, 99),
                                      service_over_budget=pct(g, 50) / (1000 / hz))
            print("P4", nm, hz, {k: round(v, 4) for k, v in P4[f"{nm}_{hz}Hz"].items()})
    R["P4_frames"] = P4

    # ---- P5 two-process co-run feasibility, ONE cell (fma bg 2 ms constant slices; fg 0.1 ms @200 Hz, 2000 requests)
    ufg = int(units_for(cal["fma"], 0.1))
    ubg = units_for(cal["fma"], gamma_slice_durations(2000, 2.0, 0.0, seed=1))
    np.save(out / "bg_units.npy", ubg)
    w.d.w2_free()   # parent releases its context so the children are the only GPU clients
    t0 = time.perf_counter() + 6.0     # both children finish CUDA init well before t0
    dur = 12.0
    me = [sys.executable, str(Path(__file__).resolve())]
    bgp = subprocess.Popen(me + ["--role", "bg", "--kind", "1", "--units", str(out / "bg_units.npy"), "--t_stop", repr(t0 + dur + 1), "--out", str(out / "p5_bg.csv")])
    fgp = subprocess.Popen(me + ["--role", "fg", "--kind", "1", "--units_n", str(ufg), "--rate", "200", "--n", "2000", "--seed", "5", "--t_begin", repr(t0 + 1.0), "--out", str(out / "p5_fg.csv")])
    for p_, cpu in ((bgp, [8]), (fgp, [4])):
        psutil.Process(p_.pid).cpu_affinity(cpu)
    psutil.Process(fgp.pid).nice(psutil.HIGH_PRIORITY_CLASS)
    bgp.wait(); fgp.wait()
    if bgp.returncode or fgp.returncode:
        sys.exit(f"FATAL co-run child failed bg={bgp.returncode} fg={fgp.returncode}")
    bgd = np.loadtxt(out / "p5_bg.csv", delimiter=",", skiprows=1); fgd = np.loadtxt(out / "p5_fg.csv", delimiter=",", skiprows=1)
    mask = (bgd[:, 0] >= t0 + 1.0) & (bgd[:, 1] <= fgd[:, 2].max())
    r = residual_wait(bgd[mask, 0], bgd[mask, 1]); lat = latencies(fgd[:, 0], fgd[:, 2]) * 1e3
    base = P3["fma_0.1ms"]["lat_p50_ms"]
    R["P5_corun_one_cell"] = dict(bg_slices_in_window=int(mask.sum()), rho=r["rho"], mean_slice_ms=r["mean_s"] * 1e3, gap_mean_us=r["gap_mean_s"] * 1e6,
                                  residual_ms=r["residual_s"] * 1e3, predicted_wait_ms=r["predicted_s"] * 1e3, isolated_lat_p50_ms=base,
                                  fg_lat_mean_ms=float(lat.mean()), fg_lat_p50_ms=pct(lat, 50), fg_lat_p99_ms=pct(lat, 99), fg_lat_max_ms=float(lat.max()),
                                  fg_wait_mean_ms=float(lat.mean() - base), note="feasibility only; not used for tolerances or hypotheses")
    print("P5", {k: (round(v, 4) if isinstance(v, float) else v) for k, v in R["P5_corun_one_cell"].items()})

    # ---- P6 decode proxy timing, unlocked (parent context freed above; decode owns its own init)
    w = W2()
    P6 = []
    for variant, layers, nm in ((1, 28, "q4"), (0, 14, "fp16")):
        bpt = ctypes.c_double()
        rc = w.d.w2_decode_init(variant, layers, 512, ctypes.byref(bpt))
        if rc != 0:
            P6.append(dict(variant=nm, layers=layers, error=w.d.w2_last_error().decode())); print("P6 init failed", P6[-1]); continue
        for graph in (0, 1):
            cap = 20000; te = np.zeros(cap); n = ctypes.c_int()
            w.chk(w.d.w2_decode_run(graph, ctypes.c_double(w.d.w2_qpc_now() + 1.0), dbl(te), cap, ctypes.byref(n)), "decode warm")
            w.chk(w.d.w2_decode_run(graph, ctypes.c_double(w.d.w2_qpc_now() + 4.0), dbl(te), cap, ctypes.byref(n)), "decode run")
            t = te[:n.value]; dt = np.diff(t) * 1e3
            fin = ctypes.c_int(); w.d.w2_decode_state_finite(ctypes.byref(fin))
            P6.append(dict(variant=nm, layers=layers, graph=bool(graph), launches_per_token=8 * layers, tokens=int(n.value),
                           tok_s=float(n.value / (t[-1] - t[0])), ms_per_token_p50=pct(dt, 50), ms_per_token_p99=pct(dt, 99),
                           bytes_per_token_mb=bpt.value / 1e6, eff_gb_s=float(bpt.value / 1e9 * n.value / (t[-1] - t[0])), state_finite=bool(fin.value)))
            print("P6", {k: (round(v, 3) if isinstance(v, float) else v) for k, v in P6[-1].items()})
        w.d.w2_decode_free()
    R["P6_decode"] = P6
    R["env_end"] = snap()
    (out / "pilot.json").write_text(json.dumps(R, indent=2, default=float), encoding="utf-8")
    print(f"\nwritten {out / 'pilot.json'}")


if __name__ == "__main__":
    main()
