"""v2 sprint 1 measurement driver (docs/V2_SPRINT1_PAUSE_COST.md): runs workloads/background/llama_pause_bench.exe (built against the PATCHED llama.cpp, third_party/llama.cpp_v2) for the 3B at a fixed
SM clock lock, once per (configuration, rep), and stores the raw per-token and per-group CSVs under data/v2/s1_pause/<stamp>/.
   python tools/pause_bench.py --smoke                  30 s check, unlocked, nothing stored but a printed line: sampled power with the v2 guard, power_rejected must be 0 under load
   python tools/pause_bench.py --run [--clock 1500]     the sweep: G = 1, 2, 4, 7, 14, 28 and graphs off, 3 reps x 300 tokens, 20 warm-up tokens discarded in the analysis
The sweep needs the admin clock helper running in an Administrator window (actuators/clock_helper.py) and nothing else on the GPU (close Chrome and tray apps). The clock is always reset in a finally block.
Configurations are interleaved in rounds (rep 1 of every configuration, then rep 2, ...) so that slow drift does not align with one configuration."""
import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "experiments" / "w4_smoke"))
EXE = ROOT / "workloads" / "background" / "llama_pause_bench.exe"
BIN = ROOT / "third_party" / "llama.cpp_v2" / "build" / "bin"
MODEL = ROOT / "data" / "llama" / "Llama-3.2-3B-Instruct-Q4_K_M.gguf"
PROMPT = ROOT / "data" / "llama" / "prompt.txt"
CONFIGS = [("G1", {"GGML_CUDA_PAUSE_GROUPS": "1"}), ("G2", {"GGML_CUDA_PAUSE_GROUPS": "2"}), ("G4", {"GGML_CUDA_PAUSE_GROUPS": "4"}), ("G7", {"GGML_CUDA_PAUSE_GROUPS": "7"}),
           ("G14", {"GGML_CUDA_PAUSE_GROUPS": "14"}), ("G28", {"GGML_CUDA_PAUSE_GROUPS": "28"}), ("graphs_off", {"GGML_CUDA_DISABLE_GRAPHS": "1"}),
           # control: a forced 2 ms busy-wait at every boundary; the token time must rise by about 2 ms x (G - 1), otherwise the boundaries are not real pause points
           ("G4_pause2ms", {"GGML_CUDA_PAUSE_GROUPS": "4", "PAUSE_FORCE_US": "2000"}), ("G7_pause2ms", {"GGML_CUDA_PAUSE_GROUPS": "7", "PAUSE_FORCE_US": "2000"})]


def run_exe(env_extra, prefix, n_tokens, n_warm, n_prompt=512, timeout=300):
    env = dict(os.environ, PATH=str(BIN) + ";" + os.environ["PATH"])
    for k in ("GGML_CUDA_PAUSE_GROUPS", "GGML_CUDA_DISABLE_GRAPHS", "PAUSE_FORCE_US"):
        env.pop(k, None)
    env.update(env_extra)
    r = subprocess.run([str(EXE), str(MODEL), str(PROMPT), str(prefix), str(n_prompt), str(n_tokens), str(n_warm)], capture_output=True, text=True, timeout=timeout, env=env)
    if r.returncode != 0:
        raise RuntimeError(f"llama_pause_bench failed ({r.returncode}): {r.stdout[-400:]} {r.stderr[-400:]}")
    return r.stdout


def smoke():
    import smoke as S
    smp = S.NvmlSampler()
    smp.start()
    t0 = time.perf_counter()
    out = ""
    for i in range(2):                                   # two runs of 1400 tokens (about 15 s each): 512 prompt + 1400 stays inside the 2048 context
        out = run_exe({"GGML_CUDA_PAUSE_GROUPS": "1"}, ROOT / "data" / "v2" / f"_smoke_{i}", 1400, 20)
    wall = time.perf_counter() - t0
    smp.stop()
    pw = smp.pw
    print(f"smoke: {wall:.1f} s, {len(pw)} sampled power readings, mean {sum(pw) / len(pw):.1f} W, max {max(pw):.1f} W, power_rejected = {smp.guard.rejected} (limit {smp.guard.limit_w:.0f} W, source {smp.guard.source})")
    print(out.strip().splitlines()[0] if out else "")
    for i in range(2):
        for suffix in ("_tokens.csv", "_groups.csv"):
            p = ROOT / "data" / "v2" / f"_smoke_{i}{suffix}"
            if p.exists():
                p.unlink()
    return 0


def sweep(clock, reps, n_tokens, n_warm):
    import smoke as S
    from actuators.startup_reset import reset_clocks
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = ROOT / "data" / "v2" / "s1_pause" / stamp
    out.mkdir(parents=True, exist_ok=True)
    cl = S.SafeClient()                                  # raises if the admin helper is not running: no silent unlocked run
    hb = S.Heartbeat(cl)
    hb.start()
    meta = dict(stamp=stamp, clock_mhz=clock, reps=reps, n_tokens=n_tokens, n_warm=n_warm, model=str(MODEL), exe=str(EXE), configs=[c for c, _ in CONFIGS], exec_lines={})
    try:
        reset_clocks(cl, is_admin=False)
        cl.reset()
        time.sleep(1.1)
        if not cl.lock(clock):
            raise RuntimeError("the helper refused the clock lock")
        time.sleep(1.5)
        for rep in range(1, reps + 1):
            for name, env in CONFIGS:
                prefix = out / f"{name}_rep{rep}"
                print(f"[{name} rep {rep}] ...", flush=True)
                line = run_exe(env, prefix, n_tokens, n_warm)
                meta["exec_lines"][f"{name}_rep{rep}"] = [l for l in line.splitlines() if l.startswith(("EXEC_MODE", "DONE"))]
                time.sleep(3)
    finally:
        hb.stop()
        cl.reset()
        cl.close()
        (out / "meta.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
    print("saved in", out)
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--clock", type=int, default=1500)
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--tokens", type=int, default=300)
    ap.add_argument("--warm", type=int, default=20)
    a = ap.parse_args()
    if not EXE.exists():
        sys.exit(f"missing {EXE}: build it with workloads/background/build_llama_v2.bat and build_llama_pause.bat")
    if a.smoke:
        return smoke()
    if a.run:
        return sweep(a.clock, a.reps, a.tokens, a.warm)
    ap.error("give --smoke or --run")


if __name__ == "__main__":
    sys.exit(main())
