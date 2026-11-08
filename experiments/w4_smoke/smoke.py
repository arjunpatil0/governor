"""W4-5 hardware smoke (NOT a result; no hypothesis is tested): checks that the pieces work on the real GPU and NVML. Run step by step, unelevated, with the admin clock helper
already running in its own Administrator window. Writes data/w45_smoke/<run>/<step>.json.   python experiments/w4_smoke/smoke.py <step> [--run RUNDIR]
steps: warm | clock | daemon | frame | driver | governor | overrun (smoke 2) | gate (smoke 3) | shift (context shift check)
Always resets the clock lock in a finally block (helper RESET) and stops child processes."""
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

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "workloads" / "common"))
sys.path.insert(0, str(ROOT / "telemetry"))
from actuators.clock_client import ClockClient  # noqa: E402
from actuators.control import ControlActuator  # noqa: E402
from actuators.startup_reset import reset_clocks  # noqa: E402
from controllers.pi import PIController  # noqa: E402
from controllers.runtime import Governor  # noqa: E402
from sim.params import load_params  # noqa: E402
from sim.scenarios import build  # noqa: E402
from telemetry.daemon import Daemon  # noqa: E402
from telemetry.fg_publisher import FramePublisher  # noqa: E402
from telemetry.nvml_source import NvmlSource  # noqa: E402
from telemetry.obs_builder import ObsBuilder  # noqa: E402
from telemetry.power_guard import PowerGuard  # noqa: E402
from telemetry.ring import SeqBlock, SharedRing  # noqa: E402
from workloads.common.exe_warm import ensure_warm  # noqa: E402
from workloads.foreground.frame_loop import FmaFrameRunner, FrameLoop  # noqa: E402

EXE = ROOT / "workloads" / "background" / "llama_governed_bench.exe"
BIN = ROOT / "third_party" / "llama.cpp" / "build" / "bin"
MODEL = ROOT / "data" / "llama" / "Llama-3.2-3B-Instruct-Q4_K_M.gguf"
PROMPT = ROOT / "data" / "llama" / "prompt.txt"
REGISTRY = Path.home() / "AppData" / "Local" / "governor" / "warmed_exes.json"
PERIOD = 1000.0 / 60.0
TRIM_S = 2.0           # frames scheduled in the first TRIM_S seconds are excluded from the driver metrics (driver/fg start-up transient)


class SafeClient(ClockClient):
    """ClockClient whose requests are serialised, so a heartbeat thread can share it with the main thread."""
    def __init__(self):
        super().__init__()
        self.lk = threading.Lock()

    def _ask(self, line):
        with self.lk:
            return super()._ask(line)


class Heartbeat(threading.Thread):
    """Keeps the helper watchdog (3 s) and idle timeout (10 s) quiet during long steps, as the governor loop does every 100 ms."""
    def __init__(self, cl):
        super().__init__(daemon=True)
        self.cl, self.ev = cl, threading.Event()

    def run(self):
        while not self.ev.wait(0.5):
            try:
                self.cl.heartbeat()
            except Exception:                                    # noqa: BLE001
                pass

    def stop(self):
        self.ev.set(); self.join(2)


def nm(tag):
    return "Local\\gov_smoke_" + tag + "_" + uuid.uuid4().hex[:8]


def run_dir(arg):
    d = Path(arg) if arg else ROOT / "data" / "w45_smoke" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    d.mkdir(parents=True, exist_ok=True)
    return d


def save(d, step, obj):
    (d / f"{step}.json").write_text(json.dumps(obj, indent=1, default=str), encoding="utf-8")
    print(json.dumps(obj, indent=1, default=str)[:6000])


class NvmlSampler(threading.Thread):
    """~200 Hz SM clock / power sampler (QPC timestamps). v2 guard (docs/AUDIT_590W.md): a power reading that is negative or above 1.5x the card's maximum power limit (the 588 to 590 W NVML glitch)
    is replaced by the last accepted reading (the sample is skipped if there is none yet), counted in guard.rejected, and the raw value and its time are kept in rej_w / rej_t. nv, h and guard can be injected (tests)."""
    def __init__(self, nv=None, h=None, guard=None):
        super().__init__(daemon=True)
        if nv is None:
            import pynvml as nv
            nv.nvmlInit(); h = nv.nvmlDeviceGetHandleByIndex(0)
        self.nv, self.h = nv, h
        self.guard = guard if guard is not None else PowerGuard.from_nvml(nv, h)
        self.t, self.sm, self.pw, self.rej_t, self.rej_w = [], [], [], [], []
        self.stop_ev = threading.Event()

    def sample_once(self):
        nv, h = self.nv, self.h
        t, sm, raw = time.perf_counter(), nv.nvmlDeviceGetClockInfo(h, nv.NVML_CLOCK_SM), nv.nvmlDeviceGetPowerUsage(h) / 1000.0
        p, ok = self.guard.filter(raw)
        if not ok:
            self.rej_t.append(t); self.rej_w.append(raw)
        if p is None:
            return
        self.t.append(t); self.sm.append(sm); self.pw.append(p)

    def run(self):
        while not self.stop_ev.is_set():
            self.sample_once()
            time.sleep(0.004)

    def stop(self):
        self.stop_ev.set(); self.join(2)


class Load:
    """Background FMA slices through the W2 DLL so that the SM clock is meaningful (clocks idle low on an idle GPU)."""
    def __init__(self, w, seconds, units=8000):
        self.th = threading.Thread(target=lambda: w.bg_until(1, [units], w.now() + seconds), daemon=True)

    def __enter__(self):
        self.th.start(); time.sleep(1.0); return self

    def __exit__(self, *a):
        self.th.join(60)


def settle_time(t, sm, t_cmd, lo, hi, hold=0.25):
    """Seconds from t_cmd until the SM clock stays inside [lo, hi] for `hold` seconds; None if never."""
    t, sm = np.asarray(t), np.asarray(sm)
    inside = (sm >= lo) & (sm <= hi)
    for i in np.where(t >= t_cmd)[0]:
        j = np.searchsorted(t, t[i] + hold)
        if j <= len(t) and inside[i:j].all() and t[min(j, len(t)) - 1] >= t[i] + hold - 0.02:
            return float(t[i] - t_cmd)
    return None


def step_warm(d):
    r = ensure_warm(EXE, ["m", "p", "o", "-1", "1", "512", nm("none1"), nm("none2"), nm("none3"), "8"], REGISTRY)
    save(d, "warm", dict(exe=str(EXE), warmed_now=r, registry=str(REGISTRY)))


def step_clock(d):
    from workloads.common.w2lib import W2
    w = W2()
    cl = ClockClient()
    smp = NvmlSampler(); smp.start()
    out = dict(steps=[])
    try:
        reset_clocks(cl, is_admin=False)
        with Load(w, 40):
            time.sleep(1.0)
            out["baseline_sm_mhz_median"] = float(np.median(smp.sm[-100:]))
            for target in (900, 1500, 1800):
                t_cmd = time.perf_counter(); ok = cl.lock(target); t_ack = time.perf_counter()
                time.sleep(1.2)
                out["steps"].append(dict(op=f"LOCK {target}", ok=ok, response=cl.last_response, ack_ms=(t_ack - t_cmd) * 1000, settle_s=settle_time(smp.t, smp.sm, t_cmd, target - 20, target + 20)))
            ok = cl.lock(1499); out["steps"].append(dict(op="LOCK 1499 (not allowed)", ok=ok, response=cl.last_response))
            t_cmd = time.perf_counter(); ok = cl.reset(); base = out["baseline_sm_mhz_median"]
            time.sleep(1.5)
            out["steps"].append(dict(op="RESET", ok=ok, response=cl.last_response, settle_s=settle_time(smp.t, smp.sm, t_cmd, base * 0.9, 4000)))
            time.sleep(1.1)
            cl.lock(1200); t_last = time.perf_counter(); time.sleep(0.5)          # watchdog: lock, then go silent
            t_dead = None
            for _ in range(80):
                time.sleep(0.1)
                if smp.sm[-1] > 1500:
                    t_dead = time.perf_counter(); break
            out["steps"].append(dict(op="watchdog (silent after LOCK 1200)", seconds_until_unlocked=None if t_dead is None else t_dead - t_last))
            time.sleep(1.1)
            cl.lock(1200); time.sleep(0.5); cl.close(); t_close = time.perf_counter(); t_un = None          # disconnect: lock, then drop the connection
            for _ in range(60):
                time.sleep(0.1)
                if smp.sm[-1] > 1500:
                    t_un = time.perf_counter(); break
            out["steps"].append(dict(op="disconnect after LOCK 1200", seconds_until_unlocked=None if t_un is None else t_un - t_close))
            cl = ClockClient(); out["final_ping"] = cl.ping()
    finally:
        try:
            cl = cl if cl.h is not None else ClockClient()
            cl.reset(); cl.close()
        except Exception as e:                                  # noqa: BLE001
            print("RESET FAILED", e)
        smp.stop()
    save(d, "clock", out)


def step_daemon(d):
    from workloads.common.w2lib import W2
    import pynvml as nv
    w = W2(); nv.nvmlInit(); h = nv.nvmlDeviceGetHandleByIndex(0)
    dm = Daemon({"nvml": NvmlSource(nv, h)}, period_s=0.05, path=d / "daemon.csv", header={"execution_mode": "real NVML, GPU load = W2 FMA slices"})
    with Load(w, 14):
        st = dm.run(duration_s=10.0)
    import pandas as pd
    df = pd.read_csv(d / "daemon.csv", comment="#")
    rep = dict(stats=st, rows=len(df), median_dt_ms=float(np.median(np.diff(df.t_qpc_s)) * 1000),
               changed_fraction={c: float(df[c].mean()) for c in df.columns if c.endswith("_changed")},
               age_ms_p90={c: float(df[c].quantile(0.9)) for c in df.columns if c.endswith("_age_ms")},
               sm_mhz_median=float(df.nvml_sm_mhz.median()), power_w_median=float(df.nvml_power_w.median()))
    save(d, "daemon", rep)


def calibrate(w, cl):
    cl.lock(1800); time.sleep(1.2)
    return FmaFrameRunner.calibrate(w)


def step_frame(d):
    from workloads.common.w2lib import W2
    w = W2(); cl = SafeClient(); hb = Heartbeat(cl); hb.start(); out = {}
    P = load_params(ROOT)
    try:
        reset_clocks(cl, is_admin=False)
        cal = calibrate(w, cl); out["calibration"] = cal
        runner = FmaFrameRunner(w, cal)
        for clk in (1800, 1500, 1200):
            if clk != 1800:
                cl.reset(); time.sleep(1.1); cl.lock(clk); time.sleep(1.2)
            ring, pace = SharedRing(nm("fr"), 4096, 3, True), SeqBlock(nm("pc"), 3, True)
            loop = FrameLoop(build("S0").fg, runner, FramePublisher(ring, pace))
            recs = loop.run(duration_s=8.0)
            lat = np.array([r["lat_ms"] for r in recs])
            out[f"clock_{clk}"] = dict(frames=len(recs), lat_p50_ms=float(np.percentile(lat, 50)), lat_p99_ms=float(np.percentile(lat, 99)), miss_frac=float((lat > PERIOD).mean()),
                                       sim_expected_p50_ms=7.0 * P.fg_ratio(clk), abandoned=loop.abandoned)
    finally:
        hb.stop(); cl.reset(); cl.close()
    save(d, "frame", out)


def run_driver(w, cal, d, label, ctrl_vals, seconds=30, with_fg=True, cost_ms=None):
    """One governed-driver run against the synthetic fg (with_fg=False: background alone): returns metrics; raw frames/tokens are kept in out['_raw'] for step_overrun."""
    frames, tokens = SharedRing(nm("fr"), 8192, 3, True), SharedRing(nm("tk"), 65536, 2, True)
    ctrl, pace = SeqBlock(nm("ct"), 3, True), SeqBlock(nm("pc"), 3, True)
    ctrl.write(ctrl_vals)
    out_csv = d / f"driver_{label}.csv"
    env = dict(os.environ, PATH=str(BIN) + ";" + os.environ["PATH"])
    pr = subprocess.Popen([str(EXE), str(MODEL), str(PROMPT), str(out_csv), "-1", str(seconds + 8), "512", ctrl.name, pace.name, tokens.name, "65536"],
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=env)
    exec_line, loop, recs, tk, dropped, e0, e1 = None, None, [], np.empty((0, 1)), 0, 0, 0
    try:
        t0 = time.time()
        while time.time() - t0 < 120:                           # model load: the first token appears in the ring
            if tokens.write_count > 0:
                break
            if pr.poll() is not None:
                raise RuntimeError("driver exited early: " + pr.stdout.read())
            time.sleep(0.2)
        tokens.read_new()
        smp = NvmlSampler(); smp.start()
        e0 = smp.nv.nvmlDeviceGetTotalEnergyConsumption(smp.h)
        if with_fg:
            fg = build("S0").fg
            if cost_ms is not None:                              # constant frame cost (ms alone at 1800 MHz) instead of the scenario's
                import dataclasses
                fg = dataclasses.replace(fg, cost_ms=lambda t, c=float(cost_ms): c)
            loop = FrameLoop(fg, FmaFrameRunner(w, cal), FramePublisher(frames, pace))
            recs = loop.run(duration_s=seconds)
        else:
            loop = type("NoFg", (), {"t0": time.perf_counter()})()
            time.sleep(seconds)
        e1 = smp.nv.nvmlDeviceGetTotalEnergyConsumption(smp.h); smp.stop()
        tk, dropped = tokens.read_new()
    finally:
        ctrl.write([0.0, 0.0, 0.5])                             # duty 0 pauses the driver
        try:
            pr.wait(timeout=45)
        except subprocess.TimeoutExpired:
            pr.kill()
        out_txt = pr.stdout.read() if pr.stdout else ""
        for line in out_txt.splitlines():
            if line.startswith("EXEC_MODE"):
                exec_line = line
    keep = [r for r in recs if r["t_sched"] >= loop.t0 + TRIM_S]
    lat = np.array([r["lat_ms"] for r in keep]) if keep else np.array([float("nan")])
    tk_t = tk[:, 0] if len(tk) else np.array([])
    win = tk_t[tk_t >= loop.t0 + TRIM_S]
    ph = ((win - loop.t0) % (PERIOD / 1000.0)) * 1000.0
    dur = seconds - TRIM_S
    return dict(label=label, ctrl=ctrl_vals, exec_mode=exec_line, frames=len(keep), fg_p50_ms=float(np.percentile(lat, 50)), fg_p99_ms=float(np.percentile(lat, 99)), fg_miss_frac=float((lat > PERIOD).mean()),
                _raw=dict(arrivals=[r["t_sched"] for r in keep], tok_end=tk_t[tk_t >= loop.t0 + TRIM_S].tolist(), tok_ms=(tk[tk_t >= loop.t0 + TRIM_S, 1].tolist() if len(tk) else [])),
                bg_tok_s=len(win) / dur, mean_power_w_whole_run=(e1 - e0) / 1000.0 / seconds, token_end_phase_ms_p10_p50_p90=[float(x) for x in np.percentile(ph, [10, 50, 90])] if len(ph) else None,
                ring_dropped=dropped, driver_output_tail=out_txt.splitlines()[-3:])


def step_driver(d):
    from workloads.common.w2lib import W2
    w = W2(); cl = SafeClient(); hb = Heartbeat(cl); hb.start(); out = []
    try:
        reset_clocks(cl, is_admin=False)
        cal = calibrate(w, cl)
        cl.reset(); time.sleep(1.1)
        for label, vals in (("aligned_g0_d1", [1.0, 1.0, 0.0]), ("aligned_g0_d0.5", [1.0, 0.5, 0.0]), ("unaligned_d1", [0.0, 1.0, 0.5])):
            out.append(run_driver(w, cal, d, label, vals)); out[-1].pop("_raw", None)
            print(json.dumps(out[-1], default=str)[:1500], flush=True)
            time.sleep(3)
    finally:
        hb.stop(); cl.reset(); cl.close()
    save(d, "driver", out)


def step_governor(d):
    from workloads.common.w2lib import W2
    w = W2(); cl = SafeClient(); hb = Heartbeat(cl); hb.start(); params = load_params(ROOT)
    frames, tokens = SharedRing(nm("fr"), 8192, 3, True), SharedRing(nm("tk"), 65536, 2, True)
    ctrl, pace = SeqBlock(nm("ct"), 3, True), SeqBlock(nm("pc"), 3, True)
    log, pr, smp = [], None, None
    try:
        reset_clocks(cl, is_admin=False)
        cal = calibrate(w, cl); cl.reset(); time.sleep(1.1)
        tuned = json.loads((ROOT / "data" / "sim_tuned.json").read_text())["params"]["c'"]
        ctl = PIController(params, "aligned", power_budget_w=60.0, **tuned)
        gov = Governor(ctl, ObsBuilder(PERIOD, PERIOD), ControlActuator(ctrl, cl, params.UNLOCKED_MHZ), SharedRing(frames.name, 8192, 3, False), SharedRing(tokens.name, 65536, 2, False),
                       PERIOD, PERIOD, params=params)
        env = dict(os.environ, PATH=str(BIN) + ";" + os.environ["PATH"])
        gov.start(0.0, startup_reset=lambda: reset_clocks(cl, is_admin=False))
        pr = subprocess.Popen([str(EXE), str(MODEL), str(PROMPT), str(d / "governor_driver.csv"), "-1", "52", "512", ctrl.name, pace.name, tokens.name, "65536"],
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=env)
        t0 = time.time()
        while tokens.write_count == 0 and time.time() - t0 < 120:
            time.sleep(0.2)
        smp = NvmlSampler(); smp.start()
        stop = threading.Event()

        def loop_gov():
            tick = time.perf_counter()
            while not stop.is_set():
                tick += 0.1
                time.sleep(max(0.0, tick - time.perf_counter()))
                e = smp.nv.nvmlDeviceGetTotalEnergyConsumption(smp.h) / 1000.0
                a = gov.step(time.perf_counter() * 1000.0, e, smp.sm[-1])
                log.append(dict(t=time.perf_counter(), clock_cmd=a.clock, duty=a.duty, guard=a.guard_ms, miss=gov.last_obs.n_missed, n=len(gov.last_obs.lat_ms), power_w=gov.last_obs.power_w, sm=smp.sm[-1]))
        th = threading.Thread(target=loop_gov, daemon=True); th.start()
        loop = FrameLoop(build("S0").fg, FmaFrameRunner(w, cal), FramePublisher(frames, pace))
        recs = loop.run(duration_s=30.0)
        stop.set(); th.join(5); smp.stop()
        keep = [r for r in recs if r["t_sched"] >= loop.t0 + TRIM_S]
        lat = np.array([r["lat_ms"] for r in keep])
        out = dict(frames=len(keep), fg_p50_ms=float(np.percentile(lat, 50)), fg_p99_ms=float(np.percentile(lat, 99)), fg_miss_frac=float((lat > PERIOD).mean()),
                   clock_commands=sorted(set(x["clock_cmd"] for x in log)), clock_changes=int(sum(1 for a, b in zip(log, log[1:]) if a["clock_cmd"] != b["clock_cmd"])),
                   duty_range=[min(x["duty"] for x in log), max(x["duty"] for x in log)], mean_power_w_last10s=float(np.mean([x["power_w"] for x in log[-100:]])),
                   sm_mhz_seen=sorted(set(int(x["sm"]) for x in log))[:12], ticks=len(log), tail=log[-3:])
    finally:
        try:
            ctrl.write([0.0, 0.0, 0.5])
            if pr is not None:
                pr.wait(timeout=45)
        except Exception:                                       # noqa: BLE001
            try:
                pr.kill()
            except Exception:                                   # noqa: BLE001
                pass
        hb.stop(); cl.reset(); cl.close()
    save(d, "governor", out)


OVERRUN_RUNS = (("bg_alone_unaligned_d1", [0.0, 1.0, 0.5], False), ("aligned_g0_d1", [1.0, 1.0, 0.0], True), ("aligned_g0.5_d1", [1.0, 1.0, 0.5], True), ("aligned_g1_d1", [1.0, 1.0, 1.0], True),
                ("aligned_g2_d1", [1.0, 1.0, 2.0], True), ("aligned_g0_d0.5", [1.0, 0.5, 0.0], True), ("unaligned_d1", [0.0, 1.0, 0.5], True))


def step_overrun(d):
    """Smoke 2 (not a result): token durations and overrun past the next frame arrival for guard 0 / 0.5 / 1 / 2 ms and for the background alone (does contention stretch tokens?).
    Raw frame arrivals and token rings go to overrun_raw_<label>.json; the summary to overrun.json."""
    from analysis.smoke_overrun import overrun_stats
    from workloads.common.w2lib import W2
    w = W2(); cl = SafeClient(); hb = Heartbeat(cl); hb.start(); out = []
    try:
        reset_clocks(cl, is_admin=False)
        cal = calibrate(w, cl)
        cl.reset(); time.sleep(1.1)
        for label, vals, with_fg in OVERRUN_RUNS:
            r = run_driver(w, cal, d, label, vals, seconds=25, with_fg=with_fg)
            raw = r.pop("_raw")
            (d / f"overrun_raw_{label}.json").write_text(json.dumps(raw), encoding="utf-8")
            r["overrun"] = overrun_stats(raw["arrivals"], raw["tok_end"], raw["tok_ms"], PERIOD) if with_fg else dict(tok_ms_summary=overrun_stats([0.0], raw["tok_end"], raw["tok_ms"], PERIOD))
            out.append(r)
            print(json.dumps(r, default=str)[:900], flush=True)
            time.sleep(3)
    finally:
        hb.stop(); cl.reset(); cl.close()
    save(d, "overrun", out)


GATE_RUNS = (("aligned_g0_d1_cost4", [1.0, 1.0, 0.0], 4.0), ("aligned_g1_d1_cost4", [1.0, 1.0, 1.0], 4.0), ("aligned_g0_d1_cost7", [1.0, 1.0, 0.0], 7.0),
             ("aligned_g1_d1_cost7", [1.0, 1.0, 1.0], 7.0), ("aligned_g1_d1_cost9", [1.0, 1.0, 1.0], 9.0), ("unaligned_d1_cost9", [0.0, 1.0, 0.5], 9.0))


def step_gate(d):
    """Smoke 3 (not a result): after the pace-view fix (journal 0041) the fit test really gates. Constant frame costs 4 / 7 / 9 ms (slack 12.7 / 9.7 / 7.6 ms against a 10 ms token):
    aligned guard 0 and 1 ms, plus an unaligned reference at 9 ms. Raw rings to overrun_raw_<label>.json, summary to overrun.json (same layout as step overrun, analysis/smoke2_report.py <dir>)."""
    from analysis.smoke_overrun import overrun_stats
    from workloads.common.w2lib import W2
    w = W2(); cl = SafeClient(); hb = Heartbeat(cl); hb.start(); out = []
    try:
        reset_clocks(cl, is_admin=False)
        cal = calibrate(w, cl)
        cl.reset(); time.sleep(1.1)
        for label, vals, cost in GATE_RUNS:
            r = run_driver(w, cal, d, label, vals, seconds=25, cost_ms=cost)
            raw = r.pop("_raw")
            (d / f"overrun_raw_{label}.json").write_text(json.dumps(raw), encoding="utf-8")
            r["cost_ms"], r["overrun"] = cost, overrun_stats(raw["arrivals"], raw["tok_end"], raw["tok_ms"], PERIOD)
            out.append(r)
            print(json.dumps(r, default=str)[:900], flush=True)
            time.sleep(3)
    finally:
        hb.stop(); cl.reset(); cl.close()
    save(d, "overrun", out)


def step_shift(d):
    """Context-shift check (journal 0044, not a result): the background alone for 40 s must run past the old 1534-token limit; the shifted tokens are flagged in the driver CSV."""
    import pandas as pd
    from workloads.common.w2lib import W2
    w = W2(); cl = SafeClient(); hb = Heartbeat(cl); hb.start()
    try:
        reset_clocks(cl, is_admin=False)
        cl.reset(); time.sleep(1.1)
        r = run_driver(w, None, d, "shift_bg_alone", [0.0, 1.0, 0.5], seconds=40, with_fg=False)
        r.pop("_raw", None)
    finally:
        hb.stop(); cl.reset(); cl.close()
    lg = pd.read_csv(d / "driver_shift_bg_alone.csv")
    done = next(x for x in r["driver_output_tail"] if x.startswith("DONE"))
    out = dict(run=r, tokens=int(len(lg)), shifted_tokens=int(lg.shifted.sum()), tok_ms_p50=float(lg.tok_ms.median()), tok_ms_p99=float(lg.tok_ms.quantile(0.99)), tok_ms_max=float(lg.tok_ms.max()),
               tok_ms_shifted_median=float(lg[lg.shifted == 1].tok_ms.median()) if lg.shifted.sum() else None, done_line=done)
    save(d, "shift", out)


STEPS = dict(warm=step_warm, clock=step_clock, daemon=step_daemon, frame=step_frame, driver=step_driver, governor=step_governor, overrun=step_overrun, gate=step_gate, shift=step_shift)

BATTERY_CHARGE_MODE = "Balanced 80%"        # Armoury Crate Battery Health Charging, fixed for the whole study from 2026-10-23 (not detectable by software: a recorded declaration)


def write_meta(d, armoury_mode, battery_charge_mode=BATTERY_CHARGE_MODE):
    """meta.json for every smoke/run directory: Armoury Crate mode (NOT_RECORDED is flagged), battery charge mode, boot time / uptime, Chrome state, process list with CPU%, git head, exe hash, helper state."""
    import procsnap
    procs = procsnap.snapshot(interval=1.0)
    git = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    try:
        helper = ClockClient().ping()
    except Exception as e:                                   # noqa: BLE001
        helper = f"unreachable: {type(e).__name__}"
    from workloads.common.exe_warm import sha256
    import psutil
    boot = psutil.boot_time()
    meta = dict(utc=datetime.now(timezone.utc).isoformat(), boot_utc=datetime.fromtimestamp(boot, timezone.utc).isoformat(), uptime_s=round(time.time() - boot), battery_charge_mode=battery_charge_mode,
                armoury_mode=armoury_mode or "NOT_RECORDED", armoury_mode_recorded=bool(armoury_mode), chrome_running=procsnap.chrome_running(procs),
                git_head=git, exe_sha256=sha256(EXE) if EXE.exists() else None, helper_ping=helper, processes=procs[:25])
    (d / "meta.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
    if not meta["armoury_mode_recorded"] or meta["chrome_running"]:
        print("WARNING: " + ("Armoury Crate mode NOT recorded; " if not meta["armoury_mode_recorded"] else "") + ("Chrome is running; " if meta["chrome_running"] else "") + "(smoke only; a full run would refuse)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("step", choices=list(STEPS))
    ap.add_argument("--run", default=None)
    ap.add_argument("--armoury-mode", default=None, help="Armoury Crate mode now active; recorded in meta.json (NOT_RECORDED is flagged)")
    a = ap.parse_args()
    d = run_dir(a.run)
    print("run dir", d)
    if not (d / "meta.json").exists():
        write_meta(d, a.armoury_mode)
    STEPS[a.step](d)
