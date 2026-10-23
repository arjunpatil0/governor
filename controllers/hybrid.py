"""(d'B) Hybrid controller (docs/W45_PLAN.md addendum F, 2026-10-22; experiments/w5_governor.yaml d'B; action-space fix: plan addendum O-1, 2026-10-23).
Idle branch = the eB rule (controllers/static.py IdleDropController): after IDLE_TICKS ticks without frame arrivals the clock drops to the knee with a free background (duty 1, guard 0).
Active branch = the learned ModelController in the SAME action space as every other controller: clock x {aligned guard/duty, unaligned duty}. Two instances watch every observation:
  self.model     aligned  (v2 + v3: token-time model, learned guard from the observed token-end overrun, power budget);
  self.model_un  unaligned (duty pacing, interference model, power budget).
The executed mode is chosen on the slow loop (every SWITCH_EVERY ticks) by the predicted token rate of the two plans, with hysteresis (the other mode must predict MORE_FACTOR x + MORE_ABS tok/s
for SWITCH_HOLD consecutive checks). Why: when the measured frame time leaves no slack for a token (trial 2026-10-23: c0m 6.68 ms, token 10.1 ms) aligned pacing delivers 0 tok/s.
Cross-contamination is cut: the instance that is not executed never learns from its own unexecuted plan (its previous-plan memory is cleared every tick); while unaligned is executed the aligned
instance gets NO token durations or overruns (they are dilated by overlap) and the alone-frame estimate of the unaligned instance instead of the contended latencies.
The learned model never sees the idle phase: its power scale / bias / duty offset / guard keep the values learned during active play, and the first active tick after an idle phase skips the
power calibration against the stale pre-idle plan."""
import dataclasses

import numpy as np

from controllers.common import IdleDetector, knee_clock
from controllers.model import ModelController
from sim.plant import Action

SWITCH_EVERY, SWITCH_HOLD = 10, 2          # slow-loop checks (1 s) and consecutive checks before the pacing mode changes
MORE_FACTOR, MORE_ABS = 1.2, 2.0           # the other mode must predict this much more (tok/s) to win


class HybridController:
    name = "d'B"

    def __init__(self, P, power_budget_w, **model_kw):
        self.P = P
        self.model = ModelController(P, "aligned", v2=True, v3=True, power_budget_w=float(power_budget_w), **model_kw)
        self.model_un = ModelController(P, "unaligned", power_budget_w=float(power_budget_w), **model_kw)

    def reset(self, ctx):
        self.idle, self._was_idle = IdleDetector(), False
        self.mode, self._votes, self._tick = "aligned", 0, 0
        self.model_un.reset(ctx)
        return self.model.reset(ctx)

    @staticmethod
    def _forget_plan(m):
        m._prev_power, m._prev_bg, m._prev_pred = None, 0.0, None

    def act(self, obs):
        if self.idle.update(obs):
            self._was_idle = True
            return Action(clock=float(knee_clock(self.P)), pacing="aligned", duty=1.0, guard_ms=0.0)
        if self._was_idle:                                                  # hand-over: the plans made before the idle phase are stale
            self._was_idle = False
            self._forget_plan(self.model); self._forget_plan(self.model_un)
        self._tick += 1
        obs_al = obs
        if self.mode == "unaligned" and self.model_un.c_hat is not None and len(obs.lat_ms):
            alone = self.model_un.c_hat * self.P.fg_ratio(obs.clock_mhz)          # contended latencies and dilated token durations would mislead the aligned instance
            obs_al = dataclasses.replace(obs, lat_ms=np.full(len(obs.lat_ms), alone), tok_ms=None, overrun_ms=None)
        a_al, a_un = self.model.act(obs_al), self.model_un.act(obs)
        if self._tick % SWITCH_EVERY == 0:
            t_al, t_un = float(self.model.plan.get("pred_tok", 0.0)), float(self.model_un.plan.get("pred_tok", 0.0))
            cur, other = (t_al, t_un) if self.mode == "aligned" else (t_un, t_al)
            if other > MORE_FACTOR * cur + MORE_ABS:
                self._votes += 1
                if self._votes >= SWITCH_HOLD:
                    self.mode, self._votes = ("unaligned" if self.mode == "aligned" else "aligned"), 0
            else:
                self._votes = 0
        a = a_al if self.mode == "aligned" else a_un
        for m in (self.model, self.model_un):                              # one clock state; the instance that was not executed forgets its plan
            m.clock = float(a.clock)
        self._forget_plan(self.model_un if self.mode == "aligned" else self.model)
        return a
