"""Load pre-check (yaml: held_out_workload; reviewer 2026-10-23): does each model load with ALL layers on the GPU at context 2048 (the governed driver aborts otherwise) and run a few seconds of decode?
PASS/FAIL ONLY (EXEC_MODE offloaded=N/N, a clean exit, tokens produced); the decode rate printed here is a plumbing number and is NEVER used to choose the held-out workload.
Needs no clock lock and no helper. Writes data/w5a/load_precheck.json and the model registry data/llama/models.json (path + sha256 of every model).   python experiments/w5a/load_precheck.py"""
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "experiments" / "w4_smoke")); sys.path.insert(0, str(ROOT / "workloads" / "common"))
import smoke  # noqa: E402
from telemetry.ring import SeqBlock, SharedRing  # noqa: E402
from workloads.common.exe_warm import ensure_warm, sha256  # noqa: E402

MODELS = {
    "llama32_1b": ("Llama-3.2-1B-Instruct-Q4_K_M.gguf", "known"),
    "llama32_3b": ("Llama-3.2-3B-Instruct-Q4_K_M.gguf", "known"),
    "phi35_mini": ("Phi-3.5-mini-instruct-Q4_K_M.gguf", "known (proposed other family)"),
    "llama31_8b": ("Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf", "HELD OUT"),
}


def vram_used_mib():
    out = subprocess.run(["nvidia-smi", "--query-gpu=memory.used,memory.total", "--format=csv,noheader,nounits"], capture_output=True, text=True).stdout.split(",")
    return int(out[0]), int(out[1])


def check(name, path):
    ctrl, pace, ring = SeqBlock(smoke.nm("ct"), 3, True), SeqBlock(smoke.nm("pc"), 3, True), SharedRing(smoke.nm("tk"), 65536, 2, True)
    ctrl.write([0.0, 1.0, 0.5])
    csv = ROOT / "data" / "w5a" / f"load_precheck_{name}.csv"
    csv.parent.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, PATH=str(smoke.BIN) + ";" + os.environ["PATH"])
    base = vram_used_mib()[0]
    t0 = time.time()
    pr = subprocess.Popen([str(smoke.EXE), str(path), str(smoke.PROMPT), str(csv), "-1", "14", "512", ctrl.name, pace.name, ring.name, "65536"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=env)
    peak = base
    while pr.poll() is None and time.time() - t0 < 120:
        peak = max(peak, vram_used_mib()[0]); time.sleep(0.5)
    if pr.poll() is None:
        pr.kill()
    out = pr.stdout.read()
    m = re.search(r"EXEC_MODE cuda offloaded=(\d+)/(\d+) n_layer=(\d+)", out)
    d = re.search(r"DONE tokens=(\d+) t_first=([\d.]+) t_last=([\d.]+)", out)
    tokens = int(d.group(1)) if d else 0
    passed = bool(m and m.group(1) == m.group(2) and pr.returncode == 0 and tokens > 0)
    return dict(workload=name, role=MODELS[name][1], passed=passed, offloaded=f"{m.group(1)}/{m.group(2)}" if m else None, n_layer=int(m.group(3)) if m else None, returncode=pr.returncode,
                tokens=tokens, vram_peak_minus_base_mib=peak - base, vram_total_mib=vram_used_mib()[1], output_tail=out.strip().splitlines()[-4:], seconds=round(time.time() - t0, 1))


def main():
    ensure_warm(smoke.EXE, ["m", "p", "o", "-1", "1", "512", smoke.nm("none1"), smoke.nm("none2"), smoke.nm("none3"), "8"], smoke.REGISTRY)
    reg, res = {}, []
    for name, (fn, role) in MODELS.items():
        p = ROOT / "data" / "llama" / fn
        reg[name] = dict(path=str(p), sha256=sha256(p), bytes=p.stat().st_size, role=role)
        res.append(check(name, p))
        print(json.dumps(res[-1]), flush=True)
        time.sleep(3)
    (ROOT / "data" / "llama" / "models.json").write_text(json.dumps(reg, indent=1), encoding="utf-8")
    (ROOT / "data" / "w5a" / "load_precheck.json").write_text(json.dumps(dict(utc=datetime.now(timezone.utc).isoformat(), exe_sha256=sha256(smoke.EXE), context=2048, results=res), indent=1), encoding="utf-8")
    print("written data/llama/models.json and data/w5a/load_precheck.json")


if __name__ == "__main__":
    main()
