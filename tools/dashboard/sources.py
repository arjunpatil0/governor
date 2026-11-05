"""Data sources of the Co-Scheduler Lab dashboard (tools/dashboard/server.py): the cell catalogue, REPLAY of a recorded cell and LIVE attach to a running session. Standard library + numpy + the project's own
telemetry readers only. READ-ONLY by construction: nothing here writes a ring, a control block or the clock helper, and NVML is used for the SAMPLED power (nvmlDeviceGetPowerUsage) and the SM clock only,
never the energy counter (phantom-energy finding, plan addenda O-4 / O-5). tests/test_dashboard_server.py greps for violations.
All times in the streamed messages are SECONDS relative to the start of the cell (replay: the cell's t0; live: the moment of attach). One message = one dict (see ReplaySource.tick / LiveSource.tick):
  seq, mode, t (the source's "now"), rate (source seconds per wall second; 0 = paused / ended), phase, events{frames [arr, start, end, late], tokens [start, end], power [t, W], sm [t, MHz],
  ctrl [t, mode(1 aligned / 0 unaligned / -1 n/a), duty, guard_ms, clock_cmd], decisions [dict of telemetry/decision_block.DECISION_FIELDS with t_s relative]}, stats{frames, late, tokens, miss_pct, tok_s, power_w, window_s}."""
import json
import math
import threading
import time
from pathlib import Path

import numpy as np

PERIOD_S = 1.0 / 60.0
WARM_S, MEASURE_S = 5.0, 60.0                         # the cell protocol (experiments/w5b/executors.py): 5 s warm-up, 60 s measured window
POWER_PLAUSIBLE_MAX_W = 250.0                         # the RTX 4070 Laptop GPU cannot draw more; larger NVML readings are glitches
LOOKAHEAD_S = 0.12                                   # replay messages carry events up to this far past "now" so the page can draw frames and tokens that are in progress
MODEL_LABEL = {"llama32_1b": "1B", "llama32_3b": "3B", "phi35_mini": "Phi", "llama31_8b": "8B"}
MODEL_CODE = {"llama32_1b": "1b", "llama32_3b": "3b", "phi35_mini": "phi", "llama31_8b": "8b"}
MANAGER_LABEL = {"a": "Nobody", "g'B": "Best fixed setting", "eB": "Fixed + idle rule", "c'B-T3b": "Simple reacting (PI)", "c'B-T3c": "Simple reacting (PI, T3c)", "d'B": "Governor"}
KIND_MANAGER = {"arm_a": "a", "static": "g'B", "eB": "eB", "cB": "c'B-T3b", "dB": "d'B", "gov_static": "g'B"}


def clean(o):
    """JSON-safe copy: NaN / inf become None, numpy scalars and arrays become python values."""
    if isinstance(o, dict):
        return {str(k): clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [clean(v) for v in o]
    if isinstance(o, np.ndarray):
        return clean(o.tolist())
    if isinstance(o, (np.floating, float)):
        f = float(o)
        return f if math.isfinite(f) else None
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, np.bool_):
        return bool(o)
    return o


# ---------------------------------------------------------------- catalogue
def _group_of(parts):
    """data/w5b/<...> path parts -> catalogue group."""
    top = parts[0]
    if top == "eval":
        return "eval-discarded" if len(parts) > 1 and parts[1] == "discarded" else "eval"
    if top in ("eval_trial", "eval_trial2", "trial", "trial2"):
        return "trial"
    return top                                               # tuning, t3b, t3c, diag


def _cell_info(cj, group, key):
    d = json.loads(cj.read_text(encoding="utf-8"))
    spec, m = d.get("spec") or {}, d.get("metrics") or {}
    ctrl = spec.get("controller") or KIND_MANAGER.get(spec.get("kind"), spec.get("kind"))
    wl = spec.get("workload")
    block = spec.get("block")
    if block is None:
        for p in cj.parts:
            if p.startswith("block") and p[5:].isdigit():
                block = int(p[5:])
    return dict(key=key, id=d.get("id") or cj.parent.name, group=group, block=block, scene=spec.get("scene"), controller=ctrl, manager=MANAGER_LABEL.get(ctrl, ctrl), workload=wl,
                model=MODEL_LABEL.get(wl, wl), model_code=MODEL_CODE.get(wl), budget_w=spec.get("budget_w"), kind=spec.get("kind"), demo=bool(spec.get("demo")),
                miss=m.get("miss_completed", m.get("miss")), tok_s=m.get("tok_s"), power_w=m.get("power_w"), power_sampled_w=m.get("power_sampled_w"))


def list_cells(root):
    """Every recorded cell that has a frames.npz: data/w5b/**/cells/*/cell.json (not the simulator dry runs) and data/dashboard_demos/*/cell.json."""
    root = Path(root)
    data = root / "data"
    out = []
    for cj in sorted((data / "w5b").glob("**/cells/*/cell.json")):
        rel = cj.relative_to(data / "w5b").parts
        if rel[0] == "_dryrun" or not (cj.parent / "frames.npz").exists():
            continue
        try:
            out.append(_cell_info(cj, _group_of(rel), cj.parent.relative_to(data).as_posix()))
        except (ValueError, OSError):
            continue
    for cj in sorted((data / "dashboard_demos").glob("*/cell.json")):
        if (cj.parent / "frames.npz").exists():
            try:
                out.append(_cell_info(cj, "demo", cj.parent.relative_to(data).as_posix()))
            except (ValueError, OSError):
                continue
    return out


def resolve_cell(root, key):
    """The cell directory for a catalogue key, only if it lies inside <root>/data (no path traversal)."""
    data = (Path(root) / "data").resolve()
    p = (data / key).resolve()
    if data not in p.parents or not (p / "cell.json").exists():
        raise FileNotFoundError(key)
    return p


# ---------------------------------------------------------------- replay
class ReplaySource:
    """Plays a recorded cell back from frames.npz (frames, tokens, 10 Hz governor log, 0.5 s sampled-power trace) and the cell's spec / metrics. Frame start times are RECONSTRUCTED (a frame starts when it
    arrived or when the previous one ended, whichever is later: the loop is single-threaded); token starts are end - duration. Governor predictions exist only for demo cells (decisions.npz)."""
    mode = "replay"

    def __init__(self, cell_dir, key=None):
        cell_dir = Path(cell_dir)
        d = json.loads((cell_dir / "cell.json").read_text(encoding="utf-8"))
        self.spec, self.metrics, self.dir, self.key = d.get("spec") or {}, d.get("metrics") or {}, cell_dir, key
        z = np.load(cell_dir / "frames.npz", allow_pickle=False)
        t0 = float(z["t0"])
        self.t0 = t0
        ts_abs = np.asarray(z["t_sched"], float)
        ts = ts_abs - t0
        lat = np.asarray(z["lat_ms"], float) / 1000.0
        end = ts + lat
        order = np.argsort(end, kind="stable")
        ts, lat, end, ts_abs = ts[order], lat[order], end[order], ts_abs[order]
        start = np.maximum(ts, np.concatenate([[-np.inf], end[:-1]]))
        self.f_arr, self.f_start, self.f_end, self.f_lat, self.f_arr_abs = ts, start, end, lat, ts_abs
        te_abs = np.asarray(z["tok_end"], float)
        te = te_abs - t0
        tm = np.asarray(z["tok_ms"], float) / 1000.0
        o = np.argsort(te, kind="stable")
        self.k_end, self.k_start, self.k_end_abs = te[o], te[o] - tm[o], te_abs[o]
        if "pw_trace_t" in z.files:
            self.tr_t, self.tr_w = np.asarray(z["pw_trace_t"], float), np.asarray(z["pw_trace_w"], float)
        else:
            self.tr_t = self.tr_w = np.empty(0)
        raw = np.asarray(z["gov_log"], float) if "gov_log" in z.files else np.empty((0, 0))
        gl = raw.reshape(-1, raw.shape[-1]) if raw.size else np.empty((0, 0))
        has_g = gl.ndim == 2 and gl.shape[1] >= 5 and len(gl) > 0
        self.g_t = gl[:, 0] - t0 if has_g else np.empty(0)
        self.g_ctrl = np.column_stack([gl[:, 5] if gl.shape[1] >= 6 else np.full(len(gl), -1.0), gl[:, 2], gl[:, 3], gl[:, 1]]) if has_g else np.empty((0, 4))
        self.g_sm = gl[:, 4] if has_g else np.empty(0)
        gpw = gl[:, 6] if has_g and gl.shape[1] >= 7 else np.full(len(gl), np.nan)
        if has_g and np.isfinite(gpw).any():
            self.pw_t, self.pw_w = self.g_t[np.isfinite(gpw)], gpw[np.isfinite(gpw)]
        else:
            self.pw_t, self.pw_w = self.tr_t, self.tr_w
        self.dec = []
        if (cell_dir / "decisions.npz").exists():
            dz = np.load(cell_dir / "decisions.npz", allow_pickle=False)
            names = [str(n) for n in dz["fields"]]
            for row in dz["rows"]:
                r = dict(zip(names, row.tolist()))
                r["t_s"] = r["t_s"] - t0
                self.dec.append(r)
        self.static_ctrl = None
        if not len(self.g_t):                                             # static setting / arm a: the commanded action never changes
            s = self.spec.get("setting")
            if self.spec.get("kind") == "arm_a":
                self.static_ctrl = [0.0, 1.0, 0.5, 2460.0]
            elif s:
                self.static_ctrl = [1.0 if s["mode"] == "aligned" else 0.0, float(s["duty"]), float(s["guard_ms"]), 2460.0 if s["clock"] == "unlocked" else float(s["clock"])]
        self.duration = float(max([self.f_end[-1] if len(self.f_end) else 0.0, self.k_end[-1] if len(self.k_end) else 0.0, self.g_t[-1] if len(self.g_t) else 0.0]))
        self.speed, self.playing = 0.1, True
        self.seq = 0
        self.restart()

    # ---- control
    def _reset_cursors(self):
        self._cur = dict(f=0, k=0, pw=0, g=0, d=0, st=False)

    def restart(self):
        self.t, self._h, self._pending_seek = 0.0, -1.0, True
        self._reset_cursors()

    def control(self, action, value=None):
        if action == "play":
            self.playing = True
            if self.t >= self.duration:
                self.restart()
        elif action == "pause":
            self.playing = False
        elif action == "speed":
            self.speed = float(value)
        elif action == "seek":
            self.t, self._h, self._pending_seek = min(max(0.0, float(value)), self.duration), -1.0, True
            self._reset_cursors()
        elif action == "restart":
            self.restart()
        else:
            raise ValueError(f"unknown replay action {action}")

    def meta(self):
        sp = self.spec
        ctrl = sp.get("controller") or KIND_MANAGER.get(sp.get("kind"), sp.get("kind"))
        return clean(dict(mode="replay", key=self.key, id=sp.get("id") or self.dir.name, scene=sp.get("scene"), controller=ctrl, manager=MANAGER_LABEL.get(ctrl, ctrl), workload=sp.get("workload"),
                          model=MODEL_LABEL.get(sp.get("workload")), model_code=MODEL_CODE.get(sp.get("workload"), "3b"), budget_w=sp.get("budget_w"), block=sp.get("block"), duration=self.duration,
                          warm_s=WARM_S, measure_s=MEASURE_S, demo=bool(sp.get("demo")), has_predictions=bool(self.dec), frame_starts_reconstructed=True, speeds=[0.04, 0.1, 0.3, 1.0, 4.0],
                          outcome={k: self.metrics.get(k) for k in ("miss", "miss_completed", "tok_s", "power_w", "power_sampled_w", "fg_p99_ms", "sm_mhz_median", "final_pacing_mode", "executor")}))

    # ---- streaming
    @staticmethod
    def _upto(arr, cur, h):
        n = int(np.searchsorted(arr, h, side="right"))
        return cur, max(cur, n)

    def stats_at(self, t):
        """Running totals of the MEASURED window up to source time t (the definition of experiments/w5a/w5a_metrics.summarise_cell, restricted to frames and tokens finished by t)."""
        w0, w1 = WARM_S, WARM_S + MEASURE_S
        a0, a1 = self.t0 + WARM_S, self.t0 + WARM_S + MEASURE_S                  # window membership in the recorder's own (absolute) arithmetic: no rounding flips at the edges
        m = (self.f_arr_abs >= a0) & (self.f_arr_abs < a1) & (self.f_end <= t)
        nf, late = int(m.sum()), int((self.f_lat[m] > PERIOD_S + 1e-12).sum())
        nt = int(((self.k_end_abs >= a0) & (self.k_end_abs < a1) & (self.k_end <= t)).sum())
        el = max(0.0, min(t, w1) - w0)
        pm = (self.tr_t >= w0) & (self.tr_t < min(t, w1)) if len(self.tr_t) else np.zeros(0, bool)
        return dict(frames=nf, late=late, tokens=nt, miss_pct=100.0 * late / nf if nf else None, tok_s=nt / el if el > 0 else None,
                    power_w=float(np.mean(self.tr_w[pm])) if pm.any() else None, window_s=el)

    def tick(self, dt_wall):
        if self.playing and self.t < self.duration:
            self.t = min(self.duration, self.t + dt_wall * self.speed)
        h = min(self.duration + LOOKAHEAD_S, self.t + LOOKAHEAD_S + (dt_wall * self.speed if self.playing else 0.0))
        h = max(h, self._h)
        c, ev = self._cur, {}
        a, b = self._upto(self.f_end, c["f"], h); c["f"] = b
        ev["frames"] = [[self.f_arr[i], self.f_start[i], self.f_end[i], bool(self.f_lat[i] > PERIOD_S + 1e-12)] for i in range(a, b)]
        a, b = self._upto(self.k_end, c["k"], h); c["k"] = b
        ev["tokens"] = [[self.k_start[i], self.k_end[i]] for i in range(a, b)]
        a, b = self._upto(self.pw_t, c["pw"], h); c["pw"] = b
        ev["power"] = [[self.pw_t[i], self.pw_w[i]] for i in range(a, b)]
        a, b = self._upto(self.g_t, c["g"], h); c["g"] = b
        ev["sm"] = [[self.g_t[i], self.g_sm[i]] for i in range(a, b)]
        if len(self.g_t):
            ev["ctrl"] = [[self.g_t[i], *self.g_ctrl[i].tolist()] for i in range(a, b)]
        else:
            ev["ctrl"] = [[0.0, *self.static_ctrl]] if (self.static_ctrl and not c["st"]) else []
        c["st"] = True
        dts = np.array([r["t_s"] for r in self.dec]) if self.dec else np.empty(0)
        a, b = self._upto(dts, c["d"], h); c["d"] = b
        ev["decisions"] = [self.dec[i] for i in range(a, b)]
        self._h = h
        self.seq += 1
        seek, self._pending_seek = self._pending_seek, False
        done = self.t >= self.duration
        phase = "done" if done else ("warm-up" if self.t < WARM_S else "measured")
        return clean(dict(seq=self.seq, mode="replay", t=self.t, rate=(self.speed if self.playing and not done else 0.0), phase=phase, seek=seek, playing=self.playing, speed=self.speed, events=ev, stats=self.stats_at(self.t)))

    def close(self):
        pass


def summarise_messages(msgs, period_s=PERIOD_S):
    """What a client can reconstruct from a stream of replay messages (the test of 'replay reproduces the recorded miss / tok/s / power'): frames and tokens of the measured window, from the events only."""
    w0, w1 = WARM_S, WARM_S + MEASURE_S
    frames, tokens, power = {}, {}, {}
    for m in msgs:
        for arr, st, en, late in m["events"]["frames"]:
            frames[(arr, en)] = (arr, en)
        for s, e in m["events"]["tokens"]:
            tokens[(s, e)] = e
        for t, w in m["events"]["power"]:
            power[t] = w
    fr = [(a, e) for a, e in frames.values() if w0 <= a < w1]
    late = sum(1 for a, e in fr if (e - a) > period_s + 1e-12)
    tk = sum(1 for e in tokens.values() if w0 <= e < w1)
    pw = [w for t, w in power.items() if w0 <= t < w1]
    return dict(frames=len(fr), miss=late / len(fr) if fr else float("nan"), tok_s=tk / MEASURE_S, power_w=float(np.mean(pw)) if pw else float("nan"))


# ---------------------------------------------------------------- live
class NvmlPoller:
    """SAMPLED power and SM clock through NVML (nvmlDeviceGetPowerUsage, nvmlDeviceGetClockInfo): never the energy counter. read() -> (power_w, sm_mhz) or (None, None) without NVML."""

    def __init__(self, period_s=0.05):
        self.latest, self.stop_ev = (None, None), threading.Event()
        try:
            import pynvml as nv
            nv.nvmlInit()
            self.nv, self.h = nv, nv.nvmlDeviceGetHandleByIndex(0)
        except Exception:                                                    # noqa: BLE001
            self.nv = self.h = None
            return
        self.period_s = period_s
        threading.Thread(target=self._poll, daemon=True).start()              # NVML calls can take tens of ms: poll in a thread so the 20 Hz stream never waits for them

    def _poll(self):
        while not self.stop_ev.wait(self.period_s):
            try:
                self.latest = (self.nv.nvmlDeviceGetPowerUsage(self.h) / 1000.0, float(self.nv.nvmlDeviceGetClockInfo(self.h, self.nv.NVML_CLOCK_SM)))
            except Exception:                                                # noqa: BLE001
                self.latest = (None, None)

    def read(self):
        return self.latest

    def close(self):
        self.stop_ev.set()


def read_session(path):
    """The session registry written by tools/dashboard/demo.py, or None (missing / unreadable / the owning process is gone)."""
    p = Path(path)
    if not p.exists():
        return None
    try:
        s = json.loads(p.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return None
    pid = s.get("pid")
    if pid:
        try:
            import psutil
            if not psutil.pid_exists(int(pid)):
                return None
        except ImportError:
            pass
    s["_path"] = str(p)
    return s


class LiveSource:
    """Attaches READ-ONLY to a running governed session: the frame ring [t_sched, t_start, t_end], the token ring [t_end, ms], the pace block, the control block and the decision block, by the names in the session
    registry, with the project's own SharedRing / SeqBlock readers (create=False: no header is ever written), plus sampled NVML power and SM clock."""
    mode = "live"

    def __init__(self, session, poller=None, clock=time.perf_counter):
        from telemetry.decision_block import DecisionBlock
        from telemetry.ring import SeqBlock, SharedRing
        self.session, self.clock, self.poller = session, clock, poller if poller is not None else NvmlPoller()
        n = session["names"]
        self.frames = SharedRing(n["frames"], n.get("frames_capacity", 8192), 3, create=False)
        self.tokens = SharedRing(n["tokens"], n.get("tokens_capacity", 65536), 2, create=False)
        self.ctrl, self.pace = SeqBlock(n["ctrl"], 3, create=False), SeqBlock(n["pace"], 3, create=False)
        self.dec = DecisionBlock(n["decision"], create=False) if n.get("decision") else None
        self.frames.read_pos, self.tokens.read_pos = self.frames.write_count, self.tokens.write_count         # attach mid-session: no history, only what happens from now
        self.ta = clock()
        self.seq, self.n_frames, self.n_late, self.n_tokens, self.psum, self.pn, self.power_glitches = 0, 0, 0, 0, 0.0, 0, 0
        self.last_dec_tick = None
        self._ctrl_good = None
        self.sm = None

    def meta(self):
        s = self.session
        return clean(dict(mode="live", id=s.get("id"), scene=s.get("scene"), controller=s.get("controller"), manager=MANAGER_LABEL.get(s.get("controller"), s.get("controller")), workload=s.get("workload"),
                          model=MODEL_LABEL.get(s.get("workload")), model_code=MODEL_CODE.get(s.get("workload"), "3b"), budget_w=s.get("budget_w"), demo=bool(s.get("demo", True)), synthetic=bool(s.get("synthetic", False)), has_predictions=bool(self.dec),
                          warm_s=WARM_S, measure_s=MEASURE_S, lag_s=0.12))

    def alive(self):
        return read_session(self.session["_path"]) is not None if self.session.get("_path") else True

    def tick(self, dt_wall):
        now = self.clock() - self.ta
        ev = {}
        fr, dropped = self.frames.read_new()
        ev["frames"] = []
        for r in fr:
            late = bool((r[2] - r[0]) > PERIOD_S + 1e-12)
            ev["frames"].append([r[0] - self.ta, r[1] - self.ta, r[2] - self.ta, late])
            self.n_frames += 1
            self.n_late += late
        tk, _ = self.tokens.read_new()
        ev["tokens"] = [[r[0] - r[1] / 1000.0 - self.ta, r[0] - self.ta] for r in tk]
        self.n_tokens += len(tk)
        p, sm = self.poller.read()
        if p is not None and not (0.0 <= p <= POWER_PLAUSIBLE_MAX_W):                  # NVML on this laptop sometimes returns 590 W (590006 mW) for a few samples: not a power the GPU can draw; dropped and counted
            self.power_glitches, p = self.power_glitches + 1, None
        ev["power"] = [] if p is None else [[now, p]]
        ev["sm"] = [] if sm is None else [[now, sm]]
        if p is not None:
            self.psum, self.pn = self.psum + p, self.pn + 1
        if sm is not None:
            self.sm = sm
        pc = self.pace.read()
        c = self.ctrl.read()
        self._ctrl_good = c if c is not None else self._ctrl_good
        ev["ctrl"] = [] if self._ctrl_good is None else [[now, self._ctrl_good[0], self._ctrl_good[1], self._ctrl_good[2], self.sm]]
        ev["decisions"] = []
        if self.dec is not None:
            from telemetry.decision_block import read_decision
            d = read_decision(self.dec)
            if d is not None and d["tick"] != self.last_dec_tick:
                self.last_dec_tick = d["tick"]
                d = dict(d)
                d["t_s"] = d["t_s"] - self.ta
                ev["decisions"].append(d)
        self.seq += 1
        pace = None if pc is None else dict(busy=bool(pc[0]), next=pc[1] - self.ta, updated=pc[2] - self.ta, age=now - (pc[2] - self.ta))
        el = max(1e-9, now)
        stats = dict(frames=self.n_frames, late=self.n_late, tokens=self.n_tokens, miss_pct=100.0 * self.n_late / self.n_frames if self.n_frames else None, tok_s=self.n_tokens / el,
                     power_w=self.psum / self.pn if self.pn else None, window_s=el, power_glitches=self.power_glitches)
        return clean(dict(seq=self.seq, mode="live", t=now, rate=1.0, phase="live", events=ev, pace=pace, stats=stats, dropped=int(dropped)))

    def control(self, action, value=None):
        raise ValueError("a live feed cannot be controlled from the dashboard (read-only)")

    def close(self):
        if hasattr(self.poller, "close"):
            self.poller.close()
