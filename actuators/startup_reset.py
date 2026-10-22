"""Governor start-up clock reset. Covers a hard-killed helper (NVML has no server-side lock expiry): ask the helper to RESET and, when this process is elevated, also run
`nvidia-smi -rgc` and `nvidia-smi -rmc` (fixed argv, no shell). It is an error if NO channel could have reset the clock (not elevated and no helper) or every attempted channel failed."""
import ctypes
import subprocess

SMI_TIMEOUT_S = 15


def _is_admin():
    return bool(ctypes.windll.shell32.IsUserAnAdmin())


def reset_clocks(clock_client=None, runner=subprocess.run, is_admin=None, timeout_s=SMI_TIMEOUT_S):
    admin = _is_admin() if is_admin is None else is_admin
    rep = {}
    if clock_client is not None:
        try:
            rep["helper"] = bool(clock_client.reset())
        except Exception as e:                                 # noqa: BLE001  report, then rely on the other channel
            rep["helper"] = f"error: {type(e).__name__}"
    else:
        rep["helper"] = "skipped: no helper"
    for key, flag in (("rgc", "-rgc"), ("rmc", "-rmc")):
        if not admin:
            rep[key] = "skipped: not elevated"
            continue
        try:
            rep[key] = runner(["nvidia-smi", flag], capture_output=True, text=True, timeout=timeout_s).returncode == 0
        except Exception as e:                                 # noqa: BLE001
            rep[key] = f"error: {type(e).__name__}"
    if not any(v is True for v in rep.values()):
        raise RuntimeError(f"no channel reset the GPU clock locks: {rep}")
    return rep
