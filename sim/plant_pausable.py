"""Pausable-decode variant of the plant (v2 sprint 1, docs/V2_SPRINT1_PAUSE_COST.md). SIMULATION ONLY.
Generated from sim/plant.py (left untouched) by replacing four pieces of Plant.run: (1) the bg start rule, (2) the bg duration, (3) the completion event, (4) the new group state. A bg token is G
groups of layers; each group takes its measured share of the token time (fracs, summing to 1) plus the measured cost of the pause point after it (boundary_ms, not after the last group). In aligned
pacing a group starts only while no fg frame is queued and the GROUP (not the whole token) is expected to end guard_ms before the next arrival; between the groups of one token the duty gap does not
apply (it is applied once after the whole token, from the token's running time). The controller sees the token's running time, not its wall time, so waits between groups do not look like a slower token. With fracs = (1.0,) and boundary_ms = 0 the result is identical to Plant (tests/test_plant_pausable.py). Token-time jitter is not modelled here."""
from collections import deque

import numpy as np

from sim.pacing import aligned_may_start, unaligned_wake
from sim.plant import TICK_MS, Obs, Plant, Result, _Static


class PausablePlant(Plant):
    def __init__(self, params, scenario, seed=0, fracs=(1.0,), boundary_ms=0.0):
        super().__init__(params, scenario, seed)
        assert abs(sum(fracs) - 1.0) < 1e-6, "group fractions must sum to 1"
        self.fracs, self.boundary_ms = tuple(float(f) for f in fracs), float(boundary_ms)
        assert scenario.bg is None or not scenario.bg.jitter, "token jitter is not modelled in the pausable plant"

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
        bg_f = 1.0
        bg_na = float("inf")
        bg_g = 0                                      # index of the next group of the token in progress (0 = no token open)
        bg_run_ms = 0.0                               # time the token spent RUNNING (waits between groups excluded): the token time the controller sees and the base of the duty gap
        G = len(self.fracs)
        tick_over = []
        jit = P.token_jitter if (bg is not None and bg.jitter) else None
        bg_wake = 0.0
        tok_t = []
        energy = 0.0
        next_tick = TICK_MS
        tick_lat, tick_missed, tick_arr, tick_tok, tick_e0, tick_t0 = [], 0, 0, 0, 0.0, 0.0
        tick_tokms = []
        tick_t_list, tick_e_list, actions = [0.0], [0.0], []
        eps = 1e-9

        def cap_at(tt):
            c = float("inf")
            for ct, cv in caps:
                if ct <= tt + eps:
                    c = cv
            return c

        def bgdur(clock):
            return (1000.0 / P.tok_s(clock, bg.profile)) if bg.kind == "llama" else bg.slice_ms * P.fg_ratio(clock)

        def grp_ms(clock, g):
            # duration of group g at this clock: its measured share of the token time, plus the measured cost of the pause point after it (not after the last group)
            return bgdur(clock) * self.fracs[g] + (self.boundary_ms if g < G - 1 else 0.0)

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
                gd_try = grp_ms(eff, bg_g)
                open_tok = bg_g > 0                                 # a token in progress may continue without the duty gap: the gap is applied once, after the whole token
                if act.pacing == "aligned":
                    ok = act.duty > 0 and (open_tok or t >= bg_wake - eps) and aligned_may_start(t, bool(q), gd_try, act.guard_ms, next_arrival(t))
                else:
                    ok = act.duty > 0 and (open_tok or t >= bg_wake - eps)
                if ok:
                    bg_run, bg_prog, bg_na = True, 0.0, next_arrival(t)
                    if bg_g == 0:
                        bg_t0 = t
            fg_on = bool(q)
            share = 1.0 / (S * (1.0 + sc.interaction * (1800.0 / eff - 1.0))) if (fg_on and bg_run) else 1.0
            fgd = w[q[0]] * P.fg_ratio(eff) if fg_on else 0.0
            bgd = grp_ms(eff, bg_g) if bg_run else 0.0
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
            elif bg is not None and act.duty > 0 and bg_wake > t + eps:
                cand.append(bg_wake)
            tn = min(cand)
            dt = max(tn - t, 0.0)
            if dt > 0:
                if fg_on and bg_run:
                    pw = 0.5 * (P.fg_power_w(eff) + P.bg_power_w(eff, bg.profile))
                elif fg_on:
                    pw = P.fg_power_w(eff)
                elif bg_run:
                    pw = P.bg_power_w(eff, bg.profile)
                else:
                    pw = P.p_idle_w
                energy += pw * dt * 1e-3
                if fg_on:
                    prog += dt * share / fgd
                if bg_run:
                    bg_prog += dt * share / bgd
                    bg_run_ms += dt
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
                bg_g += 1
                if bg_g == G:                                       # the last group finished: the token is complete
                    bg_g = 0
                    tok_t.append(t); tick_tok += 1; tick_tokms.append(bg_run_ms); tick_over.append(max(0.0, t - bg_na) if bg_na != float("inf") else 0.0)
                    bg_wake = unaligned_wake(t - bg_run_ms, t, act.duty) if act.duty > 0 else t
                    bg_run_ms = 0.0
            while ai < n and arr[ai] <= t + eps:
                q.append(ai); ai += 1; tick_arr += 1
            if pending is not None and pending[0] <= t + eps:
                applied = pending[1]; pending = None
            if t >= next_tick - eps:
                dtk = t - tick_t0
                obs = Obs(t_ms=t, lat_ms=np.array(tick_lat), n_missed=tick_missed, n_arrived=tick_arr, tokens=tick_tok,
                          power_w=(energy - tick_e0) / (dtk * 1e-3) if dtk > 0 else 0.0, clock_mhz=eff, period_ms=fg.period_ms, deadline_ms=fg.deadline_ms, tok_ms=np.array(tick_tokms), overrun_ms=np.array(tick_over))
                tick_lat, tick_missed, tick_arr, tick_tok, tick_e0, tick_t0 = [], 0, 0, 0, energy, t
                tick_tokms, tick_over = [], []
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
