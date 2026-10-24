"""(c) PI on the foreground frame-time error with a deadline-aware clock rule; (c-prime) the same loop on the aligned-pacing guard.

Pacing loop, every tick (100 ms): error e = (target x deadline - q95 of recent frame latency) / deadline.
 unaligned: duty += kp (e - e_prev) + ki e (velocity form, clamped to [dmin, 1]); a missed frame halves the duty.
 aligned:   the guard follows the same error with opposite sign (late frames -> more guard, slow relaxation down to gmin); a missed frame adds 1 ms.
Clock rule, every clock_every ticks (1 s; the clock actuator takes ~443 ms and is rate-limited): estimate the alone frame cost at 1800 MHz from the low
quantile (unaligned) / median (aligned) of recent latencies and pick the LOWEST allowed clock whose predicted frame time fits clock_margin x deadline
(aligned: and a bg token still fits before the next frame). Hysteresis on downward moves. fg idle (no arrivals) -> knee clock, bg free."""
from collections import deque

import numpy as np

from controllers.common import ALLOWED_CLOCKS, IdleDetector, Window, knee_clock
from sim.plant import Action


class PIController:
    def __init__(self, P, pacing="unaligned", kp=0.5, ki=0.15, target=0.8, clock_margin=0.6, hyst=0.05, duty0=0.2, dmin=0.02, guard0=1.0,
                 gmin=0.5, gmax=8.0, clock_every=10, win=5, fit_hyst_ms=0.3, power_budget_w=None, power_gain=0.03):
        self.P, self.pacing = P, pacing
        self.kp, self.ki, self.target, self.clock_margin, self.hyst = kp, ki, target, clock_margin, hyst
        self.duty0, self.dmin, self.guard0, self.gmin, self.gmax = duty0, dmin, guard0, gmin, gmax
        self.clock_every, self.win, self.fit_hyst_ms = clock_every, win, fit_hyst_ms
        self.power_budget_w, self.power_gain = power_budget_w, power_gain      # aligned only: a PI loop on mean GPU power throttles the token rate (duty gap) to meet the budget
        self.name = "c" if pacing == "unaligned" else "c'"

    def reset(self, ctx):
        self.period, self.deadline = ctx["period_ms"], ctx["deadline_ms"]
        self.duty, self.guard, self.e_prev, self.tick = self.duty0, self.guard0, 0.0, 0
        self.clock = float(self.P.UNLOCKED_MHZ)
        self.w5, self.w20, self.idle = Window(self.win), Window(20), IdleDetector()
        self.pduty, self.pw = 1.0, deque(maxlen=10)
        return self._action()

    def _action(self, idle=False):
        if self.pacing == "unaligned":
            return Action(clock=self.clock, pacing="unaligned", duty=1.0 if idle else self.duty)
        return Action(clock=self.clock, pacing="aligned", duty=self.pduty, guard_ms=self.guard)

    def act(self, obs):
        self.tick += 1
        self.w5.add(obs.lat_ms); self.w20.add(obs.lat_ms)
        if self.power_budget_w is not None and self.pacing == "aligned":
            self.pw.append(obs.power_w)
            if len(self.pw) >= 5:
                e_p = (0.97 * self.power_budget_w - float(np.mean(self.pw))) / self.power_budget_w
                self.pduty = float(np.clip(self.pduty + self.power_gain * e_p, 0.05, 1.0))
        if self.idle.update(obs):
            self.clock = float(knee_clock(self.P))
            return self._action(idle=True)
        q95 = self.w5.q(95)
        e = 0.0 if np.isnan(q95) else (self.target * self.deadline - q95) / self.deadline
        if obs.n_missed > 0:
            self.duty *= 0.5
            self.guard += 1.0
        else:
            step = self.kp * (e - self.e_prev) + self.ki * e
            self.duty += step
            self.guard -= 10.0 * (step if e < 0 else 0.3 * self.ki * e)      # late -> grow fast; early -> relax slowly
        self.e_prev = e
        self.duty = float(np.clip(self.duty, self.dmin, 1.0)); self.guard = float(np.clip(self.guard, self.gmin, self.gmax))
        if self.tick % self.clock_every == 0:
            self._update_clock(obs)
        return self._action()

    def _update_clock(self, obs):
        P = self.P
        x = self.w20.q(10) if self.pacing == "unaligned" else self.w20.q(50)
        if np.isnan(x):
            return
        cest = x / P.fg_ratio(obs.clock_mhz)
        clocks = ALLOWED_CLOCKS(P)
        for f in clocks:
            frame = cest * P.fg_ratio(f)
            down = f < self.clock
            if self.pacing == "unaligned":
                ok = frame <= (self.clock_margin - (self.hyst if down else 0.0)) * self.deadline
            else:
                ok = frame + 1000.0 / P.tok_s(f) + self.guard <= self.period - (self.fit_hyst_ms if down else 0.0)
            if ok:
                self.clock = float(f)
                return
        if self.pacing == "aligned":            # no clock lets a token fit: save power at the lowest clock that still meets the margin (bg starves anyway)
            for f in clocks:
                if cest * P.fg_ratio(f) <= self.clock_margin * self.deadline:
                    self.clock = float(f)
                    return
        self.clock = float(clocks[-1])


class SwitchingPIController:
    """(c'B) The PI controller with a within-cell pacing-mode switch by a simple NON-learned rule (reviewer + Arjun 2026-10-23, fairness against d'B, plan addendum O-2): unaligned when the recent
    measured frame time exceeds threshold + hyst_ms, aligned when it falls below threshold - hyst_ms (threshold = period - the clean token duration: 6.57 ms for the 3B, 12.2 ms for the 1B, never for the 8B; plan addendum O-3), and never
    sooner than dwell_ticks (50 ticks = 5 s) after the last switch. The frame time is the median of the last window_frames (30) frame latencies while aligned (the frames run alone) and their 10th
    percentile while unaligned (the low quantile is the frame alone; contended frames are longer), the same estimators PIController uses. Two PIController instances share one clock; only the
    executed one sees observations; the incoming one keeps its last duty / guard and gets fresh latency windows. Not learned: no model, no prediction."""
    name = "c'"

    def __init__(self, P, power_budget_w=None, threshold_ms=None, hyst_ms=0.3, dwell_ticks=50, window_frames=30, token_window=20, **pi_kw):
        """threshold_ms None (default) = TOKEN-AWARE (plan addendum O-3): period - the clean token duration (6.57 ms for the 3B); a number fixes it (tests, ablations)."""
        self.P, self.threshold_ms, self.hyst_ms, self.dwell_ticks, self.window_frames, self.token_window = P, threshold_ms, hyst_ms, int(dwell_ticks), int(window_frames), int(token_window)
        self.al = PIController(P, "aligned", power_budget_w=power_budget_w, **pi_kw)
        self.un = PIController(P, "unaligned", **pi_kw)

    def reset(self, ctx):
        self.un.reset(ctx)
        a = self.al.reset(ctx)
        self.mode, self.tick, self.tick_of_switch = "aligned", 0, 0
        self.frames = deque(maxlen=self.window_frames)
        self.tok_clean = deque(maxlen=self.token_window)       # token durations seen while aligned (tokens run in the slack, alone) or before any frame: the clean estimate
        self.period = float(ctx["period_ms"])
        return a

    def clean_token_ms(self):
        """Median of the recent clean token durations, scaled to the clock the controller is COMMANDING now (token time ~ 1 / tok_s(clock), the L table shape: a lower clock lengthens the token and
        shrinks the aligned slack, reviewer 2026-10-24 finding 3); each duration is stored normalised to 1800 MHz at the clock it was observed at. Before any token: the L-table prior at the current clock."""
        f_now = self.P.clamp_clock(self.clock)
        if len(self.tok_clean):
            return float(np.median(np.fromiter(self.tok_clean, float))) * self.P.tok_s(1800.0) / self.P.tok_s(f_now)
        return 1000.0 / self.P.tok_s(f_now)

    def threshold(self):
        """The frame time above which a clean token no longer fits the period: fixed threshold_ms if given, else period - the clean token estimate (never below 0)."""
        return float(self.threshold_ms) if self.threshold_ms is not None else max(0.0, self.period - self.clean_token_ms())

    @property
    def clock(self):
        return (self.al if self.mode == "aligned" else self.un).clock

    def _adopt(self, ctrl, clock):
        ctrl.clock = float(clock)
        ctrl.w5, ctrl.w20, ctrl.idle = Window(ctrl.win), Window(20), IdleDetector()
        ctrl.e_prev = 0.0
        ctrl.pw.clear()

    def act(self, obs):
        self.tick += 1
        for x in np.asarray(obs.lat_ms, float).ravel():
            self.frames.append(float(x))
        if obs.tok_ms is not None and len(obs.tok_ms) and (self.mode == "aligned" or len(obs.lat_ms) == 0):
            k = self.P.tok_s(self.P.clamp_clock(obs.clock_mhz)) / self.P.tok_s(1800.0)         # normalise to 1800 MHz: duration x tok_s(observed clock) / tok_s(1800)
            self.tok_clean.extend(float(x) * k for x in np.asarray(obs.tok_ms, float).ravel())
        cur = self.al if self.mode == "aligned" else self.un
        a = cur.act(obs)
        if len(obs.lat_ms) and len(self.frames) >= self.window_frames and self.tick - self.tick_of_switch >= self.dwell_ticks:
            lat = np.fromiter(self.frames, float)
            est = float(np.median(lat)) if self.mode == "aligned" else float(np.percentile(lat, 10))
            to = None
            thr = self.threshold()
            if self.mode == "aligned" and est > thr + self.hyst_ms:
                to = "unaligned"
            elif self.mode == "unaligned" and est < thr - self.hyst_ms:
                to = "aligned"
            if to is not None:
                self.mode, self.tick_of_switch = to, self.tick
                self.frames.clear()
                self._adopt(self.al if to == "aligned" else self.un, a.clock)
        self.al.clock = self.un.clock = float(a.clock)
        return a
