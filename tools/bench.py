"""v2 bench: one command runs a named setup N times (default 3 x 60 s) and prints a small table: late frames %, frame p99, tok/s, mean power, VRAM per process.
   python tools/bench.py yolo-alone yolo-3b-free yolo-3b-paced --video <clip.mp4>          (several setups in one go: one table row each)
   python tools/bench.py yolo-alone --check --video <clip.mp4>                              (prerequisites only, nothing is launched)
Setups: yolo-alone | yolo-3b-free | yolo-3b-paced | yolo-8b-free | yolo-8b-paced.
  free   = the v1 governed llama driver, unaligned, duty 1 (back-to-back tokens, hints ignored): "uncontrolled".
  paced  = the same driver in v1 aligned slack-filling mode, duty 1, guard --guard-ms: tokens start only where they fit before the next frame is due (v1 gap-filling).
One run: the YOLO child loads and warms up (READY), the llama driver loads and decodes, both are resident, then GO: the YOLO loop starts at a common QPC time t0 and runs --duration seconds. All
metrics use the window [t0 + trim, t0 + duration] (trim = 2 s, the v1 convention). late % and p99 come from the YOLO frame records (p99 of schedule-to-completion latency, ms); tok/s = tokens whose end
falls in the window / window length (driver token ring); power = mean of NVML SAMPLED power (nvmlDeviceGetPowerUsage, 20 Hz, readings above 1.5x the max power limit (210 W here) dropped as the known glitch and counted; never the
energy counter); VRAM = peak per-process MiB in the window (telemetry/vram.py). A setup whose models leave less than --min-free-mib free before GO is skipped ("does not fit"); a run whose peak system
VRAM comes within --min-free-mib of the total is marked with * (WDDM may page). Table cells are means over the runs; per-run values are in bench.json (and with --per-run).
Output: data/v2/bench/<UTC stamp>/ (bench.json, table.txt, one folder per run with frames.npz, result.json, logs). Clocks, power limit and the Armoury Crate mode are NOT touched; give --armoury-mode to record it."""
import argparse
import json
import os
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "python"))

EXE = ROOT / "workloads" / "background" / "llama_governed_bench.exe"
BIN = ROOT / "third_party" / "llama.cpp" / "build" / "bin"
PROMPT = ROOT / "data" / "llama" / "prompt.txt"
MODELS = {"3b": ROOT / "data" / "llama" / "Llama-3.2-3B-Instruct-Q4_K_M.gguf", "8b": ROOT / "data" / "llama" / "Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf"}
REGISTRY = Path.home() / "AppData" / "Local" / "governor" / "warmed_exes.json"
SETUPS = {"yolo-alone": (None, None), "yolo-3b-free": ("3b", "free"), "yolo-3b-paced": ("3b", "paced"), "yolo-8b-free": ("8b", "free"), "yolo-8b-paced": ("8b", "paced")}
TRIM_S = 2.0
POWER_PLAUSIBLE_MAX_W = 250.0                                           # default of power_mean; run_once passes the guard limit (1.5x max power limit)
RING_CAPACITY = 65536
INSTALL_HINT = "pip install --use-feature=truststore ultralytics   (a dry run adds httpx, polars, ultralytics, ultralytics-thop, ultralytics-platform and changes no numpy/scipy/torch)"


class DoesNotFit(RuntimeError):
    pass


# ---------------------------------------------------------------- pure functions (tests/test_bench.py)
def ctrl_values(mode, guard_ms):
    """Control block of the v1 governed driver: [pacing (0 unaligned duty-cycle, 1 aligned slack filling), duty, guard_ms]."""
    return {"free": [0.0, 1.0, float(guard_ms)], "paced": [1.0, 1.0, float(guard_ms)]}[mode]


def tokens_per_s(token_end_times, t_lo, t_hi):
    """Tokens whose end time falls in [t_lo, t_hi], per second of window."""
    return sum(1 for t in token_end_times if t_lo <= t <= t_hi) / (t_hi - t_lo)


def power_mean(samples, t_lo, t_hi, max_w=POWER_PLAUSIBLE_MAX_W):
    """Mean of sampled power (t, W) in the window; readings outside 0..max_w are the NVML glitch (a few samples read 590 W) and are dropped and counted. -> (mean W or None, n used, n dropped)."""
    win = [w for t, w in samples if t_lo <= t <= t_hi]
    ok = [w for w in win if 0.0 <= w <= max_w]
    return (sum(ok) / len(ok) if ok else None), len(ok), len(win) - len(ok)


def mean(vals):
    vals = [v for v in vals if v is not None]
    return sum(vals) / len(vals) if vals else None


def aggregate(runs):
    """Per-setup means over the runs of the table fields; None where no run has the value."""
    return dict(runs=len(runs), late_pct=mean(r["late_pct"] for r in runs), lat_p99_ms=mean(r["lat_p99_ms"] for r in runs), tok_s=mean(r["tok_s"] for r in runs),
                power_w=mean(r["power_w"] for r in runs), vram_yolo_mib=mean(r["vram_mib"]["yolo"] for r in runs), vram_llama_mib=mean(r["vram_mib"]["llama"] for r in runs),
                near_full=any(r["near_full"] for r in runs))


def _f(v, nd=1):
    return "n/a" if v is None else f"{v:.{nd}f}"


def format_table(rows, per_run=False):
    """rows: list of (setup name, aggregate dict or a skip-reason string, runs list). A small fixed-width table."""
    head = ["setup", "runs", "late %", "p99 ms", "tok/s", "power W", "VRAM yolo MiB", "VRAM llama MiB"]
    body = []
    for name, agg, runs in rows:
        if isinstance(agg, str):
            body.append([name, "-", agg] + [""] * (len(head) - 3))
            continue
        star = "*" if agg["near_full"] else ""
        body.append([name, str(agg["runs"]), _f(agg["late_pct"], 2), _f(agg["lat_p99_ms"]), _f(agg["tok_s"]), _f(agg["power_w"]), _f(agg["vram_yolo_mib"], 0), _f(agg["vram_llama_mib"], 0) + star])
        if per_run:
            for i, r in enumerate(runs):
                body.append([f"  run {i + 1}", "", _f(r["late_pct"], 2), _f(r["lat_p99_ms"]), _f(r["tok_s"]), _f(r["power_w"]), _f(r["vram_mib"]["yolo"], 0), _f(r["vram_mib"]["llama"], 0)])
    widths = [max(len(c) for c in col) for col in zip(head, *body)]

    def line(cells):
        return "  ".join(c.ljust(w) if i == 0 else c.rjust(w) for i, (c, w) in enumerate(zip(cells, widths))).rstrip()
    return "\n".join([line(head), line(["-" * w for w in widths])] + [line(b) for b in body])


# ---------------------------------------------------------------- hardware side
class PowerSampler(threading.Thread):
    """NVML sampled power at ~20 Hz as (QPC s, W). Never the energy counter."""

    def __init__(self, period_s=0.05):
        super().__init__(daemon=True)
        import pynvml as nv
        from telemetry.power_guard import PowerGuard
        nv.nvmlInit()
        self.nv, self.h, self.period_s, self.samples, self.ev = nv, nv.nvmlDeviceGetHandleByIndex(0), period_s, [], threading.Event()
        self.guard = PowerGuard.from_nvml(nv, self.h)                        # the same guard as the experiment sampler: window means drop readings above 1.5x the max power limit

    def run(self):
        while not self.ev.is_set():
            self.samples.append((time.perf_counter(), self.nv.nvmlDeviceGetPowerUsage(self.h) / 1000.0))
            self.ev.wait(self.period_s)

    def stop(self):
        self.ev.set()
        self.join(2)


def preflight(a):
    """Fail loudly before anything is launched. Returns a dict of what was found."""
    import importlib.util
    problems, info = [], {}
    if importlib.util.find_spec("ultralytics") is None:
        problems.append("ultralytics is not installed: " + INSTALL_HINT)
    for p in (EXE, PROMPT):
        if not Path(p).exists():
            problems.append(f"missing {p}")
    if not Path(a.video).is_file():
        problems.append(f"video not found: {a.video}")
    for s in a.setups:
        llama = SETUPS[s][0]
        if llama and not MODELS[llama].is_file():
            problems.append(f"missing model {MODELS[llama]}")
    try:
        import pynvml
        pynvml.nvmlInit()
        m = pynvml.nvmlDeviceGetMemoryInfo(pynvml.nvmlDeviceGetHandleByIndex(0))
        info["vram_total_mib"], info["vram_used_mib"] = m.total / 2**20, m.used / 2**20
    except Exception as e:                                                   # noqa: BLE001
        problems.append(f"NVML not usable: {e}")
    if problems:
        raise SystemExit("bench preflight failed:\n  " + "\n  ".join(problems))
    return info


def git_info():
    from telemetry.provenance import git_state
    try:
        head, dirty = git_state(ROOT)
        return dict(head=head, dirty=bool(dirty))
    except Exception as e:                                                   # noqa: BLE001
        return dict(head=None, dirty=None, error=str(e))


def wait_for(pred, proc, what, timeout_s, log):
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        if pred():
            return
        if proc.poll() is not None:
            raise RuntimeError(f"{what}: process exited early (code {proc.returncode}); log {log}:\n" + Path(log).read_text(errors="replace")[-1500:])
        time.sleep(0.1)
    raise RuntimeError(f"{what}: timed out after {timeout_s} s; log {log}")


def run_once(setup, a, run_dir):
    """One run of a setup -> dict of metrics. Always stops the child processes and the samplers."""
    from telemetry.ring import SeqBlock, SharedRing
    from telemetry.vram import VramPoller
    import slackhint
    llama, mode = SETUPS[setup]
    run_dir.mkdir(parents=True, exist_ok=True)
    tag = uuid.uuid4().hex[:8]
    names = {k: f"Local\\gov_bench_{k}_{tag}" for k in ("ctrl", "pace", "tok")}
    ctrl = pace = tokens = None
    yolo = drv = power = None
    vram = VramPoller(period_s=a.vram_period)
    ylog, dlog = run_dir / "yolo.log", run_dir / "driver.log"
    try:
        if llama:
            ctrl, pace, tokens = SeqBlock(names["ctrl"], 3, True), slackhint.Producer(names["pace"], create=True), SharedRing(names["tok"], RING_CAPACITY, 2, True)
            ctrl.write(ctrl_values(mode, a.guard_ms))
        ycmd = [sys.executable, "-m", "workloads.foreground.yolo_loop", "--video", str(a.video), "--weights", a.weights, "--imgsz", str(a.imgsz), "--fps", str(a.fps),
                "--duration", str(a.duration), "--out", str(run_dir), "--trim-s", str(TRIM_S), "--handshake"] + (["--pace-name", names["pace"]] if llama else [])
        yolo = subprocess.Popen(ycmd, cwd=ROOT, stdin=subprocess.PIPE, stdout=open(ylog, "w"), stderr=subprocess.STDOUT, text=True)
        wait_for(lambda: "READY" in ylog.read_text(errors="replace"), yolo, "yolo_loop warm-up", 300, ylog)
        if llama:
            env = dict(os.environ, PATH=str(BIN) + ";" + os.environ["PATH"])
            drv = subprocess.Popen([str(EXE), str(MODELS[llama]), str(PROMPT), str(run_dir / "driver.csv"), "-1", str(a.duration + 25), "512", names["ctrl"], names["pace"], names["tok"], str(RING_CAPACITY)],
                                   stdout=open(dlog, "w"), stderr=subprocess.STDOUT, text=True, env=env)
            wait_for(lambda: tokens.write_count > 0, drv, "llama driver load", 180, dlog)
            tokens.read_new()
        time.sleep(1.5)
        s = vram.poll_once() or {}
        if s and s["total_mib"] - s["used_mib"] < a.min_free_mib:
            raise DoesNotFit(f"{setup}: {s['used_mib']:.0f} of {s['total_mib']:.0f} MiB in use with both loaded, less than --min-free-mib {a.min_free_mib:.0f} free")
        power = PowerSampler()
        power.start()
        t0 = time.perf_counter() + 0.5
        yolo.stdin.write(f"GO {t0!r}\n")
        yolo.stdin.flush()
        t_lo, t_hi = t0 + TRIM_S, t0 + a.duration
        yolo.wait(timeout=a.duration + 90)
        if yolo.returncode != 0:
            raise RuntimeError(f"yolo_loop failed (code {yolo.returncode}); log {ylog}:\n" + ylog.read_text(errors="replace")[-1500:])
        if drv is not None and drv.poll() is not None:
            raise RuntimeError(f"llama driver exited during the window (code {drv.returncode}); log {dlog}")
        power.stop()
        res = json.loads((run_dir / "result.json").read_text())
        pw, n_ok, n_bad = power_mean(power.samples, t_lo, t_hi, max_w=power.guard.limit_w)
        tok_s, dropped = None, None
        if llama:
            tk, dropped = tokens.read_new()
            tok_s = tokens_per_s(tk[:, 0].tolist() if len(tk) else [], t_lo, t_hi)
        pids = {"yolo": yolo.pid, **({"llama": drv.pid} if drv else {})}
        vs = vram.summary(list(pids.values()), t_lo, t_hi)
        vm = {k: (vs[pids[k]]["peak_mib"] if k in pids else None) for k in ("yolo", "llama")}
        sysv = vs["system"]
        near_full = sysv["peak_mib"] is not None and sysv["total_mib"] - sysv["peak_mib"] < a.min_free_mib
        sm = res["summary"]
        return dict(setup=setup, late_pct=sm["late_pct"], late=sm["late"], frames=sm["frames"], lat_p50_ms=sm["lat_p50_ms"], lat_p99_ms=sm["lat_p99_ms"], gpu_p50_ms=sm["gpu_p50_ms"], abandoned=res["abandoned"],
                    tok_s=tok_s, ring_dropped=None if dropped is None else int(dropped), power_w=pw, power_samples=n_ok, power_glitches=n_bad, vram_mib=vm, vram_system_peak_mib=sysv["peak_mib"],
                    vram_total_mib=sysv["total_mib"], near_full=near_full, pids=pids, vram_errors=vram.errors, yolo_result=res)
    finally:
        if ctrl is not None:
            ctrl.write([0.0, 0.0, 0.5])                                     # duty 0 pauses the driver
        for p in (yolo, drv):
            if p is not None and p.poll() is None:
                try:
                    p.wait(timeout=30 if p is drv else 5)
                except subprocess.TimeoutExpired:
                    p.kill()
        if power is not None and power.is_alive():
            power.stop()
        vram.stop()


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0], formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    ap.add_argument("setups", nargs="*", help="one or more of: " + ", ".join(SETUPS))
    ap.add_argument("--video", default=str(ROOT / "data" / "foreground" / "video.mp4"), help="the fixed video file every run uses (looped)")
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--duration", type=float, default=60.0)
    ap.add_argument("--fps", type=float, default=30.0)
    ap.add_argument("--weights", default="yolov8n.pt")
    ap.add_argument("--imgsz", type=int, default=640)
    ap.add_argument("--guard-ms", type=float, default=0.5, help="guard of the paced (aligned) setups; 0.5 ms is the v1 starting value")
    ap.add_argument("--gap-s", type=float, default=8.0, help="pause between runs")
    ap.add_argument("--min-free-mib", type=float, default=300.0)
    ap.add_argument("--vram-period", type=float, default=0.5)
    ap.add_argument("--armoury-mode", default=None, help="Armoury Crate mode, recorded in bench.json")
    ap.add_argument("--out", default=None)
    ap.add_argument("--per-run", action="store_true", help="also print every run")
    ap.add_argument("--check", action="store_true", help="prerequisites only; launch nothing")
    a = ap.parse_args(argv)
    unknown = [s for s in a.setups if s not in SETUPS]
    if unknown or not a.setups:
        ap.error("give at least one known setup (" + ", ".join(SETUPS) + ")" + (f"; unknown: {unknown}" if unknown else ""))
    info = preflight(a)
    if a.check:
        print("bench preflight OK", json.dumps(info))
        return 0
    from workloads.common.exe_warm import ensure_warm
    ensure_warm(EXE, ["m", "p", "o", "-1", "1", "512", "Local\\gov_bench_none1", "Local\\gov_bench_none2", "Local\\gov_bench_none3", "8"], REGISTRY)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = Path(a.out) if a.out else ROOT / "data" / "v2" / "bench" / stamp
    out.mkdir(parents=True, exist_ok=True)
    meta = dict(stamp=stamp, args=vars(a), git=git_info(), preflight=info, exe=str(EXE), trim_s=TRIM_S)
    rows, results = [], {}
    for s in a.setups:
        runs = []
        try:
            for i in range(a.runs):
                print(f"[{s}] run {i + 1}/{a.runs} ({a.duration:.0f} s) ...", flush=True)
                r = run_once(s, a, out / s / f"run{i + 1}")
                runs.append(r)
                print(f"    late {_f(r['late_pct'], 2)}%  p99 {_f(r['lat_p99_ms'])} ms  tok/s {_f(r['tok_s'])}  power {_f(r['power_w'])} W  power glitches dropped {r['power_glitches']}", flush=True)
                if i + 1 < a.runs:
                    time.sleep(a.gap_s)
        except DoesNotFit as e:
            print(f"[{s}] skipped: {e}", flush=True)
            rows.append((s, "does not fit in VRAM", []))
            results[s] = dict(skipped=str(e))
            continue
        rows.append((s, aggregate(runs), runs))
        results[s] = dict(aggregate=aggregate(runs), runs=runs)
        time.sleep(a.gap_s)
    table = format_table(rows, per_run=a.per_run)
    note = "late %: frames finished after the next frame was due; p99: schedule-to-completion ms; power: sampled NVML (readings above 1.5x the max power limit dropped); VRAM: peak per process; * = VRAM nearly full (WDDM may page)"
    (out / "table.txt").write_text(table + "\n" + note + "\n", encoding="utf-8")
    (out / "bench.json").write_text(json.dumps(dict(meta=meta, results=results), indent=1, default=str), encoding="utf-8")
    print("\n" + table + "\n" + note + f"\nsaved in {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
