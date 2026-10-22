"""(d'B) Hybrid controller (docs/W45_PLAN.md addendum F, 2026-10-22; experiments/w5_governor.yaml d'B).
Idle branch = the eB rule (controllers/static.py IdleDropController): after IDLE_TICKS ticks without frame arrivals the clock drops to the knee with a free background (duty 1, guard 0).
Active branch = the learned ModelController (v2 + v3: token-time model, learned guard from the observed token-end overrun, power budget). The learned model never sees the idle phase:
its power scale / bias / duty offset / guard keep the values learned during active play, and the first active tick after an idle phase skips the power calibration against the
stale pre-idle plan. Reason: simulator round 3 showed the model's idle plan (with a drifting background power scale) was the only place it lost; a rule already handles idle."""
from controllers.common import IdleDetector, knee_clock
from controllers.model import ModelController
from sim.plant import Action


class HybridController:
    name = "d'B"

    def __init__(self, P, power_budget_w, **model_kw):
        self.P = P
        self.model = ModelController(P, "aligned", v2=True, v3=True, power_budget_w=float(power_budget_w), **model_kw)

    def reset(self, ctx):
        self.idle, self._was_idle = IdleDetector(), False
        return self.model.reset(ctx)

    def act(self, obs):
        if self.idle.update(obs):
            self._was_idle = True
            return Action(clock=float(knee_clock(self.P)), pacing="aligned", duty=1.0, guard_ms=0.0)
        if self._was_idle:                                                  # hand-over: the plan the model made before the idle phase is stale
            self._was_idle = False
            self.model._prev_power, self.model._prev_bg, self.model._prev_pred = None, 0.0, None
        return self.model.act(obs)
