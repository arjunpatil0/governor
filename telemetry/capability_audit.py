#!/usr/bin/env python3
"""capability_audit.py - verify every sensor/actuator the governor depends on, on THIS machine.

Per item: available (Y/N/NOT_RUN), needs_admin, latency_ms, a real reading or measured effect, note.
Nothing is estimated: items that cannot run (e.g. clock lock without elevation) are reported NOT_RUN.
Output: data/capability_audit.json and data/capability_audit.md
Run elevated for the clock-lock / power-limit tests:  python telemetry/capability_audit.py
"""
import argparse, ctypes, json, os, platform, shutil, statistics as st, subprocess, sys, threading, time
from ctypes import wintypes
from datetime import datetime
from pathlib import Path

import psutil
import pynvml as nv
import torch

if not torch.cuda.is_available():
    sys.exit("FATAL: torch.cuda unavailable. Refusing to run: no CPU fallback is allowed.")

DATA = Path(__file__).resolve().parents[1] / "data"
ROWS = []


def add(item, kind, available, needs_admin=None, latency_ms=None, reading=None, note=""):
    ROWS.append(dict(item=item, kind=kind, available=available, needs_admin=needs_admin,
                     latency_ms=None if latency_ms is None else round(latency_ms, 4),
                     reading=reading, note=note))


def run(cmd, timeout=30):
    t = time.perf_counter()
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, (p.stdout + p.stderr).strip(), (time.perf_counter() - t) * 1e3
    except Exception as e:  # noqa: BLE001
        return -1, f"{type(e).__name__}: {e}", (time.perf_counter() - t) * 1e3


def ps(cmd, timeout=30):
    return run(["powershell", "-NoProfile", "-Command", cmd], timeout)


def is_admin():
    return bool(ctypes.windll.shell32.IsUserAnAdmin())


def median_call_ms(fn, n=200):
    ts = []
    for _ in range(n):
        t = time.perf_counter(); fn(); ts.append((time.perf_counter() - t) * 1e3)
    return st.median(ts)


class GpuLoad:
    """Background fp16 matmul load via torch (CUDA only; construction fails loudly without CUDA)."""
    def __enter__(self):
        self.stop = threading.Event()
        a = torch.randn(4096, 4096, device="cuda", dtype=torch.float16)

        def loop():
            while not self.stop.is_set():
                for _ in range(8):
                    a @ a
                torch.cuda.synchronize()
        self.t = threading.Thread(target=loop, daemon=True); self.t.start()
        time.sleep(2.0)
        return self

    def __exit__(self, *exc):
        self.stop.set(); self.t.join()


def median_clock(h, secs=1.0):
    xs, end = [], time.perf_counter() + secs
    while time.perf_counter() < end:
        xs.append(nv.nvmlDeviceGetClockInfo(h, nv.NVML_CLOCK_SM)); time.sleep(0.01)
    return st.median(xs)


def event_reasons(mask):
    names = []
    for n in dir(nv):
        if n.startswith(("nvmlClocksEventReason", "nvmlClocksThrottleReason")) and not n.endswith("All"):
            v = getattr(nv, n)
            if isinstance(v, int) and v and (mask & v) == v:
                names.append(n.replace("nvmlClocksEventReason", "").replace("nvmlClocksThrottleReason", ""))
    return sorted(set(names)) or ["None"]


# ---------------------------------------------------------------- environment
def audit_env(h):
    batt = psutil.sensors_battery()
    props = torch.cuda.get_device_properties(0)
    return dict(
        timestamp=datetime.now().isoformat(timespec="seconds"),
        admin=is_admin(), os=platform.platform(), python=sys.version.split()[0], torch=torch.__version__,
        execution_mode=f"CUDA via torch on {props.name} (no CPU fallback)",
        gpu_name=nv.nvmlDeviceGetName(h), sm_count=props.multi_processor_count,
        compute_capability=f"{props.major}.{props.minor}", vram_total_mib=props.total_memory // 2**20,
        driver=nv.nvmlSystemGetDriverVersion(), ac_plugged=None if batt is None else batt.power_plugged,
        battery_pct=None if batt is None else batt.percent, cpu_logical=psutil.cpu_count(),
        ambient_temp_c="NOT MEASURED (no sensor; enter manually per experiment)",
        nvcc=run(["nvcc", "--version"])[1].splitlines()[-1] if shutil.which("nvcc") else "not found",
        msvc_cl_on_path=bool(shutil.which("cl")),
    )


# ---------------------------------------------------------------- NVML sensors
def audit_nvml(h):
    reasons_fn = getattr(nv, "nvmlDeviceGetCurrentClocksEventReasons", None) or nv.nvmlDeviceGetCurrentClocksThrottleReasons
    metrics = {
        "power_w": lambda: nv.nvmlDeviceGetPowerUsage(h) / 1000,
        "sm_clock_mhz": lambda: nv.nvmlDeviceGetClockInfo(h, nv.NVML_CLOCK_SM),
        "mem_clock_mhz": lambda: nv.nvmlDeviceGetClockInfo(h, nv.NVML_CLOCK_MEM),
        "temp_c": lambda: nv.nvmlDeviceGetTemperature(h, nv.NVML_TEMPERATURE_GPU),
        "util_gpu_pct": lambda: nv.nvmlDeviceGetUtilizationRates(h).gpu,
        "vram_used_mib": lambda: nv.nvmlDeviceGetMemoryInfo(h).used // 2**20,
        "fan_pct": lambda: nv.nvmlDeviceGetFanSpeed(h),
        "total_energy_j": lambda: nv.nvmlDeviceGetTotalEnergyConsumption(h) / 1000,
        "clock_event_reasons": lambda: event_reasons(reasons_fn(h)),
    }
    with GpuLoad():
        for name, fn in metrics.items():
            try:
                val = fn()
                add(f"NVML {name}", "sensor", "Y", False, median_call_ms(fn), val, "read under GPU matmul load")
            except nv.NVMLError as e:
                add(f"NVML {name}", "sensor", "N", None, None, None, str(e))
        # how often does the value actually change? (effective refresh, not call rate)
        for name in ("power_w", "util_gpu_pct", "temp_c"):
            fn = metrics[name]; last = fn(); t_last = time.perf_counter(); dts = []; calls = 0
            end = t_last + 4.0
            while time.perf_counter() < end:
                v = fn(); calls += 1; t = time.perf_counter()
                if v != last:
                    dts.append((t - t_last) * 1e3); last, t_last = v, t
            if dts:
                p90 = sorted(dts)[int(0.9 * (len(dts) - 1))]
                add(f"NVML {name} update interval", "sensor", "Y", False, st.median(dts),
                    f"median {st.median(dts):.1f} ms, p90 {p90:.1f} ms over {len(dts)} changes; {calls/4:.0f} calls/s",
                    "latency_ms column = median interval between distinct values")
            else:
                add(f"NVML {name} update interval", "sensor", "N", False, None, "value never changed in 4 s", "")


# ---------------------------------------------------------------- power limit / clock locks
def smi(*a):
    return run(["nvidia-smi", *a])


def audit_power_and_clocks(h, admin, skip_lock):
    try:
        cur = nv.nvmlDeviceGetPowerManagementLimit(h)
        lo, hi = nv.nvmlDeviceGetPowerManagementLimitConstraints(h)
        dflt = nv.nvmlDeviceGetPowerManagementDefaultLimit(h)
        add("Power limit read (NVML)", "sensor", "Y", False, None,
            f"current {cur/1000:.1f} W, default {dflt/1000:.1f} W, range {lo/1000:.0f}-{hi/1000:.0f} W")
        t = time.perf_counter()
        try:
            nv.nvmlDeviceSetPowerManagementLimit(h, cur)  # same value: no-op if permitted
            add("Power limit set (NVML)", "actuator", "Y", True, (time.perf_counter() - t) * 1e3,
                "set to current value accepted", "effect size NOT tested (would need a lower limit under load)")
        except nv.NVMLError as e:
            add("Power limit set (NVML)", "actuator", "N", True, (time.perf_counter() - t) * 1e3, None, f"{e} (admin={admin})")
    except nv.NVMLError as e:
        add("Power limit read/set (NVML)", "actuator", "N", None, None, None, str(e))

    if skip_lock:
        add("nvidia-smi -lgc/-rgc (SM clock lock)", "actuator", "NOT_RUN", True, None, None, "--skip-clock-lock")
        return
    if not admin:
        rc, out, ms = smi("-rgc")
        add("nvidia-smi -lgc/-rgc (SM clock lock)", "actuator", "NOT_RUN", True, ms, None,
            f"not elevated; -rgc probe rc={rc}: {out[:120]!r}. Re-run from an Administrator shell for the apply/revert test.")
        add("nvidia-smi -lmc/-rmc (mem clock lock)", "actuator", "NOT_RUN", True, None, None, "not elevated")
        return

    try:
        with GpuLoad():
            before = median_clock(h, 1.5)
            target = int(min(1200, before * 0.6))
            rc, out, apply_ms = smi("-lgc", f"{target},{target}")
            t0 = time.perf_counter(); settle = None
            while time.perf_counter() - t0 < 3.0:
                if abs(nv.nvmlDeviceGetClockInfo(h, nv.NVML_CLOCK_SM) - target) <= 0.03 * target:
                    settle = (time.perf_counter() - t0) * 1e3
                    break
                time.sleep(0.005)
            locked = median_clock(h, 1.0)
            p_locked = nv.nvmlDeviceGetPowerUsage(h) / 1000
            rc2, out2, rev_ms = smi("-rgc")
            t0 = time.perf_counter(); rev_settle = None
            while time.perf_counter() - t0 < 3.0:
                if nv.nvmlDeviceGetClockInfo(h, nv.NVML_CLOCK_SM) > 0.9 * before:
                    rev_settle = (time.perf_counter() - t0) * 1e3
                    break
                time.sleep(0.005)
            after = median_clock(h, 1.0)
        add("nvidia-smi -lgc/-rgc (SM clock lock)", "actuator", "Y" if rc == 0 and rc2 == 0 else "N", True, settle,
            f"median SM clock {before:.0f} -> {locked:.0f} (target {target}) -> {after:.0f} MHz after revert; power while locked {p_locked:.1f} W",
            f"smi apply {apply_ms:.0f} ms, revert smi {rev_ms:.0f} ms, revert settle {rev_settle}; rc={rc}/{rc2} {out[:80]!r}")
    finally:
        smi("-rgc")
    try:
        memmax = nv.nvmlDeviceGetMaxClockInfo(h, nv.NVML_CLOCK_MEM)
        rc, out, ms = smi("-lmc", f"{memmax},{memmax}")
        add("nvidia-smi -lmc/-rmc (mem clock lock)", "actuator", "Y" if rc == 0 else "N", True, ms,
            f"lock to max {memmax} MHz rc={rc}", out[:120] + " (accept/reject only; effect NOT tested)")
    finally:
        smi("-rmc")


# ---------------------------------------------------------------- VRAM
def audit_vram(h):
    mi = nv.nvmlDeviceGetMemoryInfo(h)
    free_mib = mi.free // 2**20
    try:
        n = max(0, mi.free - 1024 * 2**20)
        t = time.perf_counter()
        x = torch.empty(n, dtype=torch.uint8, device="cuda"); torch.cuda.synchronize()
        ms = (time.perf_counter() - t) * 1e3
        del x; torch.cuda.empty_cache()
        add("VRAM headroom", "sensor", "Y", False, ms,
            f"total {mi.total//2**20} MiB, used {mi.used//2**20}, free {free_mib}; allocated {n//2**20} MiB ok",
            "WDDM paging onset NOT measured here (needs over-subscription test in W2)")
    except Exception as e:  # noqa: BLE001
        add("VRAM headroom", "sensor", "N", False, None, f"free {free_mib} MiB", f"alloc failed: {e}")


# ---------------------------------------------------------------- PDH GPU engine
def audit_pdh():
    try:
        import win32pdh
    except Exception as e:  # noqa: BLE001
        add("PDH GPU Engine counters", "sensor", "N", None, None, None, f"{type(e).__name__}: {e}")
        return
    with GpuLoad():  # expand AFTER the load starts so this process's engine instances exist
        paths = win32pdh.ExpandCounterPath(r"\GPU Engine(*)\Utilization Percentage")
        q = win32pdh.OpenQuery(); cs = {}
        for p in paths:
            try:
                cs[p] = win32pdh.AddCounter(q, p)
            except Exception:  # noqa: BLE001
                pass
        win32pdh.CollectQueryData(q); time.sleep(1.0)
        t = time.perf_counter(); win32pdh.CollectQueryData(q); ms = (time.perf_counter() - t) * 1e3
        pid = f"pid_{os.getpid()}_"; mine = 0.0; top = []
        for p, c in cs.items():
            try:
                v = win32pdh.GetFormattedCounterValue(c, win32pdh.PDH_FMT_DOUBLE)[1]
            except Exception:  # noqa: BLE001
                continue
            top.append((v, p))
            if pid in p:
                mine += v
    top.sort(reverse=True)
    add("PDH GPU Engine counters", "sensor", "Y" if cs else "N", False, ms,
        f"{len(cs)} engine instances; this process (pid {os.getpid()}) summed engine util {mine:.1f}%; top instance: {top[0][1][-60:] if top else 'n/a'}",
        "latency_ms = one CollectQueryData over all instances; counter refresh is ~1 s so >1 Hz polling is not useful")
    win32pdh.CloseQuery(q)


# ---------------------------------------------------------------- PresentMon / CPU power
def audit_presentmon():
    found = [shutil.which(n) for n in ("PresentMon", "PresentMon.exe")]
    for pat in (r"C:\Program Files\Intel\PresentMon", r"C:\Program Files\NVIDIA Corporation\FrameView"):
        if Path(pat).exists():
            found += [str(p) for p in Path(pat).rglob("*.exe") if "present" in p.name.lower() or "frameview" in p.name.lower()][:2]
    found = [c for c in found if c]
    add("PresentMon (frame times)", "sensor", "Y" if found else "N", True, None, found[0] if found else None,
        "capture needs admin or Performance Log Users membership; not run here" if found
        else "not installed; get the Intel PresentMon release binary")


def audit_cpu_power():
    rc, out, ms = ps("Get-CimInstance -Namespace root/LibreHardwareMonitor -ClassName Sensor -ErrorAction Stop | "
                     "Where-Object {$_.SensorType -eq 'Power'} | Select-Object Name,Value | Format-List | Out-String")
    ok = rc == 0 and "Name" in out
    add("LibreHardwareMonitor WMI (Ryzen package power)", "sensor", "Y" if ok else "N", None, ms,
        out[:200] if ok else None, "" if ok else "LHM not running / WMI namespace absent")
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.OpenFileMappingW.restype = wintypes.HANDLE
    k32.OpenFileMappingW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
    hm = k32.OpenFileMappingW(4, False, "Global\\HWiNFO_SENS_SM2")
    add("HWiNFO shared memory", "sensor", "Y" if hm else "N", None, None, "mapping opened" if hm else None,
        "" if hm else "HWiNFO not running with Shared Memory Support enabled")
    if hm:
        k32.CloseHandle(hm)
    try:
        import win32pdh
        q = win32pdh.OpenQuery()
        c = win32pdh.AddCounter(q, r"\Energy Meter(rapl_package0_pkg)\Power")

        def sample(secs):
            xs, end = [], time.perf_counter() + secs
            win32pdh.CollectQueryData(q)
            while time.perf_counter() < end:
                time.sleep(0.25); t = time.perf_counter(); win32pdh.CollectQueryData(q)
                xs.append((win32pdh.GetFormattedCounterValue(c, win32pdh.PDH_FMT_DOUBLE)[1], (time.perf_counter() - t) * 1e3))
            return [x[0] for x in xs], [x[1] for x in xs]
        idle, lat = sample(3.0)
        spinners = [subprocess.Popen([sys.executable, "-c", "while 1: pass"]) for _ in range(psutil.cpu_count())]
        try:
            time.sleep(1.0); busy, _ = sample(3.0)
        finally:
            for s in spinners:
                s.kill()
        add("Windows PDH Energy Meter rapl_package0_pkg", "sensor", "Y", False, st.median(lat),
            f"raw counter idle median {st.median(idle):.0f}, all-core spin median {st.median(busy):.0f} (n={len(idle)}/{len(busy)}, 250 ms polls)",
            "unit assumed mW (Microsoft Energy Meter docs) - NOT yet validated against a wall meter or HWiNFO; treat as relative until checked")
    except Exception as e:  # noqa: BLE001
        add("Windows PDH Energy Meter rapl_package0_pkg", "sensor", "N", None, None, None, f"{type(e).__name__}: {e}")
    ra = shutil.which("ryzenadj")
    add("ryzenadj (CPU power limits)", "actuator", "Y" if ra else "N", True, None, ra,
        "" if ra else "not on PATH; needs release binary + driver (admin); Ryzen 7940HS support not yet verified")


# ---------------------------------------------------------------- CPU actuators
def audit_cpu_actuators():
    p = psutil.Process()
    t = time.perf_counter(); orig = p.nice(); p.nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
    ms = (time.perf_counter() - t) * 1e3; p.nice(orig)
    add("CPU priority class", "actuator", "Y", False, ms, "BELOW_NORMAL set and reverted", "effect NOT tested here (needs contended fg test)")
    aff = p.cpu_affinity(); t = time.perf_counter(); p.cpu_affinity([aff[0]])
    ms = (time.perf_counter() - t) * 1e3; p.cpu_affinity(aff)
    add("CPU affinity", "actuator", "Y", False, ms, f"pinned to cpu {aff[0]} and restored ({len(aff)} logical)", "")

    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.SetProcessInformation.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    k32.CreateJobObjectW.restype = wintypes.HANDLE
    k32.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    k32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    spin = [sys.executable, "-c", "import time\nt=time.perf_counter();n=0\nwhile time.perf_counter()-t<2:n+=1\nprint(n)"]

    class PTS(ctypes.Structure):
        _fields_ = [("Version", wintypes.DWORD), ("ControlMask", wintypes.DWORD), ("StateMask", wintypes.DWORD)]

    def child_iters(eco):
        c = subprocess.Popen(spin, stdout=subprocess.PIPE, text=True); ms = None
        if eco:
            s = PTS(1, 1, 1); t = time.perf_counter()
            ok = k32.SetProcessInformation(int(c._handle), 4, ctypes.byref(s), ctypes.sizeof(s))
            ms = (time.perf_counter() - t) * 1e3 if ok else f"fail:{ctypes.get_last_error()}"
        return int(c.communicate()[0]), ms

    base, _ = child_iters(False)
    eco, ms = child_iters(True)
    add("EcoQoS (ProcessPowerThrottling)", "actuator", "Y" if isinstance(ms, float) else "N",
        False, ms if isinstance(ms, float) else None,
        f"spin-loop iterations in 2 s: normal {base}, EcoQoS {eco} ({100*(eco-base)/base:+.1f}%)",
        "single run each; indicative only, not an effect-size estimate" if isinstance(ms, float) else str(ms))

    class RATE(ctypes.Structure):
        _fields_ = [("ControlFlags", wintypes.DWORD), ("CpuRate", wintypes.DWORD)]
    c = subprocess.Popen([sys.executable, "-c", "while 1: pass"])
    try:
        pc = psutil.Process(c.pid); pc.cpu_percent(None); time.sleep(1.5); uncapped = pc.cpu_percent(None)
        job = k32.CreateJobObjectW(None, None)
        rate = max(1, int(10000 * 0.25 / psutil.cpu_count()))  # 25% of one core, expressed as 1/100 % of the whole machine
        info = RATE(0x1 | 0x4, rate); t = time.perf_counter()
        ok1 = k32.SetInformationJobObject(job, 15, ctypes.byref(info), ctypes.sizeof(info))
        ok2 = k32.AssignProcessToJobObject(job, int(c._handle)); ms = (time.perf_counter() - t) * 1e3
        pc.cpu_percent(None); time.sleep(3.0); capped = pc.cpu_percent(None)
        add("Job-object CPU hard cap", "actuator", "Y" if ok1 and ok2 else "N", False, ms,
            f"child CPU {uncapped:.0f}% of one core -> {capped:.0f}% (target ~25%)", f"ok={bool(ok1)}/{bool(ok2)} err={ctypes.get_last_error()}")
    finally:
        c.kill()


# ---------------------------------------------------------------- report
def render_md(env):
    L = ["# Capability audit", "",
         f"Run: {env['timestamp']} | admin: {env['admin']} | AC: {env['ac_plugged']} | {env['gpu_name']} "
         f"({env['sm_count']} SMs, cc {env['compute_capability']}, {env['vram_total_mib']} MiB) | driver {env['driver']}", "",
         "| Item | Kind | Avail | Admin | Latency ms | Reading / measured effect | Note |", "|---|---|---|---|---|---|---|"]

    def f(x):
        return "" if x is None else str(x).replace("|", "/").replace("\n", " ")
    for r in ROWS:
        L.append(f"| {f(r['item'])} | {r['kind']} | {r['available']} | {f(r['needs_admin'])} | {f(r['latency_ms'])} | {f(r['reading'])} | {f(r['note'])} |")
    L += ["", f"Execution mode: {env['execution_mode']}", f"Ambient temp: {env['ambient_temp_c']}",
          f"nvcc: {env['nvcc']} | MSVC cl on PATH: {env['msvc_cl_on_path']}"]
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-clock-lock", action="store_true")
    a = ap.parse_args()
    nv.nvmlInit(); h = nv.nvmlDeviceGetHandleByIndex(0); admin = is_admin()
    env = audit_env(h)
    steps = (lambda: audit_nvml(h), lambda: audit_power_and_clocks(h, admin, a.skip_clock_lock),
             lambda: audit_vram(h), audit_pdh, audit_presentmon, audit_cpu_power, audit_cpu_actuators)
    for step in steps:
        try:
            step()
        except Exception as e:  # noqa: BLE001  - one broken probe must not hide the rest
            add("AUDIT STEP ERROR", "error", "N", None, None, None, f"{type(e).__name__}: {e}")
    DATA.mkdir(exist_ok=True)
    (DATA / "capability_audit.json").write_text(json.dumps(dict(env=env, rows=ROWS), indent=2, default=str), encoding="utf-8")
    md = render_md(env)
    (DATA / "capability_audit.md").write_text(md, encoding="utf-8")
    print(md)


if __name__ == "__main__":
    main()
