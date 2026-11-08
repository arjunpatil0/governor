"""Per-process GPU memory (v2 track). Sampled, read-only; it never touches the NVML energy counter.
On this machine (Windows WDDM) NVML names the processes that use the GPU but returns no memory figure for them (usedGpuMemory is N/A), so the figure comes from the
PDH counter "GPU Process Memory(pid_*)\\Dedicated Usage", the same source as Task Manager. PDH reports every adapter (the laptop's iGPU as well), so the NVIDIA adapter is
identified as the LUID under which NVML's own process list appears (the most common one), unless a LUID is given. If NVML does return a figure (other drivers) it is used as is.
Without PDH (not Windows, no pywin32) and without NVML figures the processes are listed with mib = None: nothing is guessed.
   VramReader.read() -> dict(t, total_mib, used_mib, luid, procs={pid: dict(mib, source, name)})
   VramPoller(period_s).start(); .latest; .samples (history for summaries); .summary(pids, t0, t1); .stop()"""
import re
import threading
import time

MIB = float(1 << 20)
NVML_NA = {(1 << 64) - 1, (1 << 32) - 1}
PDH_PATH = r"\GPU Process Memory(*)\Dedicated Usage"
_INST = re.compile(r"pid_(\d+)_luid_(0x[0-9a-fA-F]+_0x[0-9a-fA-F]+)_phys_(\d+)")


def nvml_process_mib(procs):
    """NVML process list (objects with .pid and .usedGpuMemory) -> {pid: MiB or None}. None and the NVML 'not available' sentinels are None, never 0."""
    out = {}
    for p in procs:
        used = getattr(p, "usedGpuMemory", None)
        out[int(p.pid)] = None if used is None or int(used) in NVML_NA else int(used) / MIB
    return out


def parse_pdh(values):
    """{PDH instance name: bytes} -> {luid: {pid: bytes}}; instance names that do not look like pid_<n>_luid_<l>_phys_<k> (e.g. the _Total instance) are skipped; phys_k entries of one pid and LUID are summed."""
    out = {}
    for name, v in values.items():
        m = _INST.search(name)
        if not m:
            continue
        pid, luid = int(m.group(1)), m.group(2).lower()
        d = out.setdefault(luid, {})
        d[pid] = d.get(pid, 0.0) + float(v)
    return out


def pick_luid(by_luid, nvml_pids, preferred=None):
    """The NVIDIA adapter's LUID: the one under which the most NVML-listed processes appear (ties: the larger summed memory). None if no NVML process is listed or none appears in PDH."""
    if preferred:
        return preferred.lower()
    best, key = None, (0, -1.0)
    for luid, pm in by_luid.items():
        k = (sum(1 for p in nvml_pids if p in pm), sum(pm.values()))
        if k[0] > 0 and k > key:
            best, key = luid, k
    return best


def merge(nvml_mib, by_luid, luid):
    """{pid: dict(mib, source)} for every NVML-listed process: NVML's own figure if it has one, else PDH on `luid`, else None."""
    procs = {}
    for pid, m in nvml_mib.items():
        if m is not None:
            procs[pid] = dict(mib=m, source="nvml")
        elif luid is not None and pid in by_luid.get(luid, {}):
            procs[pid] = dict(mib=by_luid[luid][pid] / MIB, source="pdh")
        else:
            procs[pid] = dict(mib=None, source="n/a")
    return procs


class PdhProcessMemory:
    """Persistent PDH query for the wildcard counter; read() -> {instance: bytes}. Raises at construction if PDH is unavailable (no silent fallback)."""

    def __init__(self):
        import win32pdh
        self.w = win32pdh
        self.q = win32pdh.OpenQuery()
        self.c = win32pdh.AddEnglishCounter(self.q, PDH_PATH)
        win32pdh.CollectQueryData(self.q)

    def read(self):
        self.w.CollectQueryData(self.q)
        return dict(self.w.GetFormattedCounterArray(self.c, self.w.PDH_FMT_LARGE))

    def close(self):
        self.w.CloseQuery(self.q)


def _all_nvml_procs(nv, h):
    procs = []
    for fn in ("nvmlDeviceGetComputeRunningProcesses", "nvmlDeviceGetGraphicsRunningProcesses"):
        try:
            procs += list(getattr(nv, fn)(h))
        except Exception:                                                    # noqa: BLE001  (a missing list is an empty one for this purpose)
            pass
    seen, out = set(), []
    for p in procs:
        if p.pid not in seen:
            seen.add(p.pid)
            out.append(p)
    return out


class VramReader:
    """nv: the pynvml module (or a fake), h: device handle, pdh: object with read() -> {instance: bytes} or None (then only NVML's own figures)."""

    def __init__(self, nv, h, pdh=None, luid=None, name_of=None, clock=time.perf_counter):
        self.nv, self.h, self.pdh, self.luid, self.clock = nv, h, pdh, luid, clock
        self.name_of = name_of or _psutil_name

    def read(self):
        mem = self.nv.nvmlDeviceGetMemoryInfo(self.h)
        nvml = nvml_process_mib(_all_nvml_procs(self.nv, self.h))
        by_luid = parse_pdh(self.pdh.read()) if self.pdh is not None else {}
        luid = pick_luid(by_luid, list(nvml), self.luid)
        procs = merge(nvml, by_luid, luid)
        for pid, d in procs.items():
            d["name"] = self.name_of(pid)
        return dict(t=self.clock(), total_mib=mem.total / MIB, used_mib=mem.used / MIB, luid=luid, procs=procs)


def _psutil_name(pid):
    try:
        import psutil
        return psutil.Process(pid).name()
    except Exception:                                                        # noqa: BLE001
        return None


def default_reader(luid=None):
    """VramReader on NVML device 0 with PDH if available; raises if NVML is missing."""
    import pynvml as nv
    nv.nvmlInit()
    h = nv.nvmlDeviceGetHandleByIndex(0)
    try:
        pdh = PdhProcessMemory()
    except Exception:                                                        # noqa: BLE001
        pdh = None
    return VramReader(nv, h, pdh, luid)


class VramPoller:
    """Samples a reader in a thread (NVML and PDH calls can take tens of ms). latest = the last sample or None; samples = every sample (a list of read() dicts).
    A failed read is counted in `errors` and does not stop the thread. reader=None builds default_reader(); without NVML the poller stays empty (latest None)."""

    def __init__(self, period_s=0.5, reader=None, start=True):
        self.period_s, self.latest, self.samples, self.errors = period_s, None, [], 0
        self.stop_ev = threading.Event()
        self.th = None
        try:
            self.reader = reader if reader is not None else default_reader()
        except Exception:                                                    # noqa: BLE001
            self.reader = None
            return
        if start:
            self.th = threading.Thread(target=self._run, daemon=True)
            self.th.start()

    def poll_once(self):
        try:
            s = self.reader.read()
        except Exception:                                                    # noqa: BLE001
            self.errors += 1
            return None
        self.latest = s
        self.samples.append(s)
        return s

    def _run(self):
        while not self.stop_ev.is_set():
            self.poll_once()
            self.stop_ev.wait(self.period_s)

    def read(self):
        return self.latest

    def summary(self, pids, t0, t1):
        """Per pid over the samples with t0 <= t <= t1: dict(peak_mib, median_mib, n) (None where the processes reported no figure), plus the system-wide used_mib peak under key 'system'."""
        out, win = {}, [s for s in self.samples if t0 <= s["t"] <= t1]
        for pid in pids:
            vals = sorted(s["procs"][pid]["mib"] for s in win if pid in s["procs"] and s["procs"][pid]["mib"] is not None)
            out[pid] = dict(peak_mib=vals[-1], median_mib=vals[len(vals) // 2], n=len(vals)) if vals else dict(peak_mib=None, median_mib=None, n=0)
        used = [s["used_mib"] for s in win]
        out["system"] = dict(peak_mib=max(used) if used else None, total_mib=win[-1]["total_mib"] if win else None, n=len(used))
        return out

    def stop(self):
        self.stop_ev.set()
        if self.th is not None and self.th.is_alive():
            self.th.join(2)
