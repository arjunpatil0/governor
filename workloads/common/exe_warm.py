"""Warm-up registry for freshly built executables. On this machine the first execution of a never-seen exe is intercepted by the endpoint antivirus (Avast is the active
product; Defender is stopped) and its side effects on NAMED objects (shared-memory rings) can happen twice (journal 0037, data/exe_first_run_probe.md). Run every new binary
once against throwaway names before any measurement; the registry (SHA-256 -> first warm-up time) lives outside the repo so it is per machine."""
import hashlib
import json
import subprocess
import time
from pathlib import Path


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def ensure_warm(exe, throwaway_args, registry_path, runner=subprocess.run, timeout_s=300):
    """True if a warm-up run was performed now, False if these exact bytes were warmed before."""
    reg_p = Path(registry_path)
    reg = json.loads(reg_p.read_text()) if reg_p.exists() else {}
    h = sha256(exe)
    if h in reg:
        return False
    runner([str(exe), *map(str, throwaway_args)], capture_output=True, text=True, timeout=timeout_s)
    reg[h] = dict(exe=str(exe), t_unix=time.time())
    reg_p.parent.mkdir(parents=True, exist_ok=True)
    reg_p.write_text(json.dumps(reg, indent=1))
    return True
