"""Read-only clock-state checks for sprint R1 (docs/R1_PREREG.md amendment 15). Nothing here changes any GPU state: it only READS the pipe namespace listing (the helper's named pipe is detected by
listing the pipe namespace and NEVER connected to or opened: a client connection would make the helper reset the clocks on disconnect), the command
lines of running processes, and the SM clock / performance state / utilization (NVML, or the query interface of the vendor tool). The sweep is run with unlocked clocks;
these checks refuse to start a cell when the admin clock helper is present or the SM clock looks locked.

Heuristic fixed in the prereg (the thresholds are recorded in meta.json as HEURISTIC):
  * idle probe (GPU utilization 0 and the game process absent): an SM clock above 1000 MHz in performance state P0 for the whole 3 s probe counts as locked;
  * loaded cell: an SM clock sampled at least 200 times in the measured window with exactly one distinct value counts as locked and fails the cell.
"""
import os
import subprocess
import time

PIPE_NAME = "governor_clock"
PIPE_DIR = "\\\\.\\pipe\\"
PIPE_PATH = PIPE_DIR + PIPE_NAME
HELPER_MARKER = "clock_helper"
IDLE_SM_MHZ_ABOVE = 1000
PROBE_S = 3.0
PROBE_INTERVAL_S = 0.25
CONSTANT_MIN_SAMPLES = 200
HEURISTIC = {"idle_sm_mhz_above": IDLE_SM_MHZ_ABOVE, "pstate": "P0", "probe_s": PROBE_S, "idle_util_pct": 0, "constant_min_samples": CONSTANT_MIN_SAMPLES}


def _own_pids():
    pids = {os.getpid()}
    try:
        pids.add(os.getppid())
    except OSError:
        pass
    return pids


def default_list_cmdlines():
    """Command lines of the running processes (psutil if present, else the process table through PowerShell, read only). Best effort: an elevated process can be hidden from a
    non-elevated caller (the harness runs elevated). This process and its parent are skipped so that the check never matches its own command line."""
    own = _own_pids()
    try:
        import psutil
        out = []
        for p in psutil.process_iter(["pid", "cmdline"]):
            if p.info["pid"] in own:
                continue
            out.append(" ".join(p.info.get("cmdline") or []))
        return out
    except ImportError:
        pass
    root = os.environ.get("SystemRoot") or os.environ.get("SYSTEMROOT")
    if not root:
        return []
    ps = os.path.join(root, "System32", "WindowsPowerShell", "v1.0", "powershell.exe")
    r = subprocess.run([ps, "-NoProfile", "-Command", "Get-CimInstance Win32_Process | ForEach-Object { \"$($_.ProcessId)`t$($_.CommandLine)\" }"],
                       capture_output=True, text=True, timeout=30)
    out = []
    for line in r.stdout.splitlines():
        pid, _, cmd = line.partition("\t")
        if pid.strip().isdigit() and int(pid) in own:
            continue
        out.append(cmd)
    return out


def default_list_pipes():
    """Names in the pipe namespace (a directory listing; no pipe is opened or connected)."""
    return os.listdir(PIPE_DIR)


def helper_present(list_pipes=default_list_pipes, list_cmdlines=default_list_cmdlines):
    """-> list of reasons (empty = the admin clock helper is not running): its named pipe is listed in the pipe namespace (never connected to), or a process command line contains
    'clock_helper'. If the pipe namespace cannot be listed the helper is treated as PRESENT (refuse) and the error is recorded. A failing process lister is tolerated (best effort)."""
    found = []
    try:
        if PIPE_NAME in {str(n).lower() for n in list_pipes()}:
            found.append(f"named pipe {PIPE_PATH} is listed")
    except Exception as e:                                                                # noqa: BLE001
        found.append(f"pipe namespace could not be listed, treating the helper as present: {type(e).__name__}: {e}")
    try:
        for cmd in list_cmdlines() or []:
            if cmd and HELPER_MARKER in cmd.lower():
                found.append(f"a process command line contains '{HELPER_MARKER}': {cmd[:200]}")
                break
    except Exception:                                                                     # noqa: BLE001  (best effort, see docstring)
        pass
    return found


def _pstate(x):
    if isinstance(x, str):
        x = x.strip().upper()
        if x.startswith("P"):
            x = x[1:]
    return int(x)


def _num(x):
    if isinstance(x, str):
        x = x.replace("%", "").replace("MHz", "").strip()
    return float(x)


def nvml_reader():
    """One reading from NVML device 0 (read only): dict(sm MHz, pstate int, util %)."""
    import pynvml
    pynvml.nvmlInit()
    h = pynvml.nvmlDeviceGetHandleByIndex(0)
    return {"sm": int(pynvml.nvmlDeviceGetClockInfo(h, pynvml.NVML_CLOCK_SM)), "pstate": int(pynvml.nvmlDeviceGetPerformanceState(h)),
            "util": int(pynvml.nvmlDeviceGetUtilizationRates(h).gpu)}


def query_reader():
    """One reading through the vendor tool's query interface (read only)."""
    import shutil
    root = os.environ.get("SystemRoot") or os.environ.get("SYSTEMROOT") or ""
    exe = next((p for p in (os.path.join(root, "System32", "nvidia-smi.exe"), shutil.which("nvidia-smi")) if p and os.path.exists(p)), None)
    if exe is None:
        raise RuntimeError("the vendor query tool was not found")
    out = subprocess.run([exe, "--query-gpu=clocks.sm,pstate,utilization.gpu", "--format=csv,noheader"], capture_output=True, text=True, timeout=15, check=True).stdout
    sm, ps, util = [x.strip() for x in out.splitlines()[0].split(",")]
    return {"sm": sm, "pstate": ps, "util": util}


def default_reader():
    try:
        return nvml_reader()
    except Exception:                                                                     # noqa: BLE001
        return query_reader()


def probe_idle(reader=default_reader, clock=time.monotonic, sleep=time.sleep, duration_s=PROBE_S, interval_s=PROBE_INTERVAL_S):
    """The idle probe. Samples reader() for duration_s. status: 'locked' (every sample idle, P0 and above the SM threshold), 'unlocked', or 'inconclusive' (a reading failed or the
    GPU was not idle: the heuristic cannot be applied, which the callers treat as a refusal). The caller must have checked that the game process is absent."""
    base = {"thresholds": dict(HEURISTIC), "duration_s": duration_s}
    samples = []
    t0 = clock()
    try:
        while True:
            r = reader()
            samples.append({"sm": _num(r["sm"]), "pstate": _pstate(r["pstate"]), "util": _num(r["util"])})
            if clock() - t0 >= duration_s:
                break
            sleep(interval_s)
    except Exception as e:                                                                # noqa: BLE001
        return dict(base, status="inconclusive", locked=False, n=len(samples), error=f"{type(e).__name__}: {e}")
    util_max = max(x["util"] for x in samples)
    sm_min, sm_max = min(x["sm"] for x in samples), max(x["sm"] for x in samples)
    info = dict(base, n=len(samples), sm_min=sm_min, sm_max=sm_max, util_max=util_max, pstates=sorted({x["pstate"] for x in samples}))
    if util_max > 0:
        return dict(info, status="inconclusive", locked=False, error=f"GPU utilization {util_max} % during the probe: not idle")
    locked = sm_min > IDLE_SM_MHZ_ABOVE and all(x["pstate"] == 0 for x in samples)
    return dict(info, status="locked" if locked else "unlocked", locked=bool(locked))


def constant_clock(sm_samples, min_samples=CONSTANT_MIN_SAMPLES):
    """Loaded-cell check: constant = at least min_samples samples with exactly one distinct value."""
    n, distinct = len(sm_samples), len(set(sm_samples))
    return {"n": n, "distinct": distinct, "min_samples": min_samples, "constant": bool(n >= min_samples and distinct == 1)}
