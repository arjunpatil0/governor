#!/usr/bin/env python3
"""W2 co-location harness. Design is fixed by experiments/w2_colocation.yaml (pre-registered); cell lists come from design.py.

Full runs need an Administrator shell (clock locks) and a clean committed tree, e.g. Experiment C:
    python experiments\\w2_colocation\\run.py --part C --ambient-c 24
Parts: A (primary residual-wait), A2 (secondary preemption characterisation), B (clock lock vs foreground), C (decode knee).
Smoke test without admin (one block, a few cells, short windows, no clock control; NOT a result):
    python experiments\\w2_colocation\\run.py --part A --smoke

The parent process holds NVML only and never creates a CUDA context; CUDA work runs in child processes (calibration, background,
foreground, decode) that share one QPC timeline. Clock resets run in a finally block. No CPU fallback anywhere.
"""
import argparse, csv, ctypes, hashlib, json, platform, subprocess, sys, threading, time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import psutil
import pynvml as nv
import yaml

ROOT = Path(__file__).resolve().parents[2]
for sub in ("telemetry", "workloads/common", "analysis", "experiments/w2_colocation"):
    sys.path.insert(0, str(ROOT / sub))
from design import build_cells, cell_seed, clock_flags, frame_units_from_pilot, order_block  # noqa: E402
from loadgen import gamma_slice_durations, latencies, parse_hags, poisson_arrivals, residual_wait  # noqa: E402
from nvml_utils import current_event_mask, decode_event_reasons  # noqa: E402
from provenance import check_run_provenance, git_state  # noqa: E402

CFG_PATH = ROOT / "experiments" / "w2_colocation.yaml"
PILOT = ROOT / "data" / "pilot" / "w2" / "20261020T222839Z" / "pilot.json"
FG_CPU, BG_CPU = 4, 8
KIND_ID = {"mem": 0, "fma": 1}
SELF = [sys.executable, str(Path(__file__).resolve())]
NO_CLOCK_CONTROL = False
FIELDS = ["block", "cell_idx", "part", "cell_id", "sm_mhz", "mem_mhz", "seed", "spec", "n_fg_measured", "frac_completed",
          "lat_mean_ms", "lat_p50_ms", "lat_p99_ms", "lat_p999_ms", "lat_max_ms", "fg_gpu_p50_ms", "miss_frac", "budget_ms",
          "bg_slices", "rho", "bg_mean_slice_ms", "residual_ms", "predicted_wait_ms", "gap_mean_us", "gap_p99_us",
          "tokens", "tok_s", "eff_gb_s", "energy_j", "power_counter_w", "power_samples_w",
          "sm_clock_med", "mem_clock_med", "sm_clock_min", "sm_clock_max", "temp_pre_c", "temp_max_c", "event_reasons", "flags"]


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()[:16]


def smi(*a):
    p = subprocess.run(["nvidia-smi", *a], capture_output=True, text=True)
    return p.returncode, (p.stdout + p.stderr).strip()


def set_sm(level):
    if NO_CLOCK_CONTROL:
        return
    rc, out = smi("-rgc") if level == "unlocked" else smi("-lgc", f"{level},{level}")
    if rc != 0:
        raise RuntimeError(f"SM clock set {level} failed: {out}")


def set_mem(mhz):
    if NO_CLOCK_CONTROL:
        return
    rc, out = smi("-lmc", f"{mhz},{mhz}")
    if rc != 0:
        raise RuntimeError(f"memory clock lock {mhz} failed: {out}")


class WinSampler(threading.Thread):
    """20 Hz NVML sampler over the measured window."""
    def __init__(self, h):
        super().__init__(daemon=True); self.h = h; self.stop_ev = threading.Event()
        self.sm, self.mem, self.pw, self.tmp, self.mask = [], [], [], [], 0

    def run(self):
        h = self.h
        while not self.stop_ev.is_set():
            self.sm.append(nv.nvmlDeviceGetClockInfo(h, nv.NVML_CLOCK_SM)); self.mem.append(nv.nvmlDeviceGetClockInfo(h, nv.NVML_CLOCK_MEM))
            self.pw.append(nv.nvmlDeviceGetPowerUsage(h) / 1000); self.tmp.append(nv.nvmlDeviceGetTemperature(h, nv.NVML_TEMPERATURE_GPU))
            self.mask |= current_event_mask(h)
            time.sleep(0.05)

    def finish(self):
        self.stop_ev.set(); self.join()


# ------------------------------------------------------------------------------------------- children
def child_main(role, spec_path):
    from w2lib import W2, calibrate
    spec = json.loads(Path(spec_path).read_text(encoding="utf-8"))
    ps = psutil.Process()
    if spec.get("cpu") is not None:
        ps.cpu_affinity([spec["cpu"]])
    if spec.get("priority") == "high":
        ps.nice(psutil.HIGH_PRIORITY_CLASS)
    out = Path(spec["out"])
    w = W2()
    if role == "calibrate":
        w.bg_until(1, [20000], w.now() + 3)          # warm-up at the locked clock
        cal = {"fma": calibrate(w, 1, [2000, 8000, 32000, 64000]), "mem": calibrate(w, 0, [200, 800, 2000, 4096, 8192])}
        out.write_text(json.dumps(cal, indent=2), encoding="utf-8")
    elif role == "bg":
        units = np.load(spec["units"])
        while w.now() < spec["t_sync"]:
            time.sleep(0.001)
        ts, te, g = w.bg_until(spec["kind"], units, spec["t_stop"], cap=spec["cap"], duty=spec["duty"])
        np.savez_compressed(out, t_start=ts, t_end=te, gpu_ms=g.astype(np.float32))
    elif role == "fg":
        arr = np.load(spec["arrivals"])
        tl, tc, g = w.fg_run(spec["kind"], arr, spec["units"])
        np.savez_compressed(out, arrival=arr, t_launch=tl, t_complete=tc, gpu_ms=g.astype(np.float32))
    elif role == "decode":
        import ctypes as C
        from w2lib import dbl
        bpt = C.c_double()
        if w.d.w2_decode_init(spec["variant"], spec["layers"], 512, C.byref(bpt)) != 0:
            sys.exit(f"FATAL decode_init: {w.d.w2_last_error().decode()}")
        te = np.zeros(spec["cap"]); n = C.c_int()
        while w.now() < spec["t_sync"]:
            time.sleep(0.001)
        w.chk(w.d.w2_decode_run(int(spec["graph"]), C.c_double(spec["t_stop"]), dbl(te), spec["cap"], C.byref(n)), "decode_run")
        fin = C.c_int(); w.d.w2_decode_state_finite(C.byref(fin))
        np.savez_compressed(out, t_tok_end=te[:n.value], bytes_per_token=bpt.value, finite=fin.value)
        w.d.w2_decode_free()


def spawn(role, spec, cell_dir):
    sp = cell_dir / f"{role}_spec.json"
    sp.write_text(json.dumps(spec), encoding="utf-8")
    log = open(cell_dir / f"{role}.log", "w")
    return subprocess.Popen(SELF + ["--child", role, "--spec", str(sp)], stdout=log, stderr=subprocess.STDOUT)


# ------------------------------------------------------------------------------------------- parent
def pct(a, q):
    return float(np.percentile(a, q))


def load_npz(path):
    """Read every array and close the file (Windows cannot delete a file that is still open)."""
    with np.load(path) as f:
        return {k: f[k] for k in f.files}


def run_cell(cell, block, idx, h, ctx):
    """Run one cell; returns (csv row dict). ctx: cfg, cal, units_frame, out_dir, timing, hags, bytes_note."""
    T = ctx["timing"]; part = cell["part"]
    cdir = ctx["out_dir"] / "cells" / f"b{block:02d}_{idx:02d}_{cell['cell_id']}"
    cdir.mkdir(parents=True)
    flags = []
    seed = cell_seed(ctx["cfg_seed"], block, idx)
    t_end = time.time() + 60
    while nv.nvmlDeviceGetTemperature(h, nv.NVML_TEMPERATURE_GPU) > T["tmax"] and time.time() < t_end:
        time.sleep(1.0)
    temp_pre = nv.nvmlDeviceGetTemperature(h, nv.NVML_TEMPERATURE_GPU)
    if temp_pre > T["tmax"]:
        flags.append("start_temp_not_reached")
    set_sm(cell["sm_mhz"])
    fg, bg = cell["fg"], cell["bg"]
    t_sync = time.perf_counter() + T["lead"]
    procs, row = [], dict(block=block, cell_idx=idx, part=part, cell_id=cell["cell_id"], sm_mhz=cell["sm_mhz"], mem_mhz=cell["mem_mhz"],
                          seed=seed, spec=json.dumps({k: v for k, v in cell.items() if k not in ("part", "cell_id")}))
    cal = ctx["cal"]

    if part == "C":
        d = cell["decode"]; layers = 28 if d["variant"] == "int4" else 14
        t_win0 = t_sync + T["preroll"]; t_win1 = t_win0 + T["window"]
        procs.append(spawn("decode", dict(out=str(cdir / "decode.npz"), variant=0 if d["variant"] == "fp16" else 1, layers=layers, graph=d["graph"],
                                          t_sync=t_sync + 0.0, t_stop=t_win1 + 0.1, cap=200_000, cpu=BG_CPU), cdir))
        n_fg = None
    else:
        rate, n_meas = fg["rate_hz"], fg["n"]
        n_warm = int(round(rate * T["warmup"]))
        if fg["arrivals"] == "poisson":
            arr = poisson_arrivals(rate, n_warm + n_meas, seed, t0=t_sync)
        else:
            arr = t_sync + np.arange(n_warm + n_meas) / rate
        t_win0 = t_sync + T["warmup"]; t_win1 = arr[-1]
        np.save(cdir / "arrivals.npy", arr)
        if fg.get("frame"):
            units_fg = ctx["frame_units"][fg["frame"]]
        else:
            units_fg = int(ctx["units_for"](cal["fma"], fg["size_ms"]))
        kid = KIND_ID[fg["kind"]]
        procs.append(spawn("fg", dict(out=str(cdir / "fg.npz"), arrivals=str(cdir / "arrivals.npy"), kind=kid, units=units_fg,
                                      cpu=FG_CPU, priority=fg["priority"]), cdir))
        if bg:
            nslice = int((t_win1 - t_sync + 2) / (0.4 * bg["m_ms"] * 1e-3)) + 100
            dur = gamma_slice_durations(min(nslice, 400_000), bg["m_ms"], bg["cv"], seed + 1)
            units = ctx["units_for"](cal[bg["kind"]], dur)
            np.save(cdir / "bg_units.npy", units)
            cap = int((t_win1 - t_sync + 2) / (0.3 * bg["m_ms"] * 1e-3)) + 1000
            procs.append(spawn("bg", dict(out=str(cdir / "bg.npz"), units=str(cdir / "bg_units.npy"), kind=KIND_ID[bg["kind"]], t_sync=t_sync,
                                          t_stop=t_win1 + 1.0, cap=min(cap, 1_500_000), duty=bg["duty"], cpu=BG_CPU), cdir))

    # measured window: energy counter read exactly twice; 20 Hz samples inside
    while time.perf_counter() < t_win0:
        time.sleep(0.002)
    e0 = nv.nvmlDeviceGetTotalEnergyConsumption(h)
    samp = WinSampler(h); samp.start()
    while time.perf_counter() < t_win1 + (0.05 if part != "C" else 0):
        time.sleep(0.005)
    e1 = nv.nvmlDeviceGetTotalEnergyConsumption(h)
    samp.finish()
    for p in procs:
        try:
            p.wait(timeout=T["child_timeout"])
        except subprocess.TimeoutExpired:
            p.kill(); flags.append("child_timeout")
        if p.returncode not in (0, None):
            flags.append(f"child_rc:{p.returncode}")
    if any(f.startswith("child_") for f in flags):
        row.update(flags=";".join(flags)); raise RuntimeError(f"child failure in {cdir}: {flags}")

    wall = t_win1 - t_win0
    energy_j = (e1 - e0) / 1000.0
    row.update(energy_j=energy_j, power_counter_w=energy_j / wall, power_samples_w=float(np.mean(samp.pw)),
               sm_clock_med=float(np.median(samp.sm)), mem_clock_med=float(np.median(samp.mem)), sm_clock_min=min(samp.sm), sm_clock_max=max(samp.sm),
               temp_pre_c=temp_pre, temp_max_c=max(samp.tmp), event_reasons="|".join(decode_event_reasons(samp.mask)))
    np.savetxt(cdir / "samples.csv", np.c_[samp.sm, samp.mem, samp.pw, samp.tmp], delimiter=",", header="sm_mhz,mem_mhz,power_w,temp_c", comments="")
    sm_t = None if cell["sm_mhz"] == "unlocked" else cell["sm_mhz"]
    flags += clock_flags(samp.sm, samp.mem, sm_t, cell["mem_mhz"])
    if not ctx["hags"]["enabled"]:
        flags.append("hags_not_enabled")
    if abs(row["power_counter_w"] - row["power_samples_w"]) > 0.15 * row["power_samples_w"] and part in ("B", "C"):
        flags.append(f"energy_vs_samples:{row['power_counter_w']:.1f}/{row['power_samples_w']:.1f}")

    if part == "C":
        z = load_npz(cdir / "decode.npz"); t = z["t_tok_end"]
        k = t[(t >= t_win0) & (t < t_win1)]
        if not int(z["finite"]):
            flags.append("decode_state_not_finite")
        row.update(tokens=int(len(k)), tok_s=float(len(k) / wall), eff_gb_s=float(z["bytes_per_token"] / 1e9 * len(k) / wall))
    else:
        z = load_npz(cdir / "fg.npz")
        a, tc, g = z["arrival"], z["t_complete"], z["gpu_ms"]
        m = a >= t_win0
        lat = latencies(a[m], tc[m]) * 1e3
        done = float(np.mean(tc[m] <= t_win1 + 1.0))
        row.update(n_fg_measured=int(m.sum()), frac_completed=done, lat_mean_ms=float(lat.mean()), lat_p50_ms=pct(lat, 50), lat_p99_ms=pct(lat, 99),
                   lat_p999_ms=pct(lat, 99.9), lat_max_ms=float(lat.max()), fg_gpu_p50_ms=float(np.median(g[m])))
        if fg["arrivals"] == "periodic":
            row.update(budget_ms=1000.0 / fg["rate_hz"], miss_frac=float(np.mean(lat > 1000.0 / fg["rate_hz"])))
        if done < 0.95:
            flags.append(f"fg_incomplete:{done:.2f}")
        if bg:
            zb = load_npz(cdir / "bg.npz"); ts, te = zb["t_start"], zb["t_end"]
            if len(ts) and ts[0] - t_sync > 0.5:
                flags.append("bg_started_late")
            w = (te > t_win0) & (ts < t_win1)
            if w.sum() < 2:
                flags.append("bg_no_slices")
            else:
                r = residual_wait(ts[w], te[w])
                np.savez_compressed(cdir / "bg_window.npz", t_start=ts[w], t_end=te[w], gpu_ms=zb["gpu_ms"][w])
                row.update(bg_slices=int(w.sum()), rho=r["rho"], bg_mean_slice_ms=r["mean_s"] * 1e3, residual_ms=r["residual_s"] * 1e3,
                           predicted_wait_ms=r["predicted_s"] * 1e3, gap_mean_us=r["gap_mean_s"] * 1e6, gap_p99_us=r["gap_p99_s"] * 1e6)
                if bg["duty"] == 1.0 and r["rho"] < 0.95:
                    flags.append(f"rho_low:{r['rho']:.3f}")
        np.savez_compressed(cdir / "fg_window.npz", arrival=a[m], t_launch=z["t_launch"][m], t_complete=tc[m], gpu_ms=g[m])
    row["flags"] = ";".join(flags)
    for tmp in ("fg.npz", "bg.npz", "arrivals.npy", "bg_units.npy"):    # window files hold the measured data; drop the warm-up duplicates
        (cdir / tmp).unlink(missing_ok=True)
    return row


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--part", choices=["A", "A2", "B", "C"])
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--ambient-c", type=float, default=None)
    ap.add_argument("--child"); ap.add_argument("--spec")
    a = ap.parse_args()
    if a.child:
        return child_main(a.child, a.spec)
    if not a.part:
        ap.error("--part is required")

    global NO_CLOCK_CONTROL
    cfg = yaml.safe_load(CFG_PATH.read_text(encoding="utf-8"))
    admin = bool(ctypes.windll.shell32.IsUserAnAdmin())
    key = {"A": "experiment_A", "A2": "experiment_A", "B": "experiment_B", "C": "experiment_C"}[a.part]
    blocks = cfg[key]["blocks"]
    T = dict(tmax=cfg["common"]["gpu_start_temp_max_c"], warmup=cfg["common"]["warmup_s"], idle=cfg["common"]["idle_between_cells_s"],
             lead=6.0 if a.part != "C" else 9.0, preroll=cfg["experiment_C"]["preroll_s"], window=cfg["experiment_C"]["window_s"], child_timeout=90)
    if a.smoke:
        NO_CLOCK_CONTROL = not admin
        blocks, T["warmup"], T["preroll"], T["window"], T["idle"] = 1, 0.5, 0.5, 1.5, 0.5
        print("SMOKE: one block, first 3 cells, short windows. Not a result.")
    elif not admin:
        sys.exit("Full run needs an Administrator shell (clock locks). Use --smoke to test without admin.")
    git_head = check_run_provenance(ROOT, smoke=a.smoke)
    dll = ROOT / "workloads" / "background" / "build" / "w2_kernels.dll"
    if not dll.exists():
        sys.exit(f"FATAL {dll} missing: build it first (no CPU fallback)")

    # one dxdiag capture per session (approved read-only call): reuse a capture younger than 6 h, else take a new one
    raw = ROOT / "data" / "raw"; raw.mkdir(parents=True, exist_ok=True)
    fresh = [p for p in raw.glob("dxdiag_*.txt") if time.time() - p.stat().st_mtime < 6 * 3600]
    if fresh:
        dxd = max(fresh, key=lambda p: p.stat().st_mtime)
    else:
        dxd = raw / f"dxdiag_{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}.txt"
        subprocess.run(["dxdiag", "/t", str(dxd)], check=True)
        for _ in range(60):
            if dxd.exists() and dxd.stat().st_size > 1000:
                break
            time.sleep(1)
        time.sleep(2)
    hags = parse_hags(dxd.read_text(errors="ignore"))

    nv.nvmlInit(); h = nv.nvmlDeviceGetHandleByIndex(0)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = ROOT / "data" / "raw" / (f"w2_{a.part}_smoke" if a.smoke else f"w2_{a.part}") / stamp
    out_dir.mkdir(parents=True)
    batt = psutil.sensors_battery()
    meta = dict(utc=stamp, part=a.part, smoke=a.smoke, admin=admin, ac_plugged=None if batt is None else batt.power_plugged, ambient_c=a.ambient_c,
                yaml_sha=sha(CFG_PATH), dll_sha=sha(dll), git_head=git_head, git_dirty=bool(git_state(ROOT)[1]) if a.smoke else False,
                gpu=nv.nvmlDeviceGetName(h), driver=nv.nvmlSystemGetDriverVersion(), hags=hags,
                execution_mode="CUDA native kernels via w2_kernels.dll (no CPU fallback)", os=platform.platform(), python=sys.version.split()[0],
                blocks=blocks, timing=T)
    (out_dir / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(f"HAGS: {hags['line']} | git {git_head[:8]} | out {out_dir}")
    if not hags["enabled"]:
        print("WARNING: HAGS is not enabled; every cell will be flagged hags_not_enabled")

    from w2lib import units_for
    f = open(out_dir / "results.csv", "w", newline="", encoding="utf-8")
    wr = csv.DictWriter(f, fieldnames=FIELDS, restval=""); wr.writeheader()
    try:
        set_mem(8001)
        cal, frame_units = None, None
        if a.part in ("A", "A2", "B"):
            set_sm(1800)                                   # calibrate at the experiment's clock (A, A2) / the B background reference clock
            calp = out_dir / "calibration.json"
            p = spawn("calibrate", dict(out=str(calp), cpu=BG_CPU), out_dir)
            if p.wait(timeout=180) != 0:
                raise RuntimeError("calibration child failed")
            cal = json.loads(calp.read_text(encoding="utf-8"))
            print("calibration:", {k: (round(v["a_ms"], 4), round(v["b_ms_per_unit"], 7)) for k, v in cal.items()})
        if a.part == "B":
            frame_units = frame_units_from_pilot(PILOT)
        ctx = dict(cfg_seed=20261021, timing=T, cal=cal, frame_units=frame_units, out_dir=out_dir, hags=hags, units_for=units_for)
        base_cells = build_cells(cfg, "A" if a.part == "A" else a.part)
        t_run = time.time()
        for b in range(blocks):
            order = order_block(base_cells, ctx["cfg_seed"], b)
            if a.smoke:
                order = order[:3]
            for i, cell in enumerate(order):
                row = run_cell(cell, b, i, h, ctx)
                wr.writerow(row); f.flush()
                print(f"[blk{b} {i+1}/{len(order)}] {cell['cell_id']:28s} sm {str(cell['sm_mhz']):>8s}  lat p50 {row.get('lat_p50_ms','')!s:.6}  "
                      f"rho {row.get('rho','')!s:.6}  tok/s {row.get('tok_s','')!s:.6}  {row['power_counter_w']:.1f} W  {row['flags']}", flush=True)
                time.sleep(T["idle"])
        print(f"done in {(time.time()-t_run)/60:.1f} min -> {out_dir}")
    finally:
        smi("-rgc"); smi("-rmc")
        f.close()


if __name__ == "__main__":
    main()
