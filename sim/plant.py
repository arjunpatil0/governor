"""Governor simulator plant: one GPU shared by a frame-paced foreground (fg) and a token-decoding background (bg).

Model (all parameters from sim/params.py, i.e. committed results; unmeasured assumptions are listed in ASSUMPTIONS and printed in every report header):
- Two contexts, time-sliced (journal 0033: nearly synchronous switch, no true concurrency). While both have work each progresses at 1/S of its solo
  speed, S = 2 + 2s/q = 2.79 (fluid approximation of q = 0.374 ms slices with s = 0.148 ms gaps); alone each runs at full speed.
- fg frame work scales with the SM clock by the W1/B ratio; a bg token takes 1/tok_s(clock) (L, bg alone) or, for the A2 anchor runs, a 2 ms fma slice.
- Clock actuation: a requested clock takes effect clock_latency_ms later (capability audit, nvidia-smi -lgc median), at most one change per
  clock_min_interval_ms (actuator policy, not a measurement). A thermal cap can clamp the effective clock.
- Pacing. unaligned: after a token, sleep measured_token_time * (1/duty - 1) (loadgen.duty_gap; the A2 DLL uses the measured slice time). aligned (frame-synchronous): bg may start a token only while no fg
  frame is queued and now + token_time + guard <= the next fg arrival (known: periodic fg, lookahead two periods; none within that => the fg is idle and the bg runs free).
- Power: time-weighted: fg only = W1 fma power at the clock, bg only = L power, both = their mean, neither = idle power (journal 0011).
"""
from collections import deque
from dataclasses import dataclass, field
from typing import Callable, Optional

import numpy as np

TICK_MS = 100.0                     # governor / daemon period (10 Hz)
ASSUMPTIONS = (
    "fg and bg effects separable: no joint (clock, duty) measurement exists",
    "bg speed under contention follows the same time-slice share as the fg (L measured the bg alone)",
    "token-level pacing: a bg token is one indivisible ~10 ms job (A2 duty used 2 ms slices)",
    "'unlocked' fg speed from W1 (2460 MHz) with no thermal throttling unless a scenario caps it",
    "fg frame jitter (jitter_sigma) is a scenario parameter, not measured",
    "idle power 5 W from a single pilot observation (journal 0011)",
)


@dataclass(frozen=True)
class Action:
    clock: float = 1800.0
    pacing: str = "unaligned"        # "unaligned" | "aligned"
    duty: float = 1.0                # unaligned: fraction of time the bg may run
    guard_ms: float = 0.5            # aligned: slack kept free before the next fg arrival


@dataclass
class Obs:
    t_ms: float
    lat_ms: np.ndarray               # latencies of fg frames completed in the last tick
    n_missed: int
    n_arrived: int
    tokens: int
    power_w: float
    clock_mhz: float                 # effective clock at the tick
    period_ms: float
    deadline_ms: float


@dataclass
class FgSpec:
    period_ms: float
    arrivals: str                    # "periodic" | "poisson" (period_ms = mean inter-arrival)
    cost_ms: Callable                # t_ms -> mean frame work (ms, alone at 1800 MHz)
    jitter_sigma: float
    deadline_ms: float
    active: Callable = lambda t: True


@dataclass
class BgSpec:
    kind: str = "llama"              # "llama" (token = 1/tok_s(clock)) | "slice" (fma slice of slice_ms at 1800 MHz)
    slice_ms: float = 2.0


@dataclass
class Scenario:
    name: str
    duration_ms: float
    fg: FgSpec
    bg: Optional[BgSpec] = None
    clock_cap: Optional[list] = None          # [(t_ms, cap_mhz)], piecewise constant
    warmup_ms: float = 0.0
    clock_min_interval_ms: float = 1000.0
    interaction: float = 0.0                  # scenario S4: co-run share divisor x (1 + interaction * (1800/clock - 1)); controllers do not know it


@dataclass
class Result:
    arr_ms: np.ndarray
    lat_ms: np.ndarray
    tok_t_ms: np.ndarray
    energy_j: float
    clock_log: list
    n_clock_changes: int
    n_rate_limited: int
    duration_ms: float
    warmup_ms: float
    deadline_ms: float
    tick_t: np.ndarray
    tick_e: np.ndarray
    actions: list = field(default_factory=list)


class _Static:
    def __init__(self, a):
        self.a = a

    def reset(self, ctx=None):
        return self.a

    def act(self, obs):
        return self.a


class Plant:
    def __init__(self, params, scenario, seed=0):
        self.p, self.sc, self.seed = params, scenario, int(seed)

    def _arrivals(self, rng):
        fg, T = self.sc.fg, self.sc.duration_ms
        if fg.arrivals == "periodic":
            a = np.arange(0.0, T, fg.period_ms)
        elif fg.arrivals == "poisson":
            n = int(T / fg.period_ms * 1.5) + 50
            a = np.cumsum(rng.exponential(fg.period_ms, n))
            a = a[a < T]
        else:
            raise ValueError(fg.arrivals)
        a = np.array([t for t in a if fg.active(t)])
        sig = fg.jitter_sigma
        jit = rng.lognormal(-0.5 * sig * sig, sig, len(a)) if sig > 0 else np.ones(len(a))
        w = np.array([fg.cost_ms(t) for t in a]) * jit
        return a, w

    def run(self, policy):
        P, sc = self.p, self.sc
        if not hasattr(policy, "act"):
            policy = _Static(policy)
        T, fg, bg = sc.duration_ms, sc.fg, sc.bg
        rng = np.random.default_rng(np.random.SeedSequence(self.seed))
        arr, w = self._arrivals(rng)
        n = len(arr)
        lat = np.full(n, np.nan)
        S = P.share_divisor
        act = policy.reset(dict(params=P, period_ms=fg.period_ms, deadline_ms=fg.deadline_ms, scenario=sc))
        if act.pacing == "aligned" and fg.arrivals != "periodic":
            raise ValueError("aligned pacing needs a periodic fg")
        caps = sorted(sc.clock_cap or [])
        applied = float(act.clock)
        target = applied
        pending = None
        last_req = -1e18
        n_changes = n_limited = 0
        eff_prev = None
        clock_log = []
        q = deque()
        prog = 0.0
        ai = 0
        t = 0.0
        bg_run = False
        bg_prog = 0.0
        bg_t0 = 0.0
        bg_wake = 0.0
        tok_t = []
        energy = 0.0
        next_tick = TICK_MS
        tick_lat, tick_missed, tick_arr, tick_tok, tick_e0, tick_t0 = [], 0, 0, 0, 0.0, 0.0
        tick_t_list, tick_e_list, actions = [0.0], [0.0], []
        eps = 1e-9

        def cap_at(tt):
            c = float("inf")
            for ct, cv in caps:
                if ct <= tt + eps:
                    c = cv
            return c

        def bgdur(clock):
            return (1000.0 / P.tok_s(clock)) if bg.kind == "llama" else bg.slice_ms * P.fg_ratio(clock)

        def next_arrival(tt):
            if ai < n and arr[ai] - tt <= 2 * fg.period_ms + eps:
                return arr[ai]
            return float("inf")

        while t < T - eps:
            eff = max(min(applied, cap_at(t)), P._fg_x[0])
            if eff != eff_prev:
                clock_log.append((t, eff)); eff_prev = eff
            # ---- bg start rule
            if bg is not None and not bg_run:
                if act.pacing == "aligned":
                    if not q and t + bgdur(eff) + act.guard_ms <= next_arrival(t) + eps:
                        bg_run, bg_prog, bg_t0 = True, 0.0, t
                elif act.duty > 0 and t >= bg_wake - eps:
                    bg_run, bg_prog, bg_t0 = True, 0.0, t
            fg_on = bool(q)
            share = 1.0 / (S * (1.0 + sc.interaction * (1800.0 / eff - 1.0))) if (fg_on and bg_run) else 1.0
            fgd = w[q[0]] * P.fg_ratio(eff) if fg_on else 0.0
            bgd = bgdur(eff) if bg_run else 0.0
            cand = [next_tick, T]
            if ai < n:
                cand.append(arr[ai])
            if pending is not None:
                cand.append(pending[0])
            cand += [ct for ct, _ in caps if ct > t + eps]
            if fg_on:
                cand.append(t + (1 - prog) * fgd / share)
            if bg_run:
                cand.append(t + (1 - bg_prog) * bgd / share)
            elif bg is not None and act.pacing == "unaligned" and act.duty > 0 and bg_wake > t + eps:
                cand.append(bg_wake)
            tn = min(cand)
            dt = max(tn - t, 0.0)
            if dt > 0:
                if fg_on and bg_run:
                    pw = 0.5 * (P.fg_power_w(eff) + P.bg_power_w(eff))
                elif fg_on:
                    pw = P.fg_power_w(eff)
                elif bg_run:
                    pw = P.bg_power_w(eff)
                else:
                    pw = P.p_idle_w
                energy += pw * dt * 1e-3
                if fg_on:
                    prog += dt * share / fgd
                if bg_run:
                    bg_prog += dt * share / bgd
            t = tn
            # ---- events at t
            if fg_on and prog >= 1 - 1e-9:
                i = q.popleft(); prog = 0.0
                lat[i] = t - arr[i]
                tick_lat.append(lat[i])
                if lat[i] > fg.deadline_ms:
                    tick_missed += 1
            if bg_run and bg_prog >= 1 - 1e-9:
                bg_run, bg_prog = False, 0.0
                tok_t.append(t); tick_tok += 1
                bg_wake = t + ((t - bg_t0) * (1.0 / act.duty - 1.0) if 0 < act.duty < 1 else 0.0)     # gap from the MEASURED token time, as the A2 DLL (w2_kernels.cu bg_loop)
            while ai < n and arr[ai] <= t + eps:
                q.append(ai); ai += 1; tick_arr += 1
            if pending is not None and pending[0] <= t + eps:
                applied = pending[1]; pending = None
            if t >= next_tick - eps:
                dtk = t - tick_t0
                obs = Obs(t_ms=t, lat_ms=np.array(tick_lat), n_missed=tick_missed, n_arrived=tick_arr, tokens=tick_tok,
                          power_w=(energy - tick_e0) / (dtk * 1e-3) if dtk > 0 else 0.0, clock_mhz=eff, period_ms=fg.period_ms, deadline_ms=fg.deadline_ms)
                tick_lat, tick_missed, tick_arr, tick_tok, tick_e0, tick_t0 = [], 0, 0, 0, energy, t
                tick_t_list.append(t); tick_e_list.append(energy)
                act = policy.act(obs)
                actions.append((t, act))
                if act.pacing == "aligned" and fg.arrivals != "periodic":
                    raise ValueError("aligned pacing needs a periodic fg")
                if float(act.clock) != target:
                    if pending is None and t - last_req >= sc.clock_min_interval_ms - eps:
                        pending = (t + P.clock_latency_ms, float(act.clock)); target = float(act.clock); last_req = t; n_changes += 1
                    else:
                        n_limited += 1
                next_tick += TICK_MS
        if tick_t_list[-1] < T - eps:
            tick_t_list.append(T); tick_e_list.append(energy)
        return Result(arr_ms=arr, lat_ms=lat, tok_t_ms=np.array(tok_t), energy_j=energy, clock_log=clock_log, n_clock_changes=n_changes, n_rate_limited=n_limited,
                      duration_ms=T, warmup_ms=sc.warmup_ms, deadline_ms=fg.deadline_ms, tick_t=np.array(tick_t_list), tick_e=np.array(tick_e_list), actions=actions)


def summarise(r, warmup_ms=None):
    w0 = r.warmup_ms if warmup_ms is None else warmup_ms
    win = (r.duration_ms - w0) * 1e-3
    sel = (r.arr_ms >= w0) & (~np.isnan(r.lat_ms) | (r.arr_ms + r.deadline_ms <= r.duration_ms + 1e-9))     # an unfinished frame counts only once its deadline has passed
    lat = r.lat_ms[sel]
    done = ~np.isnan(lat)
    miss = (~done) | (lat > r.deadline_ms)
    e_win = r.energy_j - float(np.interp(w0, r.tick_t, r.tick_e))
    tok = int(((r.tok_t_ms >= w0)).sum())
    return dict(n_frames=int(sel.sum()), miss_frac=float(miss.mean()) if len(lat) else 0.0, frac_completed=float(done.mean()) if len(lat) else 1.0,
                lat_mean_ms=float(lat[done].mean()) if done.any() else float("nan"), lat_p50_ms=float(np.percentile(lat[done], 50)) if done.any() else float("nan"),
                lat_p99_ms=float(np.percentile(lat[done], 99)) if done.any() else float("nan"), bg_tok_s=tok / win if win > 0 else 0.0,
                power_w=e_win / win if win > 0 else 0.0, j_per_token=(e_win / tok) if tok else float("inf"), clock_changes=r.n_clock_changes)
