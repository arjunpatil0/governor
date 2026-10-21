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
import argparse, csv, ctypes, hashlib, json, os, platform, subprocess, sys, threading, time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import psutil
import pynvml as nv
import yaml

ROOT = Path(__file__).resolve().parents[2]
for sub in ("telemetry", "workloads/common", "analysis", "experiments/w2_colocation"):
    sys.path.insert(0, str(ROOT / sub))
from console import disable_quickedit  # noqa: E402
from llama_cell import parse_exec_mode, window_tokens  # noqa: E402
from design import G_SEED, build_cells, cell_seed, clock_flags, frame_units_for_part, order_block, precheck_cells_G  # noqa: E402
from w2_timeline import pack_rec  # noqa: E402
from loadgen import gamma_slice_durations, latencies, parse_hags, poisson_arrivals, residual_wait  # noqa: E402
from nvml_utils import current_event_mask, decode_event_reasons  # noqa: E402
from provenance import check_run_provenance, git_state  # noqa: E402

CFG_PATH = ROOT / "experiments" / "w2_colocation.yaml"
LLAMA_EXE = ROOT / "workloads" / "background" / "llama_decode_bench.exe"
LLAMA_BIN = ROOT / "third_party" / "llama.cpp" / "build" / "bin"
LLAMA_DIR = ROOT / "data" / "llama"
PILOT = ROOT / "data" / "pilot" / "w2" / "20261020T222839Z" / "pilot.json"
FG_CPU, BG_CPU = 4, 8
KIND_ID = {"mem": 0, "fma": 1}
G_BG_REC_BLOCKS = 800_000      # bg record buffer (Rec = 48 B): ~3700 slices of 216 blocks; later slices run uninstrumented and are counted
SELF = [sys.executable, str(Path(__file__).resolve())]
NO_CLOCK_CONTROL = False
FIELDS = ["block", "cell_idx", "part", "cell_id", "sm_mhz", "mem_mhz", "seed", "spec", "n_fg_measured", "frac_completed",
          "lat_mean_ms", "lat_p50_ms", "lat_p99_ms", "lat_p999_ms", "lat_max_ms", "fg_gpu_p50_ms", "miss_frac", "budget_ms",
          "bg_slices", "rho", "bg_mean_slice_ms", "residual_ms", "predicted_wait_ms", "gap_mean_us", "gap_p99_us",
          "tokens", "tok_s", "eff_gb_s", "energy_j", "power_counter_w", "power_samples_w",
          "sm_clock_med", "mem_clock_med", "sm_clock_min", "sm_clock_max", "temp_pre_c", "temp_max_c", "event_reasons", "rec_blocks_fg", "rec_dropped_fg", "rec_blocks_bg", "rec_dropped_bg", "flags"]


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()[:16]


SMI_TIMEOUT_S = 30


def smi(*a):
    try:
        p = subprocess.run(["nvidia-smi", *a], capture_output=True, text=True, timeout=SMI_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        return 124, f"nvidia-smi {' '.join(a)} timed out after {SMI_TIMEOUT_S} s"
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
def save_rec(path, rec, sync0, sync1, sms):
    """Per-block records (packed) plus the host<->GPU timer offsets measured before and after the run: (offset_s, round_trip_s) each."""
    np.savez_compressed(path, sync0=np.array(sync0), sync1=np.array(sync1), sms=sms, **pack_rec(rec))


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
        rec = bool(spec.get("rec"))
        if rec:
            while w.now() < spec["t_probe"]:        # both children sync the GPU timer to QPC at the same instant (journal 0029)
                time.sleep(0.001)
        sync0 = w.gt_sync3() if rec else None
        while w.now() < spec["t_sync"]:
            time.sleep(0.001)
        if rec:
            ts, te, g, r = w.bg_until_rec(units, spec["t_stop"], t_rec0=spec["t_rec0"], cap_blocks=spec["rec_cap_blocks"], cap=spec["cap"], duty=spec["duty"])
            save_rec(Path(spec["rec_out"]), r, sync0, w.gt_sync3(), w.sms)
        else:
            ts, te, g = w.bg_until(spec["kind"], units, spec["t_stop"], cap=spec["cap"], duty=spec["duty"])
        np.savez_compressed(out, t_start=ts, t_end=te, gpu_ms=g.astype(np.float32))
    elif role == "fg":
        arr = np.load(spec["arrivals"])
        if spec.get("rec"):
            while w.now() < spec["t_probe"]:
                time.sleep(0.001)
            sync0 = w.gt_sync3()
            cap_blocks = (len(arr) - spec["rec_from"] + 10) * w.sms * 6
            tl, tc, g, r = w.fg_run_rec(spec["kind"], arr, spec["units"], rec_from=spec["rec_from"], cap_blocks=cap_blocks)
            save_rec(Path(spec["rec_out"]), r, sync0, w.gt_sync3(), w.sms)
        else:
            tl, tc, g = w.fg_run(spec["kind"], arr, spec["units"])
        np.savez_compressed(out, arrival=arr, t_launch=tl, t_complete=tc, gpu_ms=g.astype(np.float32))
    elif role == "ovh":         # Experiment G pre-check (iii), controlled A/B in one process: plain vs recording kernel, alternating, per gap stride
        out_rows = []
        w.bg_until(1, [20000], w.now() + 3)
        for stride in (64, 128, 256, 512):
            w.set_gap_stride(stride)
            for units in (1000, 8000, 40000):
                plain, recd, gaps = [], [], []
                for _ in range(6):
                    ts, te, _g = w.bg_until(1, [units], w.now() + 0.25); plain.append(float(np.median(te - ts)) * 1e3)
                    ts, te, _g, r = w.bg_until_rec([units], w.now() + 0.25, t_rec0=0.0, cap_blocks=800_000); recd.append(float(np.median(te - ts)) * 1e3)
                    gaps.append(float(np.median((r["t1"] - r["t0"]).astype(np.float64) / np.maximum(r["nreads"], 1))))
                out_rows.append(dict(stride=stride, units=units, plain_ms=float(np.median(plain)), rec_ms=float(np.median(recd)),
                                     ratio=float(np.median(np.array(recd) / np.array(plain))), median_read_gap_ns=float(np.median(gaps))))
        out.write_text(json.dumps(out_rows, indent=1), encoding="utf-8")
    elif role == "gtprobe":     # Experiment G pre-checks (i) timer resolution and (ii) single-process, two-stream timebase
        reads = w.gt_resolution(100_000)
        off, rt = w.gt_sync(500)
        r = w.two_streams_rec(8000, 3000, 0.002)
        off2, rt2 = w.gt_sync(500)
        np.savez_compressed(out, reads=reads, off=off, rt=rt, off2=off2, rt2=rt2, sms=w.sms,
                            times=np.array([r["a_launch"], r["a_done"], r["b_launch"], r["b_done"]]), **pack_rec(r["rec"]))
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
    t_sync = time.perf_counter() + (T["lead_llama"] if part == "L" else T["lead"])      # part L: model load + 512-token prefill happen before t_sync
    procs, row = [], dict(block=block, cell_idx=idx, part=part, cell_id=cell["cell_id"], sm_mhz=cell["sm_mhz"], mem_mhz=cell["mem_mhz"],
                          seed=seed, spec=json.dumps({k: v for k, v in cell.items() if k not in ("part", "cell_id")}))
    cal = ctx["cal"]

    if part == "L":
        t_win0 = t_sync + T["preroll"]; t_win1 = t_win0 + T["window"]
        env = dict(os.environ, PATH=str(LLAMA_BIN) + os.pathsep + os.environ["PATH"])
        log = open(cdir / "llama.log", "w")
        procs.append(subprocess.Popen([str(LLAMA_EXE), str(LLAMA_DIR / cell["llama"]["model"]), str(LLAMA_DIR / "prompt.txt"), str(cdir / "llama_tokens.csv"),
                                       repr(t_sync), repr(t_win1 + 0.1), str(cell["llama"]["n_prompt"])], stdout=log, stderr=subprocess.STDOUT, env=env))
        n_fg = None
    elif part == "C":
        d = cell["decode"]; layers = 28 if d["variant"] == "int4" else 14
        t_win0 = t_sync + T["preroll"]; t_win1 = t_win0 + T["window"]
        procs.append(spawn("decode", dict(out=str(cdir / "decode.npz"), variant=0 if d["variant"] == "fp16" else 1, layers=layers, graph=d["graph"],
                                          t_sync=t_sync + 0.0, t_stop=t_win1 + 0.1, cap=200_000, cpu=BG_CPU), cdir))
        n_fg = None
    else:
        rec = bool(cell.get("rec"))
        t_win0 = t_sync + T["warmup"]
        if fg:
            rate, n_meas = fg["rate_hz"], fg["n"]
            n_warm = int(round(rate * T["warmup"]))
            if fg["arrivals"] == "poisson":
                arr = poisson_arrivals(rate, n_warm + n_meas, seed, t0=t_sync)
            else:
                arr = t_sync + np.arange(n_warm + n_meas) / rate
            t_win1 = arr[-1]
            np.save(cdir / "arrivals.npy", arr)
            if fg.get("frame"):
                units_fg = ctx["frame_units"][fg["frame"]]
            else:
                units_fg = int(ctx["units_for"](cal["fma"], fg["size_ms"]))
            kid = KIND_ID[fg["kind"]]
            procs.append(spawn("fg", dict(out=str(cdir / "fg.npz"), arrivals=str(cdir / "arrivals.npy"), kind=kid, units=units_fg,
                                          cpu=FG_CPU, priority=fg["priority"], rec=rec, rec_from=n_warm, t_probe=t_sync - 1.0, rec_out=str(cdir / "fg_rec.npz")), cdir))
        else:                                              # part G bgalone: no foreground, a window of T["window"] after the warm-up
            t_win1 = t_win0 + T["window"]
        if bg:
            nslice = int((t_win1 - t_sync + 2) / (0.4 * bg["m_ms"] * 1e-3)) + 100
            dur = gamma_slice_durations(min(nslice, 400_000), bg["m_ms"], bg["cv"], seed + 1)
            units = ctx["units_for"](cal[bg["kind"]], dur)
            np.save(cdir / "bg_units.npy", units)
            cap = int((t_win1 - t_sync + 2) / (0.3 * bg["m_ms"] * 1e-3)) + 1000
            procs.append(spawn("bg", dict(out=str(cdir / "bg.npz"), units=str(cdir / "bg_units.npy"), kind=KIND_ID[bg["kind"]], t_sync=t_sync,
                                          t_stop=t_win1 + 1.0, cap=min(cap, 1_500_000), duty=bg["duty"], cpu=BG_CPU,
                                          rec=rec, t_rec0=t_win0, t_probe=t_sync - 1.0, rec_cap_blocks=G_BG_REC_BLOCKS, rec_out=str(cdir / "bg_rec.npz")), cdir))

    # measured window: energy counter read exactly twice; 20 Hz samples inside
    while time.perf_counter() < t_win0:
        time.sleep(0.002)
    e0 = nv.nvmlDeviceGetTotalEnergyConsumption(h)
    samp = WinSampler(h); samp.start()
    while time.perf_counter() < t_win1 + (0.05 if part not in ("C", "L") else 0):
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
    if abs(row["power_counter_w"] - row["power_samples_w"]) > 0.15 * row["power_samples_w"] and part in ("B", "C", "L"):
        flags.append(f"energy_vs_samples:{row['power_counter_w']:.1f}/{row['power_samples_w']:.1f}")

    if part == "L":
        em = parse_exec_mode((cdir / "llama.log").read_text(errors="ignore"))
        if not em["ok"]:
            row.update(flags=";".join(flags + [f"exec_mode_not_gpu:{em['detail']}"])); raise RuntimeError(f"llama driver not fully on GPU in {cdir}: {em['detail']}")
        tk = np.genfromtxt(cdir / "llama_tokens.csv", delimiter=",", names=True)
        k, late = window_tokens(tk["t_tok_end"], t_win0, t_win1)
        if late:
            flags.append("decode_started_late")
        row.update(tokens=int(k), tok_s=float(k / wall), eff_gb_s=float(ctx["llama_model_bytes"] / 1e9 * k / wall))
    elif part == "C":
        z = load_npz(cdir / "decode.npz"); t = z["t_tok_end"]
        k = t[(t >= t_win0) & (t < t_win1)]
        if len(t) == 0 or t[0] > t_win0:
            flags.append("decode_started_late")
        if not int(z["finite"]):
            flags.append("decode_state_not_finite")
        row.update(tokens=int(len(k)), tok_s=float(len(k) / wall), eff_gb_s=float(z["bytes_per_token"] / 1e9 * len(k) / wall))
    else:
        if fg:
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
        if fg:
            np.savez_compressed(cdir / "fg_window.npz", arrival=a[m], t_launch=z["t_launch"][m], t_complete=tc[m], gpu_ms=g[m], idx0=int(np.argmax(m)))
    if cell.get("rec"):                                    # Experiment G: record counts; bg overflow is by design (buffer cap), fg overflow is a flag
        for role in ("fg", "bg"):
            f = cdir / f"{role}_rec.npz"
            if f.exists():
                zr = np.load(f)
                row[f"rec_blocks_{role}"] = int(len(zr["t0_rel"])); row[f"rec_dropped_{role}"] = int(zr["dropped"])
                if role == "fg" and int(zr["dropped"]) > 0:
                    flags.append(f"rec_dropped_fg:{int(zr['dropped'])}")
    row["flags"] = ";".join(flags)
    for tmp in ("fg.npz", "bg.npz", "arrivals.npy", "bg_units.npy"):    # window files hold the measured data; drop the warm-up duplicates
        (cdir / tmp).unlink(missing_ok=True)
    return row


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--part", choices=["A", "A2", "B", "C", "L", "G"])
    ap.add_argument("--precheck", action="store_true", help="part G only: pre-checks (i)-(iii), unlocked clocks, 3 blocks of 6 cells, full-length windows; NOT a result")
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--ambient-c", type=float, default=None)
    ap.add_argument("--armoury-mode", default=None, help="Armoury Crate mode (e.g. Silent/Performance/Turbo/Manual); required for full runs, not detectable (journal 0021)")
    ap.add_argument("--child"); ap.add_argument("--spec")
    a = ap.parse_args()
    if a.child:
        return child_main(a.child, a.spec)
    if not a.part:
        ap.error("--part is required")
    if a.precheck:
        if a.part != "G":
            ap.error("--precheck is for --part G")
        a.smoke = True
    disable_quickedit()                                    # a click in the console would pause the run (journal 0023)

    global NO_CLOCK_CONTROL
    cfg = yaml.safe_load(CFG_PATH.read_text(encoding="utf-8"))
    admin = bool(ctypes.windll.shell32.IsUserAnAdmin())
    key = {"A": "experiment_A", "A2": "experiment_A", "B": "experiment_B", "C": "experiment_C", "L": "experiment_C", "G": "experiment_A"}[a.part]
    blocks = cfg[key]["blocks"]
    T = dict(tmax=cfg["common"]["gpu_start_temp_max_c"], warmup=cfg["common"]["warmup_s"], idle=cfg["common"]["idle_between_cells_s"],
             lead=5.0, lead_llama=25.0, preroll=cfg["experiment_C"]["preroll_s"], window=cfg["experiment_C"]["window_s"], child_timeout=90)
    batt0 = psutil.sensors_battery()
    if not a.smoke and batt0 is not None and not batt0.power_plugged:
        sys.exit("Full run refused: the laptop is on battery. The registration (hardware: AC power) requires AC; plug in and retry.")
    if a.smoke:
        NO_CLOCK_CONTROL = not admin
        if a.precheck:
            blocks = 3
            print("PRE-CHECK (Experiment G i-iii): 3 blocks x 6 cells, full-length windows, no clock control without admin. Not a result.")
        else:
            blocks, T["warmup"], T["preroll"], T["window"], T["idle"] = 1, 0.5, 0.5, 1.5, 0.5
            print("SMOKE: one block, first 3 cells plus one per other fg stream, short windows. Not a result.")
    elif not admin:
        sys.exit("Full run needs an Administrator shell (clock locks). Use --smoke to test without admin.")
    if not a.smoke and not a.armoury_mode:
        sys.exit("Full run refused: pass --armoury-mode <the Armoury Crate mode now active> (it changes the GPU memory clock; journal 0021).")
    git_head = check_run_provenance(ROOT, smoke=a.smoke)
    dll = ROOT / "workloads" / "background" / "build" / "w2_kernels.dll"
    if not dll.exists():
        sys.exit(f"FATAL {dll} missing: build it first (no CPU fallback)")
    llama_meta = None
    if a.part == "L":                                  # fail before any clock is touched (addendum: no silent fallback)
        model = LLAMA_DIR / "Llama-3.2-3B-Instruct-Q4_K_M.gguf"
        for need in (LLAMA_EXE, model, LLAMA_DIR / "prompt.txt", LLAMA_BIN / "llama.dll"):
            if not need.exists():
                sys.exit(f"FATAL part L needs {need} (build: third_party/build_llama.bat and workloads/background/build_llama_driver.bat)")
        h256 = hashlib.sha256()
        with open(model, "rb") as mf:
            for chunk in iter(lambda: mf.read(1 << 24), b""):
                h256.update(chunk)
        if h256.hexdigest() != "6c1a2b41161032677be168d354123594c0e6e67d2b9227c84f296ad037c728ff":
            sys.exit(f"FATAL model sha256 {h256.hexdigest()} differs from the registered 6c1a2b41...28ff")
        commit = subprocess.run(["git", "-C", str(ROOT / "third_party" / "llama.cpp"), "rev-parse", "HEAD"], capture_output=True, text=True, timeout=30).stdout.strip()
        if commit != "620d2225cc436ab0b001e3200e590e3b286ef9ab":
            sys.exit(f"FATAL llama.cpp commit {commit!r} is not the pinned 620d2225...")
        llama_meta = dict(commit=commit, build_path="source build (third_party/build_llama.bat, CUDA sm_89)", model=model.name, model_bytes=model.stat().st_size,
                          model_sha256=h256.hexdigest(), prompt_sha256=hashlib.sha256((LLAMA_DIR / "prompt.txt").read_bytes()).hexdigest(),
                          driver_exe_sha=sha(LLAMA_EXE), cpu_affinity="none (the +/-5% sanity check was also unpinned)")

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
    out_dir = ROOT / "data" / "raw" / (f"w2_{a.part}_precheck" if a.precheck else f"w2_{a.part}_smoke" if a.smoke else f"w2_{a.part}") / stamp
    out_dir.mkdir(parents=True)
    batt = psutil.sensors_battery()
    meta = dict(utc=stamp, part=a.part, smoke=a.smoke, precheck=a.precheck, admin=admin, ac_plugged=None if batt is None else batt.power_plugged, ambient_c=a.ambient_c, armoury_mode=a.armoury_mode,
                yaml_sha=sha(CFG_PATH), dll_sha=sha(dll), git_head=git_head, git_dirty=bool(git_state(ROOT)[1]) if a.smoke else False,
                gpu=nv.nvmlDeviceGetName(h), driver=nv.nvmlSystemGetDriverVersion(), hags=hags,
                execution_mode=("llama.cpp CUDA build, all layers offloaded (checked per cell from the driver log; a cell with any CPU layer aborts the run)" if a.part == "L" else "CUDA native kernels via w2_kernels.dll (no CPU fallback)"), llama=llama_meta, os=platform.platform(), python=sys.version.split()[0],
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
        if a.part in ("A", "A2", "B", "G"):
            set_sm(1800)                                   # calibrate at the experiment's clock (A, A2) / the B background reference clock
            calp = out_dir / "calibration.json"
            p = spawn("calibrate", dict(out=str(calp), cpu=BG_CPU), out_dir)
            if p.wait(timeout=180) != 0:
                raise RuntimeError("calibration child failed")
            cal = json.loads(calp.read_text(encoding="utf-8"))
            print("calibration:", {k: (round(v["a_ms"], 4), round(v["b_ms_per_unit"], 7)) for k, v in cal.items()})
        base_cells = build_cells(cfg, "A" if a.part == "A" else a.part)
        frame_units = frame_units_for_part(a.part, base_cells, PILOT)
        if a.precheck:                                     # (i) timer resolution and (ii-a) single-process two-stream timebase, in one CUDA child
            pg = spawn("gtprobe", dict(out=str(out_dir / "gtprobe.npz"), cpu=BG_CPU), out_dir)
            if pg.wait(timeout=180) != 0:
                raise RuntimeError("gtprobe child failed")
            po = spawn("ovh", dict(out=str(out_dir / "ovh.json"), cpu=BG_CPU), out_dir)
            if po.wait(timeout=300) != 0:
                raise RuntimeError("ovh child failed")
        ctx = dict(cfg_seed=G_SEED if a.part == "G" else 20261021, llama_model_bytes=(llama_meta or {}).get("model_bytes"), timing=T, cal=cal, frame_units=frame_units, out_dir=out_dir, hags=hags, units_for=units_for)
        t_run = time.time()
        for b in range(blocks):
            order = order_block(precheck_cells_G(base_cells) if a.precheck else base_cells, ctx["cfg_seed"], b)
            if a.smoke and not a.precheck:                                    # first 3 cells + the first cell of every other fg stream (journal 0021: the 9 ms frame cell was the 4th)
                sigf = lambda c: (c["fg"]["size_ms"], c["fg"].get("frame")) if c.get("fg") else None
                pick = order[:3]
                seen = {sigf(c) for c in pick}
                for c in order[3:]:
                    if sigf(c) not in seen:
                        pick.append(c); seen.add(sigf(c))
                order = order if a.part == "G" else pick       # part G smoke runs all 14 cells so every code path of the full run is exercised
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
