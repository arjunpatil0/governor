"""Diagnostic for the smoke incident (journal 0038/0039): NVML nvmlDeviceResetGpuLockedClocks raised NVMLError_Unknown twice in the helper log (18:07:35 on a client disconnect and 18:31:57 at
shutdown), each time after an earlier successful reset and with no lock in between, while other back-to-back resets (18:07:47, 18:10:36/37) succeeded. Hypotheses: (H1) resetting an
already-unlocked clock errors; (H2) the reset errors when the GPU has been idle (low power state) for a while. This script separates them. RUN ELEVATED (Administrator PowerShell), helper STOPPED:
   python experiments/w4_smoke/reset_probe.py
Writes data/w45_smoke/reset_probe.json and always leaves the clock reset (nvidia-smi -rgc as a last step)."""
import json
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "workloads" / "common"))
import pynvml as nv  # noqa: E402

nv.nvmlInit()
H = nv.nvmlDeviceGetHandleByIndex(0)
OUT = []


def attempt(label, fn):
    t = time.time()
    try:
        fn(); r = "ok"
    except Exception as e:                                  # noqa: BLE001
        r = f"{type(e).__name__}: {e}"
    sm = nv.nvmlDeviceGetClockInfo(H, nv.NVML_CLOCK_SM)
    OUT.append(dict(case=label, result=r, sm_mhz_after=sm, util_gpu=nv.nvmlDeviceGetUtilizationRates(H).gpu, seconds=round(time.time() - t, 4)))
    print(OUT[-1], flush=True)


reset = lambda: nv.nvmlDeviceResetGpuLockedClocks(H)          # noqa: E731
lock = lambda mhz: nv.nvmlDeviceSetGpuLockedClocks(H, mhz, mhz)       # noqa: E731


def main():
    from w2lib import W2
    w = W2()

    def load(seconds):
        threading.Thread(target=lambda: w.bg_until(1, [8000], w.now() + seconds), daemon=True).start()
        time.sleep(1.5)

    subprocess.run(["nvidia-smi", "-rgc"], capture_output=True)
    load(12)                                                  # BUSY GPU
    for i in range(3):
        attempt(f"busy: reset #{i + 1} with no lock held", reset); time.sleep(1.0)
    attempt("busy: lock 1500", lambda: lock(1500)); time.sleep(1.0)
    attempt("busy: reset after lock", reset); time.sleep(1.0)
    attempt("busy: reset again (already unlocked)", reset)
    time.sleep(12)                                            # load ends, GPU goes idle
    for idle_s in (2, 10, 30):                                # IDLE GPU, no lock held
        time.sleep(idle_s)
        attempt(f"idle {idle_s} s more: reset with no lock held", reset)
    attempt("idle: lock 1500", lambda: lock(1500)); time.sleep(10)
    attempt("idle: reset 10 s after lock", reset)
    time.sleep(30)
    attempt("idle 30 s: reset (already unlocked)", reset)
    subprocess.run(["nvidia-smi", "-rgc"], capture_output=True)
    d = ROOT / "data" / "w45_smoke"; d.mkdir(parents=True, exist_ok=True)
    (d / "reset_probe.json").write_text(json.dumps(dict(utc=datetime.now(timezone.utc).isoformat(), cases=OUT), indent=1), encoding="utf-8")
    print("written", d / "reset_probe.json")


if __name__ == "__main__":
    main()
