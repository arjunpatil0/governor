#!/usr/bin/env python3
"""W1 downclock sensitivity harness. Design is fixed by experiments/w1_downclock.yaml (pre-registered).

Full run (needs an Administrator shell for nvidia-smi -lgc):
    python experiments\\w1_downclock\\run.py --ambient-c 24
Smoke test without admin (unlocked clock only, short windows; data goes to a 'smoke' folder):
    python experiments\\w1_downclock\\run.py --smoke
"""
import argparse, csv, ctypes, hashlib, json, platform, random, statistics as st, subprocess, sys, threading, time
from datetime import datetime, timezone
from pathlib import Path

import psutil
import pynvml as nv
import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "telemetry"))
from nvml_utils import current_event_mask, decode_event_reasons, summarize_temps  # noqa: E402
from provenance import check_run_provenance, git_state  # noqa: E402

CFG_PATH = ROOT / "experiments" / "w1_downclock.yaml"
DLL_PATH = ROOT / "workloads" / "background" / "build" / "bench_kernels.dll"
KINDS = {"mem": 0, "fma": 1}
FIELDS = ["block", "cell_idx", "kernel", "level", "target_mhz", "work", "gpu_ms", "wall_s", "throughput",
          "energy_j", "epw", "power_counter_w", "power_samples_w", "sm_clock_med", "mem_clock_med",
          "temp_pre_c", "temp_start_c", "temp_max_c", "event_mask", "event_reasons", "checksum", "flags"]


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()[:16]


SMI_TIMEOUT_S = 30


def smi(*a):
    try:
        p = subprocess.run(["nvidia-smi", *a], capture_output=True, text=True, timeout=SMI_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        return 124, f"nvidia-smi {' '.join(a)} timed out after {SMI_TIMEOUT_S} s"
    return p.returncode, (p.stdout + p.stderr).strip()


NO_CLOCK_CONTROL = False  # set for non-admin --smoke: nothing is locked, so nothing to reset


def set_clock(level):
    if NO_CLOCK_CONTROL:
        return
    rc, out = smi("-rgc") if level == "unlocked" else smi("-lgc", f"{level},{level}")
    if rc != 0:
        raise RuntimeError(f"clock set {level} failed: {out}")


class Sampler(threading.Thread):
    """20 Hz NVML sampler over the measured window."""
    def __init__(self, h):
        super().__init__(daemon=True); self.h = h; self.stop_ev = threading.Event()
        self.sm, self.mem, self.pw, self.tmp, self.mask = [], [], [], [], 0

    def run(self):
        h = self.h
        while not self.stop_ev.is_set():
            self.sm.append(nv.nvmlDeviceGetClockInfo(h, nv.NVML_CLOCK_SM))
            self.mem.append(nv.nvmlDeviceGetClockInfo(h, nv.NVML_CLOCK_MEM))
            self.pw.append(nv.nvmlDeviceGetPowerUsage(h) / 1000)
            self.tmp.append(nv.nvmlDeviceGetTemperature(h, nv.NVML_TEMPERATURE_GPU))
            self.mask |= current_event_mask(h)
            time.sleep(0.05)

    def finish(self):
        self.stop_ev.set(); self.join()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--ambient-c", type=float, default=None, help="manually read room temperature, for meta.json")
    a = ap.parse_args()

    cfg = yaml.safe_load(CFG_PATH.read_text(encoding="utf-8"))
    d = cfg["design"]
    levels = list(d["sm_clock_levels_mhz"])
    reps, preroll, window = d["reps_per_cell"], d["preroll_after_lock_s"], d["measure_window_s"]
    warm, idle, tmax = d["global_warmup_s"], d["idle_between_s"], d["start_temp_max_c"]
    admin = bool(ctypes.windll.shell32.IsUserAnAdmin())
    if a.smoke:
        levels, reps, preroll, window, warm, idle = ["unlocked"], 2, 0.5, 1.0, 2.0, 0.5
        print("SMOKE: unlocked only, short windows. Not a result.")
        global NO_CLOCK_CONTROL
        NO_CLOCK_CONTROL = not admin
    elif not admin:
        sys.exit("Full run needs an Administrator shell (clock locks). Use --smoke to test without admin.")
    for L in levels:
        assert L == "unlocked" or (210 <= L <= 3105 and L % 15 == 0), f"unsupported clock {L}"
    git_head = check_run_provenance(ROOT, smoke=a.smoke)  # a full run must be on a clean, committed tree

    dll = ctypes.CDLL(str(DLL_PATH))
    dll.bench_last_error.restype = ctypes.c_char_p
    sms = ctypes.c_int()
    if dll.bench_init(ctypes.byref(sms)) != 0:
        sys.exit(f"FATAL bench_init: {dll.bench_last_error().decode()} (no CPU fallback)")
    nv.nvmlInit(); h = nv.nvmlDeviceGetHandleByIndex(0)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = ROOT / "data" / "raw" / ("w1_downclock_smoke" if a.smoke else "w1_downclock") / stamp
    out_dir.mkdir(parents=True)
    dirty = bool(git_state(ROOT)[1]) if a.smoke else False  # a full run passed the clean-tree gate above
    batt = psutil.sensors_battery()
    meta = dict(utc=stamp, smoke=a.smoke, admin=admin, ac_plugged=None if batt is None else batt.power_plugged,
                ambient_c=a.ambient_c, yaml_sha=sha(CFG_PATH), dll_sha=sha(DLL_PATH), git_head=git_head, git_dirty=dirty,
                gpu=nv.nvmlDeviceGetName(h), sm_count=sms.value, driver=nv.nvmlSystemGetDriverVersion(),
                execution_mode="CUDA native kernels via bench_kernels.dll (no CPU fallback)",
                os=platform.platform(), python=sys.version.split()[0], levels=levels, reps=reps,
                preroll_s=preroll, window_s=window)
    (out_dir / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

    cells = [(k, L) for k in KINDS for L in levels]
    print(f"{len(cells)} cells x {reps} blocks = {len(cells)*reps} measurements -> {out_dir}")
    f = open(out_dir / "results.csv", "w", newline="", encoding="utf-8")
    w = csv.DictWriter(f, fieldnames=FIELDS); w.writeheader()
    work, gms, wall, cs = (ctypes.c_double() for _ in range(4))
    try:
        set_clock("unlocked")
        print(f"global warm-up {warm}s (discarded)")
        dll.bench_run(KINDS["fma"], ctypes.c_double(warm), *(ctypes.byref(x) for x in (work, gms, wall, cs)))
        t_run = time.time()
        for b in range(reps):
            order = cells[:]; random.Random(d["block_order_seed"] + b).shuffle(order)
            for ci, (kernel, L) in enumerate(order):
                flags = []
                t_end = time.time() + 60
                while nv.nvmlDeviceGetTemperature(h, nv.NVML_TEMPERATURE_GPU) > tmax and time.time() < t_end:
                    time.sleep(1.0)
                temp0 = nv.nvmlDeviceGetTemperature(h, nv.NVML_TEMPERATURE_GPU)
                if temp0 > tmax:
                    flags.append("start_temp_not_reached")
                set_clock(L)
                dll.bench_run(KINDS[kernel], ctypes.c_double(preroll), *(ctypes.byref(x) for x in (work, gms, wall, cs)))
                s = Sampler(h); s.start()
                e_a = nv.nvmlDeviceGetTotalEnergyConsumption(h)
                rc = dll.bench_run(KINDS[kernel], ctypes.c_double(window), *(ctypes.byref(x) for x in (work, gms, wall, cs)))
                e_b = nv.nvmlDeviceGetTotalEnergyConsumption(h)
                s.finish()
                if rc != 0:
                    raise RuntimeError(f"bench_run failed: {dll.bench_last_error().decode()}")
                energy_j = (e_b - e_a) / 1000.0
                thr = work.value / (gms.value / 1000.0)
                pc_w = energy_j / wall.value
                ps_w = st.mean(s.pw)
                smed = st.median(s.sm)
                if L != "unlocked" and abs(smed - L) > 0.03 * L:
                    flags.append(f"clock_off_target:{smed:.0f}")
                if abs(pc_w - ps_w) > 0.15 * ps_w:
                    flags.append(f"energy_vs_samples:{pc_w:.1f}/{ps_w:.1f}")
                row = dict(block=b, cell_idx=ci, kernel=kernel, level=L, target_mhz="" if L == "unlocked" else L,
                           work=work.value, gpu_ms=gms.value, wall_s=wall.value, throughput=thr,
                           energy_j=energy_j, epw=energy_j / work.value, power_counter_w=pc_w, power_samples_w=ps_w,
                           sm_clock_med=smed, mem_clock_med=st.median(s.mem), **summarize_temps(temp0, s.tmp),
                           event_mask=s.mask, event_reasons="|".join(decode_event_reasons(s.mask)),
                           checksum=cs.value, flags=";".join(flags))
                w.writerow(row); f.flush()
                done = b * len(cells) + ci + 1
                print(f"[{done}/{len(cells)*reps}] blk{b} {kernel:3s} {str(L):>8s}  {thr:9.1f} {'GB/s' if kernel=='mem' else 'GFLOP/s'}"
                      f"  {pc_w:5.1f} W  sm {smed:.0f}  {row['temp_start_c']}->{row['temp_max_c']}C  {row['event_reasons']}  {';'.join(flags)}", flush=True)
                set_clock("unlocked")
                time.sleep(idle)
        print(f"done in {(time.time()-t_run)/60:.1f} min -> {out_dir}")
    finally:
        smi("-rgc"); smi("-rmc")
        f.close(); dll.bench_free()


if __name__ == "__main__":
    main()
