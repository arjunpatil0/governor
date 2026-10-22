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
