"""One measured cell of sprint R1 (docs/R1_PREREG.md): preflight, metadata, the rest rule and run_cell. NEVER changes GPU clocks or power limits.

Everything that needs Windows or hardware (pynvml, winreg, psutil, ctypes libraries, typeperf, the LLM and PresentMon processes) sits behind `Probes` / `Deps` objects whose real
implementations import lazily, so the flow is tested with fakes on any OS.

Flow of run_cell (the prereg is being amended: the LLM is loaded before the warm-up, GO is sent at the START of the warm-up, so it decodes through the warm-up; tok/s is counted inside the window only):
  QPC check -> spawn the LLM (not SOLO), wait for READY, check EXEC_MODE (IGPU: 780M/Radeon only) -> (PRIO_IDLE: set + read back) -> 50 ms sampler -> PresentMon capture (not LLM_ALONE) ->
  [warm-up starts: GO <t_close> to the LLM, PDH shared-memory read 1 (during the warm-up, never after t_open)] -> [t_open: energy read 1 immediately] -> window ->
  [t_close: energy read 2, PDH read 2, PRIO_IDLE read-back] -> wait DONE -> stop capture -> parse + gap checks + reset check -> result.json.
LLM_ALONE runs in its own invocation (run.py --llm-alone) with the game process absent.
The game itself is started by the operator, not by this rig (UNVERIFIED how the benchmark scene is restarted per cell: see docs/R1_SETUP.md once written)."""
import dataclasses
import hashlib
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import threading
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path

from tools.realgame import clockcheck, gpu_priority, metrics, presentmon

ARMS = ("SOLO", "UNGATED", "PRIO_IDLE", "DUTY50", "IGPU", "LLM_ALONE")
EXPECTED_LLAMA_COMMIT = "620d2225c"
PRESENTMON_SHA256_PREREG = "b2a706bc6ad475749e3b7e3409263aa1e6906d45bdcf993f6dbc0f660188f1af"
# NVML throttle bits. The raw OR-ed mask is recorded as throttle_mask_or. SwPowerCap (0x4) is a separate boolean (throttle_swpowercap: on a power-limited laptop it is routine).
# throttle_flag (the "throttling" flag of the list) counts only HwSlowdown 0x8, SwThermalSlowdown 0x20, HwThermalSlowdown 0x40, HwPowerBrakeSlowdown 0x80 (the rig's definition; the prereg
# names the flag but not the bits). Idle (0x1), AppClocks (0x2), SyncBoost and Display bits are not counted.
THROTTLE_SWPOWERCAP = 0x4
THROTTLE_FLAG_MASK = 0x8 | 0x20 | 0x40 | 0x80
QPC_TOLERANCE_S = 0.001


class CellRefused(RuntimeError):
    """A deterministic refusal inside a cell (wrong device, power-static changed, DLL dir missing, a failing priority call, ...): repeating the cell cannot help, so the sweep stops at once."""


class PreflightError(RuntimeError):
    def __init__(self, failures):
        self.failures = list(failures)
        super().__init__("preflight refused:\n  " + "\n  ".join(self.failures))


@dataclass
class Config:
    repo_root: Path
    llm_exe: Path
    model: Path
    prompt: Path
    presentmon_exe: Path
    game_process: str
    armoury_mode: "str | None"
    llama_dir: Path
    n_prompt: int
    seed: int = 89770043
    warmup_s: float = 20.0
    window_s: float = 60.0
    pm_settle_s: float = 2.0
    ready_timeout_s: float = 300.0
    done_timeout_s: float = 60.0
    capture_stop_timeout_s: float = 10.0
    sampler_interval_s: float = 0.05
    llama_commit: str = EXPECTED_LLAMA_COMMIT
    llm_exe_vk: "Path | None" = None           # the Vulkan build of the driver, used only for the IGPU arm
    igpu_vk_index: "int | None" = None         # DEPRECATED and ignored: Vulkan device order is not stable; the IGPU arm selects its device by description (igpu_device_match)
    igpu_device_match: str = "780M"            # RG_DEVICE_MATCH passed to the IGPU child (substring of the ggml device description, case-insensitive)
    cuda_device_match: str = "RTX"             # RG_DEVICE_MATCH passed to the CUDA arms
    allow_pm_hash_mismatch: bool = False       # explicit override of the PresentMon sha256 check; recorded in meta.json
    expect_power_scheme: "str | None" = None   # --expect-power-scheme NAME_OR_GUID: preflight and every cell start refuse when the active Windows power scheme differs
    power_static_ref: "dict | None" = None     # amendment 19 (replaced): the sweep-start nvidia-smi static power fields; every cell start must match them (set by run.py)


def validate_game_process(name):
    """The game process name must end with '.exe' (case-insensitive), not start with '-' and contain no whitespace or path separators (it is passed to PresentMon on a command line)."""
    if (not isinstance(name, str) or not name.lower().endswith(".exe") or name.startswith("-") or name != name.strip() or len(name) <= 4
            or any(ch in name for ch in ' \t\r\n/\\"')):
        raise ValueError(f"--game-process must be an executable name ending in .exe, not starting with '-' and without spaces or path separators: {name!r}")
    return name


# ------------------------------------------------------------------ hashing
_SHA_CACHE = {}


def _hash_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_file(path):
    """sha256 hex, cached by (path, mtime_ns, size)."""
    st = os.stat(path)
    key = (str(Path(path).resolve()), st.st_mtime_ns, st.st_size)
    if key not in _SHA_CACHE:
        _SHA_CACHE[key] = _hash_file(path)
    return _SHA_CACHE[key]


# ------------------------------------------------------------------ probes (real implementations, lazy)
_TOOLS = {}


def tool_paths():
    """Full paths of git (shutil.which over the absolute PATH entries, the current directory excluded, resolved once and cached), tasklist and typeperf (%SystemRoot%\\System32).
    Nothing is looked up through the current working directory."""
    if not _TOOLS:
        cwd = os.path.normcase(os.path.abspath(os.getcwd()))
        safe = os.pathsep.join(d for d in os.environ.get("PATH", "").split(os.pathsep) if d and os.path.isabs(d) and os.path.normcase(os.path.abspath(d)) != cwd)
        git = shutil.which("git", path=safe)
        if not git:
            raise RuntimeError("git not found on PATH (the current directory is never searched)")
        git = os.path.abspath(git)
        if os.path.normcase(os.path.dirname(git)) == cwd:
            raise RuntimeError(f"git resolved to the current working directory ({git}): refusing")
        sysroot = os.environ.get("SystemRoot") or os.environ.get("SYSTEMROOT")
        if not sysroot:
            raise RuntimeError("SystemRoot is not set: cannot resolve tasklist and typeperf")
        sys32 = Path(sysroot) / "System32"
        _TOOLS.update(git=git, tasklist=str(sys32 / "tasklist.exe"), typeperf=str(sys32 / "typeperf.exe"))
    return dict(_TOOLS)


GIT_TIMEOUT_S = 30
SMI_INFO_TIMEOUT_S = 20


def _git(path, *args):
    try:
        return subprocess.run([tool_paths()["git"], "-C", str(path), *args], capture_output=True, text=True, check=True, timeout=GIT_TIMEOUT_S).stdout
    except subprocess.TimeoutExpired as e:
        raise RuntimeError(f"git {' '.join(args[:2])} in {path} timed out after {GIT_TIMEOUT_S} s: refusing") from e


class PowerSchemeError(RuntimeError):
    """The active Windows power scheme cannot be read or parsed."""


_SCHEME_RE = re.compile(r"Power Scheme GUID:\s*([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})\s*(?:\((.*)\))?")


def parse_power_scheme(text):
    """`powercfg /getactivescheme` text -> (guid lower case, name). Anything else -> PowerSchemeError."""
    m = _SCHEME_RE.search(text) if isinstance(text, str) else None
    if not m:
        raise PowerSchemeError(f"cannot parse the powercfg /getactivescheme output: {str(text)[:120]!r}")
    return m.group(1).lower(), (m.group(2) or "").strip()


def read_active_power_scheme(run=None, system_root=None):
    """Read only: %SystemRoot%/System32/powercfg.exe /getactivescheme (full path, fixed argv, no shell, 20 s timeout) -> (guid, name). run and system_root are injectable."""
    run = run or subprocess.run
    root = system_root or os.environ.get("SystemRoot") or r"C:\Windows"
    try:
        out = run([str(Path(root) / "System32" / "powercfg.exe"), "/getactivescheme"], capture_output=True, text=True, timeout=SMI_INFO_TIMEOUT_S, check=True, shell=False).stdout
    except Exception as e:                                                                # noqa: BLE001
        raise PowerSchemeError(f"cannot read the active power scheme ({type(e).__name__}: {e})") from e
    return parse_power_scheme(out)


def power_scheme_matches(expect, guid, name):
    """expect is the exact guid or a case-insensitive substring of the scheme name."""
    e = str(expect).strip().lower()
    return bool(e) and (e == str(guid).lower() or e in str(name).lower())


def read_power_scheme(probes):
    """-> (guid, name) through probes.power_scheme(); any failure -> PowerSchemeError."""
    try:
        guid, name = probes.power_scheme()
        return guid, name
    except PowerSchemeError:
        raise
    except Exception as e:                                                                # noqa: BLE001
        raise PowerSchemeError(f"cannot read the active power scheme ({type(e).__name__}: {e})") from e


def power_scheme_problem(cfg, probes):
    """None when --expect-power-scheme is not given or the active scheme matches; else the refusal text (an unreadable scheme refuses only when the flag is given)."""
    if not cfg.expect_power_scheme:
        return None
    try:
        guid, name = read_power_scheme(probes)
    except PowerSchemeError as e:
        return f"power scheme unreadable ({e}); --expect-power-scheme {cfg.expect_power_scheme!r} cannot be confirmed"
    if not power_scheme_matches(cfg.expect_power_scheme, guid, name):
        return f"power scheme mismatch: active scheme is {name!r} ({guid}), --expect-power-scheme is {cfg.expect_power_scheme!r}"
    return None


def info_timeout_text(e):
    """The record text of a failed information-only subprocess: 'unavailable (TimeoutExpired after 20 s)' or 'unavailable (<Type>: <text>)'."""
    if isinstance(e, subprocess.TimeoutExpired):
        return f"unavailable (TimeoutExpired after {SMI_INFO_TIMEOUT_S} s)"
    return f"unavailable ({type(e).__name__}: {e})"


def _process_table():
    """[(pid, name)] via psutil if present, else tasklist (Windows)."""
    try:
        import psutil
        return [(p.info["pid"], p.info["name"]) for p in psutil.process_iter(["pid", "name"])]
    except ImportError:
        pass
    out = subprocess.run([tool_paths()["tasklist"], "/FO", "CSV", "/NH"], capture_output=True, text=True, check=True, timeout=30).stdout
    rows = []
    for line in out.splitlines():
        parts = [x.strip('"') for x in line.split('","')]
        if len(parts) >= 2 and parts[1].isdigit():
            rows.append((int(parts[1]), parts[0].strip('"')))
    return rows


_NVSMI_EXTRA = (r"C:\Program Files\NVIDIA Corporation\NVSMI\nvidia-smi.exe",)


def nvidia_smi_exe():
    """Full path of nvidia-smi: %SystemRoot%\\System32 first, then the NVSMI install folder. PATH and the current directory are never searched."""
    root = os.environ.get("SystemRoot") or os.environ.get("SYSTEMROOT")
    cands = ([str(Path(root) / "System32" / "nvidia-smi.exe")] if root else []) + list(_NVSMI_EXTRA)
    for c in cands:
        if os.path.isfile(c):
            return c
    raise RuntimeError(f"nvidia-smi was not found at any of {cands}")


def nvml_power_limit_w(nv, h):
    """Enforced power limit in W: nvmlDeviceGetEnforcedPowerLimit / 1000, else nvmlDeviceGetPowerManagementLimit / 1000, else RuntimeError."""
    return clockcheck.enforced_power_limit_w(nv, h)


POWER_STATIC_TOL_W = 0.5
POWER_STATIC_FIELDS = (("default_power_limit_w", "Default Power Limit", "default"), ("min_power_limit_w", "Min Power Limit", "min"), ("max_power_limit_w", "Max Power Limit", "max"))
_POWER_LINE = re.compile(r"^\s*(Default Power Limit|Min Power Limit|Max Power Limit|Current Power Limit)\s*:\s*(.*?)\s*$", re.I)


class PowerStaticError(RuntimeError):
    pass


def parse_power_static(text):
    """Parse the nvidia-smi POWER query (-q -d POWER) text -> dict(default_power_limit_w, min_power_limit_w, max_power_limit_w, current_power_limit_w (information, may be None), raw_lines).
    For each label the first numeric value ('80.00 W') is used; every matching line is kept in raw_lines. Default, min and max must be present and numeric, else PowerStaticError."""
    raw, vals = [], {}
    for line in str(text or "").splitlines():
        m = _POWER_LINE.match(line)
        if not m:
            continue
        raw.append(line.strip())
        label = m.group(1).lower()
        n = re.match(r"^([-+]?\d+(?:\.\d+)?)\s*W?$", m.group(2), re.I)
        if n and label not in vals:
            vals[label] = float(n.group(1))
    out, missing = {}, []
    for key, label, _ in POWER_STATIC_FIELDS:
        if label.lower() in vals:
            out[key] = vals[label.lower()]
        else:
            missing.append(label)
    if missing:
        raise PowerStaticError(f"cannot parse the static power fields from the nvidia-smi POWER query (-q -d POWER) (no numeric value for: {', '.join(missing)}): refusing")
    out["current_power_limit_w"] = vals.get("current power limit")
    out["raw_lines"] = raw
    return out


class NvmlPowerStaticReader:
    """Default, min and max power limit from NVML (no process is spawned): nvmlDeviceGetPowerManagementDefaultLimit and nvmlDeviceGetPowerManagementLimitConstraints, mW -> W. Device 0."""

    def __init__(self, nv=None):
        if nv is None:
            import pynvml as nv
        nv.nvmlInit()
        self.nv, self.h = nv, nv.nvmlDeviceGetHandleByIndex(0)

    def read(self):
        mn, mx = self.nv.nvmlDeviceGetPowerManagementLimitConstraints(self.h)
        return {"default_power_limit_w": float(self.nv.nvmlDeviceGetPowerManagementDefaultLimit(self.h)) / 1000.0, "min_power_limit_w": float(mn) / 1000.0,
                "max_power_limit_w": float(mx) / 1000.0, "source": "nvml"}


def read_power_static(probes):
    """The static power fields through probes.nvml_power_static() (NVML). Any failure -> PowerStaticError (refusal)."""
    try:
        got = probes.nvml_power_static()
        out = {k: float(got[k]) for k, _, _ in POWER_STATIC_FIELDS}
    except Exception as e:                                                                # noqa: BLE001
        raise PowerStaticError(f"cannot read the static power fields (default, min, max power limit) from NVML ({type(e).__name__}: {e}): refusing") from e
    out["source"] = "nvml"
    return out


def parse_power_static_info(text):
    """Information only: the raw Default/Min/Max/Current Power Limit lines of the nvidia-smi POWER text and the dynamic current limit (None if absent)."""
    raw, cur = [], None
    for line in str(text or "").splitlines():
        m = _POWER_LINE.match(line)
        if not m:
            continue
        raw.append(line.strip())
        n = re.match(r"^([-+]?\d+(?:\.\d+)?)\s*W?$", m.group(2), re.I)
        if m.group(1).lower() == "current power limit" and n and cur is None:
            cur = float(n.group(1))
    return {"current_power_limit_w": cur, "raw_lines": raw}


def power_static_problems(ref, now, tol_w=POWER_STATIC_TOL_W):
    """Default, min and max power limit must equal the sweep-start values within tol_w. The dynamic current limit is excluded. -> list of texts (empty = unchanged)."""
    bad = []
    for key, label, short in POWER_STATIC_FIELDS:
        if abs(float(now[key]) - float(ref[key])) > tol_w + 1e-9:
            bad.append(f"static power field changed since sweep start: {short} power limit is {now[key]} W, was {ref[key]} W (more than {tol_w} W)")
    return bad


def sweep_start_records(probes):
    """Amendment 21, at sweep start (also --llm-alone): the full nvidia-smi text, display_active / display_mode and the NVML name, driver version and VRAM total. A failing source is
    recorded as 'unavailable (...)' (a record, not a refusal)."""
    def get(fn, keys):
        try:
            got = fn()
            return {k: got[k] for k in keys}
        except Exception as e:                                                            # noqa: BLE001
            return {k: info_timeout_text(e) for k in keys}
    try:
        text = probes.nvidia_smi_text()
    except Exception as e:                                                                # noqa: BLE001
        text = info_timeout_text(e)
    rec = {"nvidia_smi_processes": text}
    try:                                                                                  # information only (raw lines, dynamic current limit): never used in a check
        info = parse_power_static_info(probes.nvidia_smi_power_text())
    except Exception as e:                                                                # noqa: BLE001
        info = info_timeout_text(e)
    rec["nvidia_smi_power"] = info
    try:
        rec["power_static"] = read_power_static(probes)
    except Exception as e:                                                                # noqa: BLE001
        rec["power_static"] = f"unavailable ({type(e).__name__}: {e})"
    try:
        rec["elevated"] = probes.is_elevated()
    except Exception:                                                                     # noqa: BLE001
        rec["elevated"] = None
    try:
        rec["power_scheme_guid"], rec["power_scheme_name"] = read_power_scheme(probes)
    except Exception as e:                                                                # noqa: BLE001
        rec["power_scheme_guid"] = rec["power_scheme_name"] = info_timeout_text(e)
    rec.update(get(probes.nvidia_smi_display, ("display_active", "display_mode")))
    rec.update(get(probes.nvml_identity, ("nvml_name", "nvml_driver_version", "vram_total_mib")))
    return rec


class SystemProbes:
    def git_head(self, path):
        return _git(path, "rev-parse", "HEAD").strip()

    def git_dirty(self, path):
        return _git(path, "status", "--porcelain").splitlines()

    def process_running(self, name):
        return self.find_pid(name) is not None

    def find_pid(self, name):
        pids = sorted(pid for pid, n in _process_table() if n and n.lower() == name.lower())
        return pids[0] if pids else None

    def on_ac(self):
        """True on AC, False on battery, None if unknown (non-Windows or the call failed)."""
        if sys.platform != "win32":
            return None
        import ctypes
        from ctypes import wintypes

        class SPS(ctypes.Structure):
            _fields_ = [("ACLineStatus", ctypes.c_ubyte), ("BatteryFlag", ctypes.c_ubyte), ("BatteryLifePercent", ctypes.c_ubyte), ("SystemStatusFlag", ctypes.c_ubyte),
                        ("BatteryLifeTime", wintypes.DWORD), ("BatteryFullLifeTime", wintypes.DWORD)]
        s = SPS()
        k32 = ctypes.WinDLL("kernel32")
        k32.GetSystemPowerStatus.argtypes = [ctypes.POINTER(SPS)]
        k32.GetSystemPowerStatus.restype = wintypes.BOOL
        if not k32.GetSystemPowerStatus(ctypes.byref(s)):
            return None
        return {0: False, 1: True}.get(s.ACLineStatus)

    def exists(self, path):
        return Path(path).exists()

    def hags(self):
        """HKLM\\SYSTEM\\CurrentControlSet\\Control\\GraphicsDrivers HwSchMode (2 = on, 1 = off); 'unavailable' if it cannot be read."""
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\GraphicsDrivers") as k:
                return winreg.QueryValueEx(k, "HwSchMode")[0]
        except Exception as e:                                                            # noqa: BLE001
            return f"unavailable ({type(e).__name__})"

    def driver_version(self):
        try:
            import pynvml
            pynvml.nvmlInit()
            v = pynvml.nvmlSystemGetDriverVersion()
            return v.decode() if isinstance(v, bytes) else v
        except Exception as e:                                                            # noqa: BLE001
            return f"unavailable ({type(e).__name__})"

    def sha256(self, path):
        return sha256_file(path)

    def presentmon_version(self, exe):
        return presentmon.version(exe)

    def process_snapshot(self):
        return sorted({n for _, n in _process_table() if n})

    def admin_helper_present(self):
        """Reasons the admin clock helper looks present (named pipe or a process command line); empty list = absent. Read only."""
        return clockcheck.helper_present()

    def clock_load_test(self):
        """The amendment 18 load test (about 3 s idle samples + 5 s CUDA load, SM clock sampled through NVML). Used by --check-clocks only, with the game absent."""
        return clockcheck.default_load_test()

    def nvml_power_static(self):
        """Default, min, max power limit (W) from NVML; no process is spawned (used at sweep start and at every cell start)."""
        return NvmlPowerStaticReader().read()

    def power_scheme(self):
        """(guid, name) of the active Windows power scheme (read only powercfg, see read_active_power_scheme)."""
        return read_active_power_scheme()

    def file_stat(self, path):
        """(size, mtime) of a file."""
        st = Path(path).stat()
        return st.st_size, st.st_mtime

    def git_changed(self, root, head, paths):
        """Names of files that differ between `head` and HEAD under `paths` (git diff --name-only head HEAD -- paths)."""
        return _git(root, "diff", "--name-only", head, "HEAD", "--", *paths).split()

    def nvidia_smi_power_text(self):
        """INFORMATION ONLY, sweep start only: the text of the nvidia-smi POWER query (-q -d POWER) (read only; full path, fixed argv, no shell; 20 s timeout)."""
        return subprocess.run([nvidia_smi_exe(), "-q", "-d", "POWER"], capture_output=True, text=True, timeout=SMI_INFO_TIMEOUT_S, check=True, shell=False).stdout

    def nvidia_smi_text(self):
        """The full text of nvidia-smi (resolved by full path, fixed argv, no shell)."""
        return subprocess.run([nvidia_smi_exe()], capture_output=True, text=True, timeout=SMI_INFO_TIMEOUT_S, check=True, shell=False).stdout

    def nvidia_smi_display(self):
        """display_active and display_mode from the query interface (fixed argv, full path, no shell)."""
        out = subprocess.run([nvidia_smi_exe(), "--query-gpu=display_active,display_mode", "--format=csv,noheader"], capture_output=True, text=True, timeout=SMI_INFO_TIMEOUT_S, check=True,
                             shell=False).stdout
        active, _, mode = out.splitlines()[0].partition(",")
        return {"display_active": active.strip(), "display_mode": mode.strip()}

    def nvml_identity(self):
        import pynvml
        pynvml.nvmlInit()
        h = pynvml.nvmlDeviceGetHandleByIndex(0)
        name, drv = pynvml.nvmlDeviceGetName(h), pynvml.nvmlSystemGetDriverVersion()
        return {"nvml_name": name.decode() if isinstance(name, bytes) else name, "nvml_driver_version": drv.decode() if isinstance(drv, bytes) else drv,
                "vram_total_mib": pynvml.nvmlDeviceGetMemoryInfo(h).total / 2**20}

    def is_elevated(self):
        """True if the process runs elevated (ctypes shell32.IsUserAnAdmin, loaded lazily); None if unknown."""
        if sys.platform != "win32":
            return None
        try:
            import ctypes
            return bool(ctypes.WinDLL("shell32").IsUserAnAdmin())
        except Exception:                                                                 # noqa: BLE001
            return None


def pm_hash_problem(cfg, probes):
    """None if sha256(PresentMon exe) equals the prereg value or the mismatch is explicitly allowed; else the refusal text. Hashing only reads the file (no execution)."""
    sha = probes.sha256(cfg.presentmon_exe)
    if sha == PRESENTMON_SHA256_PREREG or cfg.allow_pm_hash_mismatch:
        return None
    return f"PresentMon sha256 {sha} does not equal the prereg value {PRESENTMON_SHA256_PREREG} (override: --allow-pm-hash-mismatch, recorded in meta)"


def clock_state_check(probes, game_process, run_load=False):
    """Amendment 15/18 checks. -> (problems, state). The admin clock helper must be absent (pipe listing and process command lines, read only). With run_load=True (--check-clocks, game
    absent) the load test also runs and its verdict applies: PASS needs a max SM clock above 1980 MHz under load. In preflight and in every cell run_load is False: the gate is the
    clock_check.json file, and a 5 s load inside a measured sweep would disturb it. state['load_test'] is None then."""
    helper = list(probes.admin_helper_present())
    load = probes.clock_load_test() if run_load else None
    if load is None:
        problems = clockcheck.verdict(helper, {"max_sm_mhz": clockcheck.PASS_SM_MHZ_ABOVE + 1, "load_error": None}, check_power=False)
    else:
        problems = clockcheck.verdict(helper, load)
    return problems, clockcheck.state_of(helper, load)


DLL_SPEC = {"cuda": ("build", "ggml-cuda.dll"), "vulkan": ("build_vk", "ggml-vulkan.dll")}


def llm_dll_dir(cfg, backend):
    """Absolute resolved llama.cpp DLL directory that must be prepended to the LLM child's PATH."""
    return Path(cfg.llama_dir, DLL_SPEC[backend][0], "bin").resolve()


def dll_dir_problems(cfg, probes, backend):
    d = llm_dll_dir(cfg, backend)
    if not probes.exists(d):
        return [f"{backend} llama.cpp DLL directory does not exist: {d}"]
    return [f"{backend} llama.cpp DLL directory {d} lacks {n}" for n in ("ggml-base.dll", DLL_SPEC[backend][1]) if not probes.exists(d / n)]


def format_rc(rc):
    if rc is None:
        return "unknown"
    if rc < 0 or rc >= 0xC0000000:
        u = rc & 0xFFFFFFFF
        return f"{rc} = 0x{u:08X}" + (" 'DLL not found'" if u == 0xC0000135 else "")
    return str(rc)


def preflight(cfg, probes=None, need_game=True, game_absent=False, need_vk=False, need_presentmon=True):
    """Raises PreflightError listing every refusal; returns None when the rig may run. game_absent: the game process must NOT be running (LLM_ALONE invocation)."""
    probes = probes or SystemProbes()
    bad = []
    try:
        dirty = probes.git_dirty(cfg.repo_root)
        if dirty:
            bad.append(f"git tree is dirty ({len(dirty)} entries, first: {dirty[0]!r}); commit before measuring")
    except Exception as e:                                                                # noqa: BLE001
        bad.append(f"git state of {cfg.repo_root} unavailable: {e}")
    if not cfg.armoury_mode:
        bad.append("--armoury-mode not given: the Armoury Crate mode must be stated for every run")
    try:
        head = probes.git_head(cfg.llama_dir)
        if not head.startswith(cfg.llama_commit):
            bad.append(f"llama.cpp tree {cfg.llama_dir} is at {head[:12]}, not {cfg.llama_commit}")
        if probes.git_dirty(cfg.llama_dir):
            bad.append(f"llama.cpp tree is dirty: {cfg.llama_dir}")
    except Exception as e:                                                                # noqa: BLE001
        bad.append(f"llama.cpp git state of {cfg.llama_dir} unavailable: {e}")
    if need_game and not probes.process_running(cfg.game_process):
        bad.append(f"game process {cfg.game_process} is not running")
    if game_absent and probes.process_running(cfg.game_process):
        bad.append(f"game process {cfg.game_process} is running: LLM_ALONE must be measured with the game absent")
    ac = probes.on_ac()
    if ac is not True:
        bad.append("not on AC power" if ac is False else "AC power state unknown: cannot confirm the laptop is on AC")
    for label, p in (("LLM executable", cfg.llm_exe), ("model", cfg.model), ("prompt", cfg.prompt)) + ((("PresentMon", cfg.presentmon_exe),) if need_presentmon else ()) + ((("Vulkan LLM executable", cfg.llm_exe_vk),) if need_vk else ()):
        if p is None or not probes.exists(p):
            bad.append(f"{label} not found: {p}")
    bad += dll_dir_problems(cfg, probes, "cuda")
    if need_vk:
        bad += dll_dir_problems(cfg, probes, "vulkan")
    if need_presentmon and probes.exists(cfg.presentmon_exe):
        why = pm_hash_problem(cfg, probes)
        if why:
            bad.append(why)
    try:
        validate_game_process(cfg.game_process)
    except ValueError as e:
        bad.append(str(e))
    bad += clock_state_check(probes, cfg.game_process)[0]
    why = power_scheme_problem(cfg, probes)
    if why:
        bad.append(why)
    try:
        ps = read_power_static(probes)
        if cfg.power_static_ref is not None:
            bad += ["power: " + w for w in power_static_problems(cfg.power_static_ref, ps)]
    except PowerStaticError as e:
        bad.append("power: " + str(e))
    if bad:
        raise PreflightError(bad)
    el = probes.is_elevated()
    print("elevated: " + {True: "true", False: "false", None: "unknown"}[el])
    print("note: this process is " + {True: "ELEVATED (administrator)", False: "not elevated", None: "of unknown elevation"}[el] + " (recorded in meta.json; not a refusal)")


def build_meta(cfg, probes=None, capture=True):
    """capture=False (rehearsal): PresentMon is neither hashed nor run; its meta fields are None."""
    probes = probes or SystemProbes()
    if capture:
        why = pm_hash_problem(cfg, probes)          # BEFORE any execution of PresentMon (the --version call below)
        if why:
            raise PreflightError([why])
        pm_sha = probes.sha256(cfg.presentmon_exe)
    meta = {"git_head": probes.git_head(cfg.repo_root), "llama_head": probes.git_head(cfg.llama_dir), "hags_hwschmode": probes.hags(),
            "driver_version": probes.driver_version(), "llm_exe_sha256": probes.sha256(cfg.llm_exe), "model_sha256": probes.sha256(cfg.model),
            "presentmon_version": probes.presentmon_version(cfg.presentmon_exe) if capture else None, "presentmon_sha256": pm_sha if capture else None,
            "presentmon_sha256_matches_prereg": (pm_sha == PRESENTMON_SHA256_PREREG) if capture else None, "seed": cfg.seed, "armoury_mode": cfg.armoury_mode,
            "game_process": cfg.game_process, "process_snapshot": probes.process_snapshot(), "warmup_s": cfg.warmup_s, "window_s": cfg.window_s,
            "n_prompt": cfg.n_prompt, "python": sys.version.split()[0], "allow_pm_hash_mismatch": bool(cfg.allow_pm_hash_mismatch), "elevated": probes.is_elevated(),
            "igpu_device_match": cfg.igpu_device_match, "cuda_device_match": cfg.cuda_device_match}
    if cfg.llm_exe_vk is not None:
        meta["llm_exe_vk_sha256"] = probes.sha256(cfg.llm_exe_vk)
    return meta


# ------------------------------------------------------------------ rest rule
PRIO_END_READBACK_BEFORE_CLOSE_S = 1.0                                              # PRIO_IDLE end read-back at t_close - 1 s: the driver stops and exits at t_close
REST_TOL_C = 3.0
REST_MIN_S = 30.0
REST_MAX_S = 300.0                                                                  # amendment 27 (was 180 s)
DEFAULT_NCTX = 12288                                                                # amendment 26 (was 16384)


def rest_until_cool(read_temp, start_temp, tol_c=REST_TOL_C, min_s=REST_MIN_S, max_s=REST_MAX_S, poll_s=1.0, clock=time.monotonic, sleep=time.sleep):
    """Prereg rest rule: wait until the GPU temperature is within tol_c (above) of the rep's starting temperature, for at least min_s and at most max_s seconds.
    Cooler than the start counts as within (one-sided reading of 'within 3 C'). -> dict(rest_s, reached, hit_max, start_temp, final_temp, min_s, max_s); the caller logs it."""
    t0 = clock()
    while True:
        elapsed = clock() - t0
        temp = read_temp()
        ok = temp - start_temp <= tol_c
        if elapsed >= max_s or (elapsed >= min_s and ok):
            return {"rest_s": elapsed, "reached": bool(ok), "hit_max": bool(elapsed >= max_s and not (ok and elapsed >= min_s)), "start_temp": start_temp,
                    "final_temp": temp, "tol_c": tol_c, "min_s": min_s, "max_s": max_s}
        sleep(min(poll_s, max_s - elapsed))


# ------------------------------------------------------------------ real dependencies (lazy)
class LlmProc:
    """The R1 driver process: line reader thread, 'READY' / 'DONE' waits, 'GO' on stdin."""

    def __init__(self, cmd, env, popen=subprocess.Popen):
        import queue
        self.p = popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1, env=env)
        self.lines, self._q = [], queue.Queue()
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self):
        for line in self.p.stdout:
            line = line.rstrip("\r\n")
            self.lines.append(line)
            self._q.put(line)
        self._q.put(None)

    @property
    def pid(self):
        return self.p.pid

    def wait_for(self, prefix, timeout):
        import queue
        end = time.monotonic() + timeout
        while True:
            try:
                line = self._q.get(timeout=max(0.0, end - time.monotonic()))
            except queue.Empty:
                raise TimeoutError(f"no {prefix!r} line from the LLM driver within {timeout} s; last lines: {self.lines[-5:]}") from None
            if line is None:
                try:
                    rc_txt = "rc=" + format_rc(self.p.wait(timeout=5))
                except subprocess.TimeoutExpired:
                    rc_txt = "process still running after 5 s (no return code)"
                raise RuntimeError(f"LLM driver exited ({rc_txt}) before {prefix!r}; output: {self.lines[-10:]}")
            if line.startswith(prefix):
                return line
            if line.startswith("FATAL"):
                raise RuntimeError(f"LLM driver: {line}")

    def send(self, text):
        self.p.stdin.write(text + "\n")
        self.p.stdin.flush()

    def poll(self):
        return self.p.poll()

    def kill(self):
        self.p.kill()


class NvmlReader:
    """Device 0 (the NVIDIA dGPU, as in the v1/v2 rig). UNVERIFIED on this build: the throttle-reason call name differs between nvidia-ml-py versions, both are tried."""

    def __init__(self):
        import pynvml
        pynvml.nvmlInit()
        self.nv, self.h = pynvml, pynvml.nvmlDeviceGetHandleByIndex(0)

    def energy_mj(self):
        return float(self.nv.nvmlDeviceGetTotalEnergyConsumption(self.h))

    def temp_c(self):
        return float(self.nv.nvmlDeviceGetTemperature(self.h, self.nv.NVML_TEMPERATURE_GPU))

    def vram_used_mb(self):
        return self.nv.nvmlDeviceGetMemoryInfo(self.h).used / 2**20

    def sm_clock(self):
        return int(self.nv.nvmlDeviceGetClockInfo(self.h, self.nv.NVML_CLOCK_SM))

    def power_w(self):
        """SAMPLED NVML power (information only, guarded by the sampler; never used in a metric)."""
        return float(self.nv.nvmlDeviceGetPowerUsage(self.h)) / 1000.0

    def power_limit_w(self):
        return nvml_power_limit_w(self.nv, self.h)

    def throttle(self):
        fn = getattr(self.nv, "nvmlDeviceGetCurrentClocksEventReasons", None) or self.nv.nvmlDeviceGetCurrentClocksThrottleReasons
        return int(fn(self.h))


class Sampler50(threading.Thread):
    """SM clock, throttle-reason bitmask, temperature and (amendment 20, information only) guarded sampled power every sampler_interval_s on the perf_counter clock (runs in every cell,
    SOLO included). Sampled power: a reading the guard rejects (above 1.5 x the NVML maximum power limit, 210 W here; negative) is stored as None and flagged in power_rejected; a failed
    read is stored as None and counted in power_errors. Cell power never comes from here: it comes from the energy counter only (two reads per window)."""

    def __init__(self, nvml, interval_s=0.05, guard=None):
        super().__init__(daemon=True)
        if guard is None:
            from telemetry.power_guard import PowerGuard
            guard = PowerGuard.default()
        self.nvml, self.interval_s, self.guard, self.stop_ev = nvml, interval_s, guard, threading.Event()
        self.t, self.sm, self.throttle, self.temp = [], [], [], []
        self.power, self.power_rejected, self.power_errors = [], [], 0
        self.limit = []                                                                   # enforced power limit (W), a covariate: None when unreadable

    def sample_once(self):
        t = time.perf_counter()
        self.t.append(t); self.sm.append(self.nvml.sm_clock()); self.throttle.append(self.nvml.throttle()); self.temp.append(self.nvml.temp_c())
        try:
            self.limit.append(float(self.nvml.power_limit_w()))
        except Exception:                                                                 # noqa: BLE001
            self.limit.append(None)
        try:
            w = self.nvml.power_w()
        except Exception:                                                                 # noqa: BLE001
            self.power_errors += 1
            self.power.append(None); self.power_rejected.append(False)
            return
        if self.guard.ok(w):
            self.power.append(w); self.power_rejected.append(False)
        else:
            self.power.append(None); self.power_rejected.append(True)

    def run(self):
        while not self.stop_ev.is_set():
            self.sample_once()
            self.stop_ev.wait(self.interval_s)

    def stop(self):
        self.stop_ev.set()
        if self.is_alive():
            self.join(2)


def read_shared_gpu_mem(pid):
    """Best effort: PDH '\\GPU Process Memory(pid_<pid>_*)\\Shared Usage' via typeperf, in bytes (the PDH counter's unit; UNVERIFIED here). Only instances that start with exactly
    'pid_<pid>_' are summed (pid_12_ never matches pid_123_...): the column headers are checked, not just the wildcard. Returns 'unavailable' on any failure (never guessed).
    Paging (analyze._flags) uses the END-of-window reading; the start reading is taken during the warm-up and is only recorded."""
    import csv as _csv
    import io
    try:
        r = subprocess.run([tool_paths()["typeperf"], rf"\GPU Process Memory(pid_{pid}_*)\Shared Usage", "-sc", "1"], capture_output=True, text=True, timeout=20)
        rows = [line for line in r.stdout.splitlines() if line.startswith('"')]
        if r.returncode != 0 or len(rows) < 2:
            return "unavailable"
        head, vals = next(_csv.reader(io.StringIO(rows[0]))), next(_csv.reader(io.StringIO(rows[1])))
        total, found = 0.0, False
        for h, v in zip(head[1:], vals[1:]):
            inst = h.split("(", 1)[1].split(")", 1)[0] if "(" in h else ""
            if inst.startswith(f"pid_{pid}_"):
                total, found = total + float(v), True
        return int(total) if found else "unavailable"
    except Exception:                                                                     # noqa: BLE001
        return "unavailable"


def query_qpc_hz():
    import ctypes
    f = ctypes.c_int64()
    if not ctypes.WinDLL("kernel32").QueryPerformanceFrequency(ctypes.byref(f)) or f.value <= 0:
        raise RuntimeError("QueryPerformanceFrequency failed")
    return float(f.value)


def query_qpc_counter():
    import ctypes
    v = ctypes.c_int64()
    if not ctypes.WinDLL("kernel32").QueryPerformanceCounter(ctypes.byref(v)):
        raise RuntimeError("QueryPerformanceCounter failed")
    return int(v.value)


@dataclass
class Deps:
    probes: object
    clock: object
    sleep: object
    spawn_llm: object          # (cmd, env, out_prefix) -> process-like: pid, lines, wait_for(prefix, timeout), send(text), poll(), kill()
    make_capture: object       # (cfg, out_csv, session) -> start(), stop(timeout)
    nvml: object               # energy_mj(), temp_c(), vram_used_mb()
    make_sampler: object       # (nvml) -> start(), stop(), t, sm, throttle, temp
    set_and_verify: object     # (pid, cls) -> dict, raises PriorityError
    get_priority: object       # (pid) -> int
    shared_mem: object         # (pid) -> bytes or 'unavailable'
    qpc_hz: float
    qpc_counter: object        # () -> raw QueryPerformanceCounter value; checked against clock() at cell start
    extra: dict = field(default_factory=dict)


def real_deps(cfg):
    nvml = NvmlReader()
    return Deps(probes=SystemProbes(), clock=time.perf_counter, sleep=time.sleep, spawn_llm=lambda cmd, env, out_prefix: LlmProc(cmd, env),
                make_capture=lambda c, out_csv, session: presentmon.Capture(c.presentmon_exe, c.game_process, str(out_csv), session),
                nvml=nvml, make_sampler=lambda nv: Sampler50(nv, cfg.sampler_interval_s), set_and_verify=gpu_priority.set_and_verify,
                get_priority=gpu_priority.get_priority, shared_mem=read_shared_gpu_mem, qpc_hz=query_qpc_hz(), qpc_counter=query_qpc_counter)


# ------------------------------------------------------------------ the cell
def _sleep_until(deps, t):
    """Sleep in steps of at most 0.25 s, then in 1 ms steps for the last 30 ms so that the caller wakes at t (energy reads at the window edges)."""
    while True:
        rem = t - deps.clock()
        if rem <= 0:
            return
        deps.sleep(min(rem - 0.02, 0.25) if rem > 0.03 else min(rem, 0.001))


def _sampler_stats(s, t_open, t_close):
    idx = [i for i, t in enumerate(s.t) if t_open <= t < t_close]
    if not idx:
        return {"sampler_n": 0, "sampled_power_n": 0, "sampled_power_mean_w": None, "power_rejected": 0, "sm_clock_mhz_median": None, "throttle_mask_or": None, "throttle_flag_mask_or": None, "throttle_swpowercap": None, "throttle_flag": None,
                "throttle_nonzero_frac": None, "sampler_temp_max": None, "enforced_limit_w_min": None, "enforced_limit_w_max": None}
    import statistics
    sm = [s.sm[i] for i in idx]
    th = [s.throttle[i] for i in idx]
    mask = 0
    for x in th:
        mask |= int(x)
    pw_all, rj_all = getattr(s, "power", None) or [], getattr(s, "power_rejected", None) or []
    pw = [pw_all[i] for i in idx if i < len(pw_all) and pw_all[i] is not None]
    rejected = sum(1 for i in idx if i < len(rj_all) and rj_all[i])
    lim_all = getattr(s, "limit", None) or []
    lim = [lim_all[i] for i in idx if i < len(lim_all) and lim_all[i] is not None]
    return {"enforced_limit_w_min": min(lim) if lim else None, "enforced_limit_w_max": max(lim) if lim else None,
            "sampler_n": len(idx), "sampled_power_n": len(pw), "sampled_power_mean_w": (sum(pw) / len(pw)) if pw else None, "power_rejected": rejected,
            "sm_clock_mhz_median": statistics.median(sm), "throttle_mask_or": mask, "throttle_flag_mask_or": mask & THROTTLE_FLAG_MASK,
            "throttle_swpowercap": bool(mask & THROTTLE_SWPOWERCAP), "throttle_flag": bool(mask & THROTTLE_FLAG_MASK),
            "throttle_nonzero_frac": sum(1 for x in th if x) / len(th), "sampler_temp_max": max(s.temp[i] for i in idx)}


def _parse_duty_achieved(lines):
    for line in lines:
        if line.startswith("DUTY_ACHIEVED"):
            return float(line.split()[1])
    return None


def _device_of(exec_line):
    return exec_line.split("device=", 1)[1].split(" offloaded=", 1)[0] if "device=" in exec_line else ""


def run_cell(arm, rep, out_dir, cfg, deps=None, warmup_s=None, window_s=None, smoke=False, capture=True, rehearsal=False):
    """Run one cell into out_dir and return the result dict (also written to result.json). Raises on any failure (no result.json is then written); deterministic refusals raise CellRefused.
    warmup_s / window_s (the --smoke mode) override cfg explicitly; the gap, frame-count and window rules scale with the window. smoke=True marks meta.json and result.json.
    rehearsal=True (run.py --rehearse; implies capture=False) marks meta/result 'rehearsal': the game process need not exist and PresentMon is neither started nor hash-checked; the capture,
    frame metrics, gap checks and the PDH game-memory read are skipped, everything else (LLM spawn, device checks, power-static check, priority, energy, sampler, tokens) runs."""
    if arm not in ARMS:
        raise ValueError(f"unknown arm {arm!r}; arms are {ARMS}")
    if warmup_s is not None or window_s is not None:
        cfg = dataclasses.replace(cfg, warmup_s=cfg.warmup_s if warmup_s is None else warmup_s, window_s=cfg.window_s if window_s is None else window_s)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    deps = deps or real_deps(cfg)
    skew = abs(deps.clock() - deps.qpc_counter() / deps.qpc_hz)
    if skew > QPC_TOLERANCE_S:
        raise RuntimeError(f"time.perf_counter() and QueryPerformanceCounter/Frequency disagree by {skew * 1000:.3f} ms (limit {QPC_TOLERANCE_S * 1000:.0f} ms): window times would not match PresentMon's QPC")
    capture = capture and not rehearsal
    uses_llm, uses_game = arm != "SOLO", arm != "LLM_ALONE" and capture
    backend, duty = ("vulkan" if arm == "IGPU" else "cuda"), (1 if arm == "DUTY50" else 0)
    events = []

    def log(msg):
        events.append(f"t={deps.clock():.6f} {msg}")

    llm = cap = sampler = None
    res = {"arm": arm, "rep": rep, "elevated": None}
    if smoke:
        res["smoke"] = True
    if rehearsal:
        res["rehearsal"] = True
    try:
        if arm == "IGPU" and cfg.llm_exe_vk is None:
            raise CellRefused("IGPU needs cfg.llm_exe_vk (the Vulkan build of the driver)")
        try:
            meta = build_meta(cfg, deps.probes, capture=capture)
        except PreflightError as e:
            raise CellRefused(str(e)) from e
        res["elevated"] = meta["elevated"]
        meta.update(arm=arm, rep=rep, backend=backend if uses_llm else None, duty=duty if uses_llm else None)
        if smoke:
            meta["smoke"] = True
        if rehearsal:
            meta["rehearsal"] = True
        (out_dir / "meta.json").write_text(json.dumps(meta, indent=1, default=str))
        game_pid = None
        if uses_game:
            game_pid = deps.probes.find_pid(cfg.game_process)
            if game_pid is None:
                raise CellRefused(f"game process {cfg.game_process} not running")
        elif arm == "LLM_ALONE":
            if deps.probes.find_pid(cfg.game_process) is not None:
                raise CellRefused(f"game process {cfg.game_process} is running: LLM_ALONE must be measured with the game absent")
            res["game_absent"] = True
        res["game_pid"] = game_pid
        clock_problems, clock_state = clock_state_check(deps.probes, cfg.game_process)
        meta["clock_state"] = clock_state
        (out_dir / "meta.json").write_text(json.dumps(meta, indent=1, default=str))
        if clock_problems:
            raise CellRefused("clock state refused: " + "; ".join(clock_problems))
        try:
            ps = read_power_static(deps.probes)
        except PowerStaticError as e:
            raise CellRefused("power refused: " + str(e)) from e
        res["power_static_cell_start"] = meta["power_static_cell_start"] = ps
        try:
            scheme0 = read_power_scheme(deps.probes)
        except PowerSchemeError as e:
            scheme0 = None
            if cfg.expect_power_scheme:
                raise CellRefused(f"power scheme refused: unreadable ({e}); --expect-power-scheme {cfg.expect_power_scheme!r}") from e
        res["power_scheme_guid"], res["power_scheme_name"] = scheme0 if scheme0 else (None, None)
        meta["power_scheme_guid"], meta["power_scheme_name"] = res["power_scheme_guid"], res["power_scheme_name"]
        (out_dir / "meta.json").write_text(json.dumps(meta, indent=1, default=str))
        if scheme0 and cfg.expect_power_scheme and not power_scheme_matches(cfg.expect_power_scheme, *scheme0):
            raise CellRefused(f"power scheme refused: active scheme is {scheme0[1]!r} ({scheme0[0]}), --expect-power-scheme is {cfg.expect_power_scheme!r}")
        (out_dir / "meta.json").write_text(json.dumps(meta, indent=1, default=str))
        if cfg.power_static_ref is not None:
            why = power_static_problems(cfg.power_static_ref, ps)
            if why:
                raise CellRefused("power refused: " + "; ".join(why))
        try:
            res["enforced_limit_w_start"] = float(deps.nvml.power_limit_w())             # covariate, before the LLM spawn; never a refusal
        except Exception:                                                                 # noqa: BLE001
            res["enforced_limit_w_start"] = None
        res["idle_vram_mib"] = meta["idle_vram_mib"] = deps.nvml.vram_used_mb()          # amendment 21: BEFORE the LLM process is launched
        if uses_llm:
            dll_bad = dll_dir_problems(cfg, deps.probes, backend)
            if dll_bad:
                raise CellRefused("; ".join(dll_bad))
            env = dict(os.environ, RG_BACKEND=backend, RG_DUTY=str(duty))
            dll_dir = str(llm_dll_dir(cfg, backend))
            env["PATH"] = dll_dir + os.pathsep + os.environ.get("PATH", "")
            res["llm_dll_dir"] = meta["llm_dll_dir"] = dll_dir
            (out_dir / "meta.json").write_text(json.dumps(meta, indent=1, default=str))
            env.setdefault("RG_NCTX", str(DEFAULT_NCTX))
            try:
                res["rg_nctx"] = meta["rg_nctx"] = int(env["RG_NCTX"])          # the n_ctx actually passed to the child
            except ValueError:
                res["rg_nctx"] = meta["rg_nctx"] = env["RG_NCTX"]
            (out_dir / "meta.json").write_text(json.dumps(meta, indent=1, default=str))
            env.pop("GGML_VK_VISIBLE_DEVICES", None)                  # never set (Vulkan device order is not stable) and never inherited
            env.pop("RG_DEVICE_MATCH", None)                          # never inherited: every LLM arm gets its own
            exe = cfg.llm_exe
            env["RG_DEVICE_MATCH"] = cfg.cuda_device_match
            if arm == "IGPU":
                exe = cfg.llm_exe_vk
                env["RG_DEVICE_MATCH"] = cfg.igpu_device_match
            meta["rg_device_match"] = res["rg_device_match"] = env["RG_DEVICE_MATCH"]
            (out_dir / "meta.json").write_text(json.dumps(meta, indent=1, default=str))
            prefix = str(out_dir / "llm")
            cmd = [str(exe), str(cfg.model), str(cfg.prompt), prefix, str(cfg.n_prompt)]
            log(f"spawn {cmd} RG_BACKEND={backend} RG_DUTY={duty} RG_NCTX={env['RG_NCTX']} RG_DEVICE_MATCH={env['RG_DEVICE_MATCH']}")
            llm = deps.spawn_llm(cmd, env, prefix)
            try:
                llm.wait_for("READY", cfg.ready_timeout_s)
            except RuntimeError as e:
                if "FATAL" in str(e) and "RG_DEVICE_MATCH" in str(e):
                    raise CellRefused(str(e)) from e                  # the driver found no device matching: deterministic
                raise
            log("LLM READY")
            exec_line = next((x for x in llm.lines if x.startswith("EXEC_MODE")), None)
            if exec_line is None or exec_line.split()[1:2] != [backend] or f"duty={duty}" not in exec_line.split():
                raise CellRefused(f"EXEC_MODE line does not confirm backend={backend} duty={duty}: {exec_line!r}")
            device = _device_of(exec_line)
            if arm == "IGPU":
                if "780M" not in device and "Radeon" not in device:
                    raise CellRefused(f"IGPU cell refused: the driver's EXEC_MODE device {device!r} does not contain '780M' or 'Radeon' (RG_DEVICE_MATCH={cfg.igpu_device_match!r}; check --igpu-device-match)")
            elif "RTX" not in device and "NVIDIA" not in device:
                raise CellRefused(f"{arm} cell refused: the driver's EXEC_MODE device {device!r} does not contain 'RTX' or 'NVIDIA' (RG_DEVICE_MATCH={cfg.cuda_device_match!r})")
            res["exec_mode"] = exec_line
        res["prio_readbacks"] = []
        if arm == "PRIO_IDLE":
            try:
                r = deps.set_and_verify(llm.pid, gpu_priority.CLASSES["IDLE"])
                res["prio_start"] = r
                res["prio_readbacks"].append(r["readback"])
            except gpu_priority.PriorityError as e:
                if e.set_status != 0 or e.readback is None:
                    raise CellRefused(f"PRIO_IDLE priority call failed (deterministic): {e}") from e          # a failing priority CALL is a refusal; a wrong class is not
                res["prio_start"] = {"set_status": e.set_status, "readback": e.readback, "ok": False, "error": str(e)}
                res["prio_readbacks"].append(e.readback)           # a mismatching read-back voids PRIO_IDLE, the cell still completes
            log(f"PRIO_IDLE start {res['prio_start']}")
        res["temp_c"] = {"start": deps.nvml.temp_c()}
        res["vram_mb"] = {"start": deps.nvml.vram_used_mb()}
        sampler = deps.make_sampler(deps.nvml)
        sampler.start()
        if uses_game:
            cap = deps.make_capture(cfg, out_dir / "frames.csv", f"R1_{arm}_{rep}_{secrets.token_hex(4)}")      # unique session per cell
            cap.start()
            deps.sleep(cfg.pm_settle_s)
        t_open = deps.clock() + cfg.warmup_s
        t_close = t_open + cfg.window_s
        res.update(t_open=t_open, t_close=t_close, qpc_hz=deps.qpc_hz, warmup_s=cfg.warmup_s, window_s=cfg.window_s)
        log(f"warm-up until {t_open}")
        if uses_llm:
            llm.send(f"GO {t_close!r}")                              # GO at the START of the warm-up: the LLM decodes from here, t_stop = window end
            log(f"GO {t_close!r}")
        shared0 = deps.shared_mem(game_pid) if uses_game else None    # PDH start reading: during the warm-up, never after t_open
        if deps.clock() >= t_open:
            raise RuntimeError("the PDH shared-memory read overran the warm-up (it must finish before t_open)")
        _sleep_until(deps, t_open)
        e0 = deps.nvml.energy_mj()                                    # first energy read immediately at t_open
        te0 = deps.clock()
        if arm == "PRIO_IDLE":
            # the driver stops decoding and exits at t_close, so read the class back while it is certainly alive (microseconds, the energy window is unaffected).
            # a PriorityError here is a CellRefused (the call failed: deterministic). Only a SUCCESSFUL read-back of the wrong class voids PRIO_IDLE.
            _sleep_until(deps, max(t_open, t_close - PRIO_END_READBACK_BEFORE_CLOSE_S))
            try:
                res["prio_readbacks"].append(deps.get_priority(llm.pid))
            except gpu_priority.PriorityError as e:
                raise CellRefused(f"PRIO_IDLE end read-back call failed (deterministic): {e}") from e
        _sleep_until(deps, t_close)
        e1 = deps.nvml.energy_mj()                                    # second read immediately at t_close: the energy window is [t_open, t_close)
        te1 = deps.clock()
        shared1 = deps.shared_mem(game_pid) if uses_game else None    # end-of-window reading: the one paging uses
        res["temp_c"]["end"] = deps.nvml.temp_c()
        res["vram_mb"]["end"] = deps.nvml.vram_used_mb()
        try:
            res["enforced_limit_w_end"] = float(deps.nvml.power_limit_w())
        except Exception:                                                                 # noqa: BLE001
            res["enforced_limit_w_end"] = None
        try:
            scheme1 = read_power_scheme(deps.probes)
        except PowerSchemeError:
            scheme1 = None
        res["power_scheme_guid_end"], res["power_scheme_name_end"] = scheme1 if scheme1 else (None, None)
        meta["power_scheme_guid_end"], meta["power_scheme_name_end"] = res["power_scheme_guid_end"], res["power_scheme_name_end"]
        (out_dir / "meta.json").write_text(json.dumps(meta, indent=1, default=str))
        if scheme1 != scheme0 and (scheme0 is not None or cfg.expect_power_scheme):
            raise RuntimeError(f"power scheme changed during the cell: {scheme0} at the start, {scheme1} at the end (a mode switch mid-cell): the cell fails")
        res["energy_j"] = (e1 - e0) / 1000.0
        res["energy_read_t"] = [te0, te1]
        res["power_w"] = res["energy_j"] / (te1 - te0)
        res["shared_gpu_mem_bytes"] = {"start": shared0, "end": shared1} if uses_game else None
        if arm == "PRIO_IDLE":
            res["prio_valid"] = all(x == gpu_priority.CLASSES["IDLE"] for x in res["prio_readbacks"])
            log(f"PRIO_IDLE read-backs {res['prio_readbacks']}")
        if uses_llm:
            res["driver_done"] = llm.wait_for("DONE", cfg.done_timeout_s)
            res["duty_achieved"] = None
            if arm == "DUTY50":
                res["duty_line"] = llm.wait_for("DUTY_ACHIEVED", cfg.done_timeout_s)
                res["duty_achieved"] = _parse_duty_achieved([res["duty_line"]])
        else:
            res["duty_achieved"] = None
        sampler.stop()
        res.update(_sampler_stats(sampler, t_open, t_close))
        sm_window = [v for t, v in zip(sampler.t, sampler.sm) if t_open <= t < t_close]
        const = clockcheck.constant_clock(sm_window)
        clock_state["loaded_constant_check"] = const
        meta["clock_state"] = clock_state
        (out_dir / "meta.json").write_text(json.dumps(meta, indent=1, default=str))
        if const["constant"]:
            raise RuntimeError(f"SM clock constant ({const['distinct']} distinct value over {const['n']} samples, at least {const['min_samples']}) for the whole window: the clock looks locked; "
                               "the cell fails and the rep reruns")
        res["temp_c"]["sampler_max"] = res.pop("sampler_temp_max")
        if cap is not None:
            cap.stop(timeout=cfg.capture_stop_timeout_s)
            frames = presentmon.parse_csv(out_dir / "frames.csv")
            cm = metrics.cell_frame_metrics(frames, t_open, t_close, deps.qpc_hz)
            presentmon.check_window_continuity(cm["frames"], t_open, t_close, deps.qpc_hz, min_fps=60.0)      # raises PresentMonGapError: the whole rep reruns
            res.update(frame=cm["frame"], gpu_busy_ms_median=cm["gpu_busy_ms_median"], n_dropped=cm["n_dropped"], swapchain=cm["swapchain"],
                       present_modes=sorted({f.present_mode for f in cm["frames"] if f.present_mode}))     # recorded only (hybrid display path, amendment 17); decides nothing
        else:
            res.update(frame=None, gpu_busy_ms_median=None, n_dropped=None, swapchain=None, present_modes=None)
        if uses_llm:
            tok = out_dir / "llm_tokens.csv"
            n_reset = metrics.count_resets(tok, t_open, t_close)
            if n_reset:
                raise RuntimeError(f"{n_reset} context reset row(s) of the token CSV fall inside the window: the cell fails (the rep reruns)")
            res["n_tokens"] = metrics.count_tokens(tok, t_open, t_close)
            res["tok_s"] = metrics.token_rate(tok, t_open, t_close)
        else:
            res["n_tokens"], res["tok_s"] = None, None
        res["flags"] = {"throttling": bool(res.get("throttle_flag"))}
        (out_dir / "result.json").write_text(json.dumps(res, indent=1, default=str))
        log("result.json written")
        return res
    except BaseException:
        log("FAILED\n" + traceback.format_exc())
        raise
    finally:
        if llm is not None:
            try:
                if llm.poll() is None:
                    llm.kill()
            except Exception as e:                                                        # noqa: BLE001
                events.append(f"kill failed: {e}")
        if cap is not None:
            try:
                cap.stop(timeout=cfg.capture_stop_timeout_s)
            except Exception as e:                                                        # noqa: BLE001
                events.append(f"capture stop failed: {e}")
        if sampler is not None:
            try:
                sampler.stop()
            except Exception as e:                                                        # noqa: BLE001
                events.append(f"sampler stop failed: {e}")
        (out_dir / "driver.log").write_text("\n".join(events + ["--- LLM driver output ---"] + (list(llm.lines) if llm is not None else [])) + "\n")
