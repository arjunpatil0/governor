"""Cell executors of the W5b tuning sitting (experiments/w5b/tune.py; tests/test_w5b_executors.py).
SimExecutor: runs a cell spec in the (frozen) simulator - a DRY RUN of the sitting logic, never data; its cells say executor 'sim'.
HwExecutor: runs a cell spec on the real GPU with the governed driver, the synthetic FMA foreground, the admin clock helper and (for c'B / d'B) the Governor loop at 10 Hz - the same pieces
smoke.py and experiments/w5a/run.py use. NOT yet run on hardware when this file was written (journal 0050); the first hardware run is the supervised trial.
build_controller(P, spec) is shared: ('static', Action) for static settings and arm a, ('ctl', controller) for c'B (SwitchingPIController: both pacing modes, non-learned switch at 6.57 +- 0.3 ms, constants from the spec) and d'B (HybridController,
safety = 1 - margin, switch_gain 2.0 and clock_every 20 from data/sim_tuned.json d')."""
import dataclasses
import json
import os
import subprocess
import sys
import threading
import time
import zlib
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "experiments" / "w5a")); sys.path.insert(0, str(ROOT / "experiments" / "w4_smoke"))
sys.path.insert(0, str(ROOT / "workloads" / "common")); sys.path.insert(0, str(ROOT / "telemetry"))
from controllers.hybrid import HybridController  # noqa: E402
from controllers.pi import SwitchingPIController  # noqa: E402
from sim.params import load_params  # noqa: E402
from sim.plant import Action, BgSpec, Plant, summarise  # noqa: E402
from sim.scenarios import C0_MS, build  # noqa: E402

WARM_S, MEASURE_S = 5.0, 60.0
BG_ALONE_MEASURE_S, FG_ALONE_S = 30.0, 15.0
TEMP_ABORT_C, TEMP_COOL_C, COOL_MIN_S = 85, 55, 20.0
PERIOD = 1000.0 / 60.0
MODELS = ROOT / "data" / "llama" / "models.json"
SEED = 20261024


class AbortSitting(SystemExit):
    """A yaml abort rule fired (lock not released, temperature, thermal/power-brake event reasons): the sitting stops, finished cells are kept."""


def window_mean(t, v, t_a, t_b):
    """Mean of the samples v taken at times t inside [t_a, t_b); nan if there are none (the second, independent power measure next to the energy counter)."""
    t, v = np.asarray(t, float), np.asarray(v, float)
    m = (t >= t_a) & (t < t_b)
    return float(np.mean(v[m])) if m.any() else float("nan")


def recent_mean(t, v, now, span):
    """Mean of the samples v taken in (now - span, now]; nan if none (the sampled power source of the Governor loop; the sampler appends from another thread, so only a copy of the tail is read)."""
    tt, vv = list(t[-200:]), list(v[-200:])
    n = min(len(tt), len(vv))
    sel = [vv[i] for i in range(n) if now - span < tt[i] <= now]
    return float(np.mean(sel)) if sel else float("nan")


def mode_code(mode):
    """Pacing mode of the governed-cell log: 1 aligned, 0 unaligned, -1 not applicable (a controller without a mode)."""
    return {"aligned": 1.0, "unaligned": 0.0}.get(mode, -1.0)


def trace_bins(t, v, t_a, t_b, step_s=0.5):
    """The sampled power as a compact time series for the cell record: mean of v in consecutive bins of step_s from t_a to t_b; returns (bin centres in seconds from t_a, means; nan in an empty bin)."""
    t, v = np.asarray(t, float), np.asarray(v, float)
    n = int(round((t_b - t_a) / step_s))
    edges = t_a + step_s * np.arange(n + 1)
    centres = step_s * (np.arange(n) + 0.5)
    means = np.array([float(np.mean(v[(t >= edges[i]) & (t < edges[i + 1])])) if ((t >= edges[i]) & (t < edges[i + 1])).any() else float("nan") for i in range(n)])
    return centres, means


def fg_spec(scene, c0, origin_ms=0.0):
    """Foreground of a scene at nominal cost c0. origin_ms = the time of the loop at which SCENE TIME 0 is (plan addendum O-6 section 5: evaluation cells start the scene at the measured window,
    origin 5000 ms; the warm-up before it runs at the scene's t = 0 conditions). origin 0 = the tuning cells' behaviour, unchanged."""
    base = build(scene or "S0").fg
    scale = float(c0) / C0_MS
    shift = lambda t, o=float(origin_ms): max(t - o, 0.0)       # noqa: E731
    return dataclasses.replace(base, cost_ms=lambda t, b=base, s=scale, f=shift: b.cost_ms(f(t)) * s, active=lambda t, b=base, f=shift: b.active(f(t)))


def _static_action(P, s):
    clk = P.UNLOCKED_MHZ if s["clock"] == "unlocked" else float(s["clock"])
    return Action(clock=clk, pacing=s["mode"], duty=float(s["duty"]), guard_ms=float(s["guard_ms"]))


def build_controller(P, spec):
    k = spec["kind"]
    if k == "static":
        return "static", _static_action(P, spec["setting"])
    if k == "arm_a":
        return "static", Action(clock=P.UNLOCKED_MHZ, pacing="unaligned", duty=1.0, guard_ms=0.5)
    if k == "eB":                                           # g'B action + idle drop to the knee clock with a free background (controllers/static.py)
        from controllers.static import IdleDropController
        return "ctl", IdleDropController(P, _static_action(P, spec["setting"]))
    if k == "gov_static":                                   # diagnostic: the same fixed action, but run through the Governor loop (A/B against the static path)
        from controllers.static import StaticController
        return "ctl", StaticController(_static_action(P, spec["setting"]))
    if k == "cB":
        p = spec["params"]
        return "ctl", SwitchingPIController(P, power_budget_w=float(spec.get("steer_budget_w", spec["budget_w"])), target=p["target"], ki=p["ki"], guard0=0.5, gmin=0.3)
    if k == "dB":
        return "ctl", HybridController(P, float(spec.get("steer_budget_w", spec["budget_w"])), safety=1.0 - float(spec["params"]["margin"]), switch_gain=2.0, clock_every=20)
    raise ValueError(f"no controller for cell kind {k}")


# ---------------------------------------------------------------- simulator dry run
class SimExecutor:
    name = "sim"

    def __init__(self):
        self.P = load_params(ROOT)

    def close(self):
        pass

    def between_cells(self):
        pass

    def run(self, spec, cdir):
        P, k = self.P, spec["kind"]
        fg = fg_spec(spec.get("scene"), spec.get("c0") or 7)
        bg = BgSpec(kind="llama", profile="fp16" if spec.get("scene") == "S5" else None)
        if k == "bg_alone":
            fg = dataclasses.replace(fg, active=lambda t: False)
        sc = build(spec.get("scene") or "S0")
        sc = dataclasses.replace(sc, duration_ms=(65000.0 if k not in ("fg_alone", "bg_alone") else 35000.0), fg=fg, bg=None if k == "fg_alone" else bg, warmup_ms=5000.0)
        if k == "fg_alone":                                                         # c0m at a LOCKED 1800 MHz (defines nominal) and unlocked (addendum O-2)
            seed = zlib.crc32(spec["id"].encode()) % (2 ** 31)
            r = summarise(Plant(P, sc, seed=seed).run(Action(clock=1800.0, pacing="unaligned", duty=1.0, guard_ms=0.5)))
            ru = summarise(Plant(P, sc, seed=seed).run(Action(clock=P.UNLOCKED_MHZ, pacing="unaligned", duty=1.0, guard_ms=0.5)))
            return dict(miss=float(r["miss_frac"]), tok_s=0.0, power_w=float(r["power_w"]), c0m=float(r["lat_p50_ms"]), c0m_unlocked=float(ru["lat_p50_ms"]), sm_locked_median=1800.0,
                        sm_unlocked_median=float(P.UNLOCKED_MHZ), executor="sim")
        if k == "bg_alone":
            policy = Action(clock=P.UNLOCKED_MHZ, pacing="unaligned", duty=1.0, guard_ms=0.5)
        else:
            kind, policy = build_controller(P, spec)
        r = summarise(Plant(P, sc, seed=zlib.crc32(spec["id"].encode()) % (2 ** 31)).run(policy))
        return dict(miss=float(r["miss_frac"]), tok_s=float(r["bg_tok_s"]), power_w=float(r["power_w"]), c0m=float(r["lat_p50_ms"]) if k == "fg_alone" else None, fg_p50_ms=r["lat_p50_ms"], fg_p99_ms=r["lat_p99_ms"],
                    clock_changes=int(r["clock_changes"]), executor="sim")


# ---------------------------------------------------------------- hardware
class HwExecutor:
    name = "hw"

    def __init__(self, power_source="sampled"):
        """power_source for the Governor loop (default 'sampled' since plan addendum O-5; 'energy' only for the diagnostic and the finished first sitting): 'energy' (its own delta of the NVML energy counter every tick: ~10 extra reads/s, each adds ~4.2 J of phantom energy) or 'sampled' (the mean of the NVML
        power samples of the last tick, no energy reads in the loop; plan addendum O-4)."""
        self.power_source = power_source
        import pynvml as nv
        import smoke
        from actuators.startup_reset import reset_clocks
        from workloads.common.exe_warm import ensure_warm, sha256
        from workloads.common.w2lib import W2
        self.smoke, self.nv = smoke, nv
        nv.nvmlInit(); self.h = nv.nvmlDeviceGetHandleByIndex(0)
        self.P = load_params(ROOT)
        self.models = json.loads(MODELS.read_text(encoding="utf-8"))
        self._verified = set()
        for name in ("llama32_1b", "llama32_3b", "phi35_mini"):
            if sha256(Path(self.models[name]["path"])) != self.models[name]["sha256"]:
                sys.exit(f"refused: model {name} does not match its registered sha256")
            self._verified.add(name)
        ensure_warm(smoke.EXE, ["m", "p", "o", "-1", "1", "512", smoke.nm("none1"), smoke.nm("none2"), smoke.nm("none3"), "8"], smoke.REGISTRY)
        self.w = W2(); self.cl = smoke.SafeClient(); self.hb = smoke.Heartbeat(self.cl); self.hb.start()
        reset_clocks(self.cl, is_admin=False)
        self.cal = smoke.calibrate(self.w, self.cl)
        self.cl.reset(); time.sleep(1.1)

    def close(self):
        try:
            self.hb.stop()
        finally:
            try:
                self.cl.reset()
            finally:
                self.cl.close()

    # ---- helpers
    def temp(self):
        return int(self.nv.nvmlDeviceGetTemperature(self.h, self.nv.NVML_TEMPERATURE_GPU))

    def between_cells(self):
        """Release any lock (10 s of unlocked idle happens inside the cool-down), check the lock is gone, wait for >= 20 s and < 55 C, abort above 85 C."""
        self.cl.reset()
        ping = self.cl.ping()
        if not str(ping).endswith("none"):
            self.cl.reset(); time.sleep(1.5)
            ping = self.cl.ping()
            if not str(ping).endswith("none"):
                raise AbortSitting(f"ABORT: clock lock not released (helper PING {ping})")
        t0 = time.time()
        while time.time() - t0 < COOL_MIN_S or self.temp() >= TEMP_COOL_C:
            time.sleep(1.0)
            if time.time() - t0 > 300:
                break
        if self.temp() > TEMP_ABORT_C:
            raise AbortSitting("ABORT: GPU temperature above 85 C")

    def _reason_mask(self):
        nv = self.nv
        thermal = getattr(nv, "nvmlClocksThrottleReasonHwThermalSlowdown", 0x40)
        brake = getattr(nv, "nvmlClocksThrottleReasonHwPowerBrakeSlowdown", 0x80)
        return thermal | brake

    def _poll_reasons(self, stop, acc):
        nv, mask = self.nv, self._reason_mask()
        while not stop.wait(0.1):
            try:
                acc[0] |= int(nv.nvmlDeviceGetCurrentClocksThrottleReasons(self.h)) & mask
            except Exception:                                    # noqa: BLE001
                pass

    def _check_reasons(self, acc):
        if acc[0]:
            raise AbortSitting(f"ABORT: HwThermalSlowdown / HwPowerBrake event reasons {acc[0]:#x} during a cell (cell flagged in cell.json; the sitting stops)")

    def verify_model(self, name):
        """The held-out Llama-3.1-8B is verified against its registered sha256 the first time a cell needs it (never touched before the evaluation)."""
        if name in self._verified:
            return
        from workloads.common.exe_warm import sha256
        if sha256(Path(self.models[name]["path"])) != self.models[name]["sha256"]:
            sys.exit(f"refused: model {name} does not match its registered sha256")
        self._verified.add(name)

    def _launch(self, workload, ctrl, pace, tokens, csv, seconds):
        self.verify_model(workload)
        smoke = self.smoke
        env = dict(os.environ, PATH=str(smoke.BIN) + ";" + os.environ["PATH"])
        return subprocess.Popen([str(smoke.EXE), str(self.models[workload]["path"]), str(smoke.PROMPT), str(csv), "-1", str(seconds), "512", ctrl.name, pace.name, tokens.name, "65536"],
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=env)

    def _wait_first_token(self, pr, tokens):
        t0 = time.time()
        while tokens.write_count == 0:
            if pr.poll() is not None:
                raise RuntimeError("driver exited early: " + pr.stdout.read())
            if time.time() - t0 > 120:
                raise RuntimeError("driver produced no token within 120 s")
            time.sleep(0.1)

    def _energy_thread(self, t_a, t_b, e):
        def run():
            for key, t in (("start", t_a), ("end", t_b)):
                while time.perf_counter() < t:
                    time.sleep(0.002)
                e[key] = self.nv.nvmlDeviceGetTotalEnergyConsumption(self.h)
        th = threading.Thread(target=run, daemon=True); th.start()
        return th

    def _finish_driver(self, pr, ctrl):
        ctrl.write([0.0, 0.0, 0.5])
        try:
            pr.wait(timeout=45)
        except subprocess.TimeoutExpired:
            pr.kill()
        out = pr.stdout.read() if pr.stdout else ""
        return next((ln for ln in out.splitlines() if ln.startswith("EXEC_MODE")), None), out.splitlines()[-2:]

    # ---- cell kinds
    def run(self, spec, cdir):
        k = spec["kind"]
        self.cl.reset()
        if k == "fg_alone":
            return self._fg_alone(spec, cdir)
        if k == "bg_alone":
            return self._bg_alone(spec, cdir)
        return self._fg_bg(spec, cdir)

    def _rings(self):
        smoke = self.smoke
        from telemetry.ring import SeqBlock, SharedRing
        return (SharedRing(smoke.nm("fr"), 8192, 3, True), SharedRing(smoke.nm("tk"), 65536, 2, True), SeqBlock(smoke.nm("ct"), 3, True), SeqBlock(smoke.nm("pc"), 3, True))

    def _bg_alone(self, spec, cdir):
        from w5a_metrics import summarise_cell
        frames, tokens, ctrl, pace = self._rings()
        ctrl.write([0.0, 1.0, 0.5])
        pr = None
        try:
            time.sleep(1.5)
            pr = self._launch(spec["workload"], ctrl, pace, tokens, cdir / "driver.csv", WARM_S + BG_ALONE_MEASURE_S + 12)
            self._wait_first_token(pr, tokens)
            tokens.read_new()
            t0 = time.perf_counter()
            e = {}
            th = self._energy_thread(t0 + WARM_S, t0 + WARM_S + BG_ALONE_MEASURE_S, e)
            while time.perf_counter() < t0 + WARM_S + BG_ALONE_MEASURE_S + 0.2:
                time.sleep(0.05)
            th.join(10)
            tk, dropped = tokens.read_new()
            res = summarise_cell([], tk[:, 0] if len(tk) else np.array([]), tk[:, 1] if len(tk) else np.array([]), t0, WARM_S, BG_ALONE_MEASURE_S, e.get("start", 0.0), e.get("end", 0.0), PERIOD)
        finally:
            exec_mode, tail = self._finish_driver(pr, ctrl) if pr is not None else (None, [])
            self.cl.reset()
        return dict(miss=0.0, tok_s=res["bg_tok_s"], power_w=res["power_w"], tok_ms_p50=res["tok_ms_p50"], bg_tokens=res["bg_tokens"], ring_dropped=int(dropped), exec_mode=exec_mode, driver_tail=tail, executor="hw")

    def _fg_alone(self, spec, cdir):
        """Foreground alone twice: at a LOCKED 1800 MHz (the clock that defines nominal c0 -> c0m) and unlocked (c0m_unlocked), each with the SM clock sampled (addendum O-2: the unlocked clock can sit
        below the boost clock when the GPU idles between frames, which is why trial_fgalone read 6.68 ms at nominal 7)."""
        from telemetry.fg_publisher import FramePublisher
        from workloads.foreground.frame_loop import FmaFrameRunner, FrameLoop
        out = {}
        for tag, lock in (("locked", 1800), ("unlocked", None)):
            ok = self.cl.lock(lock) if lock else self.cl.reset()
            time.sleep(1.5)
            frames, tokens, ctrl, pace = self._rings()
            loop = FrameLoop(fg_spec("S0", spec["c0"]), FmaFrameRunner(self.w, self.cal), FramePublisher(frames, pace))
            smp = self.smoke.NvmlSampler(); smp.start()
            try:
                recs = loop.run(duration_s=FG_ALONE_S)
            finally:
                smp.stop(); self.cl.reset()
            lat = np.array([r["lat_ms"] for r in recs if r["t_sched"] >= loop.t0 + 2.0])
            sm = np.array(smp.sm)
            out[tag] = dict(p50=float(np.percentile(lat, 50)) if len(lat) else float("nan"), p99=float(np.percentile(lat, 99)) if len(lat) else float("nan"), miss=float((lat > PERIOD).mean()) if len(lat) else float("nan"),
                            sm_median=float(np.median(sm)) if len(sm) else float("nan"), sm_p10=float(np.percentile(sm, 10)) if len(sm) else float("nan"), sm_p90=float(np.percentile(sm, 90)) if len(sm) else float("nan"),
                            abandoned=int(loop.abandoned), clock_ok=bool(ok))
        return dict(miss=out["locked"]["miss"], tok_s=0.0, power_w=float("nan"), c0m=out["locked"]["p50"], c0m_unlocked=out["unlocked"]["p50"], fg_p99_ms=out["locked"]["p99"],
                    sm_locked_median=out["locked"]["sm_median"], sm_unlocked_median=out["unlocked"]["sm_median"], sm_unlocked_p10_p90=[out["unlocked"]["sm_p10"], out["unlocked"]["sm_p90"]],
                    c0m_over_nominal=out["locked"]["p50"] / float(spec["c0"]), fg_alone_detail=out, abandoned=out["locked"]["abandoned"] + out["unlocked"]["abandoned"], executor="hw")

    def _fg_bg(self, spec, cdir):
        from actuators.control import ControlActuator
        from controllers.runtime import Governor
        from telemetry.fg_publisher import FramePublisher
        from telemetry.obs_builder import ObsBuilder
        from telemetry.ring import SharedRing
        from w5a_metrics import summarise_cell
        from workloads.foreground.frame_loop import FmaFrameRunner, FrameLoop
        smoke, P = self.smoke, self.P
        frames, tokens, ctrl, pace = self._rings()
        kind, obj = build_controller(P, spec)
        gov, glog, gerr = None, [], []
        if kind == "static":
            ctrl.write([1.0 if obj.pacing == "aligned" else 0.0, float(obj.duty), float(obj.guard_ms)])
            ok_clock = self.cl.reset() if obj.clock >= P.UNLOCKED_MHZ else self.cl.lock(int(obj.clock))
        else:
            gov = Governor(obj, ObsBuilder(PERIOD, PERIOD), ControlActuator(ctrl, self.cl, P.UNLOCKED_MHZ), SharedRing(frames.name, 8192, 3, False), SharedRing(tokens.name, 65536, 2, False), PERIOD, PERIOD, params=P)
            gov.start(0.0)
            ok_clock = True
        pr, smp, stop, acc, pstop = None, None, threading.Event(), [0], threading.Event()
        reads, lastpw = [0], [0.0]
        try:
            time.sleep(1.5)
            pr = self._launch(spec["workload"], ctrl, pace, tokens, cdir / "driver.csv", WARM_S + MEASURE_S + 12)
            self._wait_first_token(pr, tokens)
            tokens.read_new()
            smp = smoke.NvmlSampler(); smp.start()
            threading.Thread(target=self._poll_reasons, args=(pstop, acc), daemon=True).start()
            gth = None
            if gov is not None:
                source = spec.get("power_source") or self.power_source

                def loop_gov():
                    tick = time.perf_counter()
                    while not stop.is_set():
                        tick += 0.1
                        time.sleep(max(0.0, tick - time.perf_counter()))
                        try:
                            pw = None
                            if spec.get("gov_no_energy"):
                                e = 0.0
                            elif source == "sampled":
                                e, pw = 0.0, recent_mean(smp.t, smp.pw, time.perf_counter(), 0.1)
                                pw = lastpw[0] if pw != pw else pw                            # no sample in the span (rare): keep the last good value
                                lastpw[0] = pw
                            else:
                                e = smp.nv.nvmlDeviceGetTotalEnergyConsumption(smp.h) / 1000.0
                                reads[0] += 1
                            a = gov.step(time.perf_counter() * 1000.0, e, smp.sm[-1], power_w=pw)
                            glog.append((time.perf_counter(), a.clock, a.duty, a.guard_ms, smp.sm[-1], mode_code(getattr(obj, "mode", None) or getattr(getattr(obj, "a", None), "pacing", None)), float("nan") if pw is None else pw))
                        except Exception as ex:                  # noqa: BLE001
                            gerr.append(f"{type(ex).__name__}: {ex}"); return
                gth = threading.Thread(target=loop_gov, daemon=True); gth.start()
            loop = FrameLoop(fg_spec(spec["scene"], spec["c0"], spec.get("origin_ms", 0.0)), FmaFrameRunner(self.w, self.cal), FramePublisher(frames, pace))
            t0 = time.perf_counter() + 0.05
            e = {}
            th = self._energy_thread(t0 + WARM_S, t0 + WARM_S + MEASURE_S, e)
            temp_before = self.temp()
            recs = loop.run(duration_s=WARM_S + MEASURE_S, t0=t0)
            th.join(10)
            stop.set()
            if gth is not None:
                gth.join(5)
            smp.stop(); pstop.set()
            tk, dropped = tokens.read_new()
            if gerr:
                raise RuntimeError("governor loop failed: " + gerr[0])
            t_sm, sm = np.array(smp.t), np.array(smp.sm)
            win = (t_sm >= t0 + WARM_S) & (t_sm < t0 + WARM_S + MEASURE_S)
            pw_t, pw_w = trace_bins(smp.t, smp.pw, t0, t0 + WARM_S + MEASURE_S, step_s=0.5)
            res = summarise_cell(recs, tk[:, 0] if len(tk) else np.array([]), tk[:, 1] if len(tk) else np.array([]), t0, WARM_S, MEASURE_S, e.get("start", 0.0), e.get("end", 0.0), PERIOD)
            n_ab = int(loop.abandoned)
            miss = (res["miss_frac"] * res["frames"] + n_ab) / (res["frames"] + n_ab) if res["frames"] else float("nan")
            np.savez_compressed(cdir / "frames.npz", t_sched=[r["t_sched"] for r in recs], lat_ms=[r["lat_ms"] for r in recs], tok_end=tk[:, 0] if len(tk) else [], tok_ms=tk[:, 1] if len(tk) else [], t0=t0,
                                gov_log=np.array(glog, float).reshape(-1, 7), pw_trace_t=pw_t, pw_trace_w=pw_w)
            changes = int(sum(1 for a, b in zip(glog, glog[1:]) if a[1] != b[1]))
            reads_n = int(reads[0])
            if (spec.get("power_source") or self.power_source) == "sampled" and reads_n:
                raise RuntimeError(f"cell {spec['id']}: the sampled-source Governor loop read the energy counter {reads_n} times (plan addendum O-5: governed cells never read the energy counter)")
            out = dict(miss=float(miss), miss_completed=res["miss_frac"], tok_s=res["bg_tok_s"], power_w=res["power_w"], power_sampled_w=window_mean(np.array(smp.t), np.array(smp.pw), t0 + WARM_S, t0 + WARM_S + MEASURE_S), fg_p50_ms=res["fg_p50_ms"], fg_p99_ms=res["fg_p99_ms"], frames=res["frames"], abandoned=n_ab,
                       bg_tokens=res["bg_tokens"], tok_ms_p50=res["tok_ms_p50"], sm_mhz_median=float(np.median(sm[win])) if win.any() else float("nan"), temp_before_c=temp_before, temp_after_c=self.temp(),
                       clock_changes=changes, clamp_events=0 if gov is None else len(gov.clamped), power_source=None if gov is None else ('none' if spec.get('gov_no_energy') else (spec.get('power_source') or self.power_source)), gov_reads=reads_n, gov_reads_per_s=reads_n / (WARM_S + MEASURE_S), clamp_examples=[] if gov is None else gov.clamped[:3], final_pacing_mode=getattr(obj, 'mode', None) if gov is not None else None, clock_ok=bool(ok_clock), ring_dropped=int(dropped), thermal_reason_bits=int(acc[0]), executor="hw")
        finally:
            stop.set(); pstop.set()
            if smp is not None:
                smp.stop()
            exec_mode, tail = self._finish_driver(pr, ctrl) if pr is not None else (None, [])
            self.cl.reset()
        out.update(exec_mode=exec_mode, driver_tail=tail)
        self._check_reasons(acc)
        return out
