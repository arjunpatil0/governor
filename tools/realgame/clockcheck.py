"""Read-only clock-state checks for sprint R1 (docs/R1_PREREG.md amendments 15 and 18). The only GPU action is the short CUDA load of the load test; nothing here changes any clock,
power limit or other GPU state. The helper's named pipe is detected by listing the pipe namespace and NEVER connected to or opened (a client connection would make the helper reset the
clocks on disconnect); the command lines of running processes are scanned as well.

Amendment 18 (supersedes the idle-reading lock test): the GPU is loaded for about 5 s with a CUDA kernel while the SM clock is sampled every 50 ms through NVML. PASS only if the maximum
SM clock is above 1980 MHz AND the clock-helper pipe is absent. Idle SM samples (3 s before the load), the performance state, the enforced power limit and the clocks-event reasons
mask during the load are information only and decide nothing. The load comes from an injectable load_fn(seconds); the default needs torch with CUDA and fails loudly without it.
In a loaded cell an SM clock sampled at least 200 times in the measured window with exactly one distinct value still counts as locked and fails the cell.
"""
import os
import subprocess
import threading
import time

PIPE_NAME = "governor_clock"
PIPE_DIR = "\\\\.\\pipe\\"
PIPE_PATH = PIPE_DIR + PIPE_NAME
HELPER_MARKER = "clock_helper"
PASS_SM_MHZ_ABOVE = 1980
LOAD_S = 5.0
SAMPLE_INTERVAL_S = 0.05
IDLE_INFO_S = 3.0
IDLE_INTERVAL_S = 0.25
CONSTANT_MIN_SAMPLES = 200
THRESHOLDS = {"max_sm_mhz_above": PASS_SM_MHZ_ABOVE, "load_s": LOAD_S, "sample_interval_s": SAMPLE_INTERVAL_S, "idle_info_s": IDLE_INFO_S, "constant_min_samples": CONSTANT_MIN_SAMPLES}


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


def enforced_power_limit_w(nv, h):
    """NVML enforced power limit in W (nvmlDeviceGetEnforcedPowerLimit / 1000); falls back to nvmlDeviceGetPowerManagementLimit; raises RuntimeError if neither can be read."""
    errs = []
    for name in ("nvmlDeviceGetEnforcedPowerLimit", "nvmlDeviceGetPowerManagementLimit"):
        try:
            return float(getattr(nv, name)(h)) / 1000.0
        except Exception as e:                                                            # noqa: BLE001
            errs.append(f"{name}: {type(e).__name__}: {e}")
    raise RuntimeError("cannot read the NVML power limit (" + "; ".join(errs) + ")")


class NvmlClockReader:
    """Device 0, read only: sm_clock(), pstate(), clock_reasons() (bitmask), enforced_power_limit_w()."""

    def __init__(self):
        import pynvml
        pynvml.nvmlInit()
        self.nv, self.h = pynvml, pynvml.nvmlDeviceGetHandleByIndex(0)

    def sm_clock(self):
        return int(self.nv.nvmlDeviceGetClockInfo(self.h, self.nv.NVML_CLOCK_SM))

    def pstate(self):
        return int(self.nv.nvmlDeviceGetPerformanceState(self.h))

    def clock_reasons(self):
        fn = getattr(self.nv, "nvmlDeviceGetCurrentClocksEventReasons", None) or self.nv.nvmlDeviceGetCurrentClocksThrottleReasons
        return int(fn(self.h))

    def enforced_power_limit_w(self):
        return enforced_power_limit_w(self.nv, self.h)


def default_load_fn(seconds, torch_module=None, clock=time.perf_counter):
    """Load the GPU for `seconds` with fp16 matmuls on a large tensor (torch, CUDA). No CPU fallback: without torch.cuda this raises RuntimeError. Always ends with
    torch.cuda.synchronize() and torch.cuda.empty_cache(), also after a failure."""
    torch = torch_module
    if torch is None:
        try:
            import torch
        except Exception as e:                                                            # noqa: BLE001
            raise RuntimeError(f"the clock load test needs torch with CUDA (import failed: {type(e).__name__}: {e}); there is no CPU fallback") from e
    if not torch.cuda.is_available():
        raise RuntimeError("the clock load test needs torch.cuda, which is not available; there is no CPU fallback")
    try:
        x = torch.randn(8192, 8192, device="cuda", dtype=torch.float16)
        y = torch.randn(8192, 8192, device="cuda", dtype=torch.float16)
        end = clock() + seconds
        while clock() < end:
            for _ in range(4):
                x @ y
            torch.cuda.synchronize()
    finally:
        torch.cuda.synchronize()
        torch.cuda.empty_cache()


def _try(fn):
    try:
        return fn(), None
    except Exception as e:                                                                # noqa: BLE001
        return None, f"{type(e).__name__}: {e}"


def load_test(reader, load_fn, clock=time.monotonic, sleep=time.sleep, load_s=LOAD_S, idle_s=IDLE_INFO_S, interval_s=SAMPLE_INTERVAL_S):
    """Idle samples (information), then load_fn(load_s) in a thread while the SM clock is sampled every interval_s for load_s seconds.
    -> dict(max_sm_mhz (None if nothing could be read), n_load_samples, load_error (None or text), read_error, info{...}). It decides nothing; see verdict()."""
    info = {"idle_sm_mhz": [], "pstate_idle": [], "idle_error": None, "pstate_load": [], "clock_reasons_mask_or": 0, "power_limit_w": None, "power_limit_error": None}
    t0 = clock()
    while True:
        sm, err = _try(reader.sm_clock)
        ps, _ = _try(reader.pstate)
        if err:
            info["idle_error"] = err
        else:
            info["idle_sm_mhz"].append(sm)
        if ps is not None and ps not in info["pstate_idle"]:
            info["pstate_idle"].append(ps)
        if clock() - t0 >= idle_s:
            break
        sleep(min(IDLE_INTERVAL_S, idle_s))
    box = {"error": None}

    def work():
        try:
            load_fn(load_s)
        except BaseException as e:                                                        # noqa: BLE001
            box["error"] = f"{type(e).__name__}: {e}"
    th = threading.Thread(target=work, daemon=True)
    th.start()
    sms, read_error = [], None
    t0 = clock()
    while True:
        sm, err = _try(reader.sm_clock)
        if err:
            read_error = err
        else:
            sms.append(sm)
        rs, _ = _try(reader.clock_reasons)
        if rs is not None:
            info["clock_reasons_mask_or"] |= int(rs)
        ps, _ = _try(reader.pstate)
        if ps is not None and ps not in info["pstate_load"]:
            info["pstate_load"].append(ps)
        if clock() - t0 >= load_s or box["error"]:
            break
        sleep(interval_s)
    th.join(timeout=load_s + 30.0)
    if th.is_alive() and box["error"] is None:
        box["error"] = "load_fn did not return in time"
    info["power_limit_w"], info["power_limit_error"] = _try(reader.enforced_power_limit_w)
    info["clock_reasons_hex"] = hex(info["clock_reasons_mask_or"])
    return {"max_sm_mhz": max(sms) if sms else None, "n_load_samples": len(sms), "load_error": box["error"], "read_error": read_error, "load_s": load_s, "info": info}


def verdict(helper, load):
    """-> list of problems (empty = PASS): the helper is present, the load test failed or could not read the clock, or the maximum SM clock under load is not above 1980 MHz."""
    problems = [f"admin clock helper is present ({h}): the sweep runs with unlocked clocks and no helper" for h in helper]
    if load.get("load_error"):
        problems.append(f"clock load test failed: {load['load_error']}")
    elif load.get("max_sm_mhz") is None:
        problems.append(f"clock load test failed: the SM clock could not be read ({load.get('read_error')})")
    elif load["max_sm_mhz"] <= PASS_SM_MHZ_ABOVE:
        problems.append(f"max SM clock under load is {load['max_sm_mhz']} MHz, not above {PASS_SM_MHZ_ABOVE} MHz: the clocks look limited or locked")
    return problems


def state_of(helper, load):
    return {"thresholds": dict(THRESHOLDS), "helper_present": list(helper), "load_test": load, "max_sm_mhz": (load or {}).get("max_sm_mhz"), "loaded_constant_check": None}


def default_load_test():
    """The real load test (NVML reader + torch load). A reader that cannot be built is reported as a load error (the check then fails loudly)."""
    try:
        reader = NvmlClockReader()
    except Exception as e:                                                                # noqa: BLE001
        return {"max_sm_mhz": None, "n_load_samples": 0, "load_error": f"NVML reader unavailable: {type(e).__name__}: {e}", "info": {}}
    return load_test(reader, default_load_fn)


def run_check(reader, load_fn, helper_fn=helper_present, clock=time.monotonic, sleep=time.sleep, **kw):
    """The whole clock check with injected reader and load_fn -> (problems, state)."""
    helper = list(helper_fn())
    load = load_test(reader, load_fn, clock=clock, sleep=sleep, **kw)
    return verdict(helper, load), state_of(helper, load)


def constant_clock(sm_samples, min_samples=CONSTANT_MIN_SAMPLES):
    """Loaded-cell check (unchanged by amendment 18): constant = at least min_samples samples with exactly one distinct value."""
    n, distinct = len(sm_samples), len(set(sm_samples))
    return {"n": n, "distinct": distinct, "min_samples": min_samples, "constant": bool(n >= min_samples and distinct == 1)}
