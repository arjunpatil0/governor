"""(d) / (d-prime) Model-based controller: an online-calibrated per-workload predictor plus a constrained choice of (clock, duty|guard) each step.

Structure (priors from committed results, not from the simulator code): fg frame time = c_hat x ratio(clock) (W1/B clock law); bg token time and power from
the L table; time-weighted power with W1 fma power for the fg; unaligned interference multiplier M(duty) from the A2 SA4 p99 ratios (fg 4 ms table).
Calibrated online: c_hat (fg cost at 1800 MHz, EWMA of a low quantile / median of observed latency / clock ratio), sigma_hat (relative frame jitter, aligned mode),
gamma (multiplicative correction of the interference prediction, log-EWMA of observed q95 / predicted q95).
Decision: maximise  bg tok/s - lam x power  subject to predicted q95 frame time <= safety x deadline; aligned mode also fixes the guard from sigma_hat and
releases n = floor((period - alone - guard) / token time) tokens per frame. No feasible point -> fastest clock and minimum duty / no tokens.
Clock changes are issued every clock_every ticks and only if the objective gain exceeds switch_gain (actuator latency and rate limit)."""
import numpy as np

from controllers.common import ALLOWED_CLOCKS, IdleDetector, Window, knee_clock
from sim.plant import Action

DUTIES = tuple(np.round(np.arange(0.02, 1.001, 0.02), 2))
A_DUTIES = tuple(np.round(np.arange(0.1, 1.001, 0.1), 2))        # aligned-mode throttle grid (only with a power budget)


class ModelController:
    def __init__(self, P, pacing="unaligned", lam=0.5, safety=0.9, alpha=0.2, gamma_alpha=0.1, sigma0=0.03, clock_every=10, switch_gain=0.5, win=5, power_budget_w=None):
        self.P, self.pacing, self.lam, self.safety = P, pacing, lam, safety
        self.power_budget_w = power_budget_w
        self.alpha, self.gamma_alpha, self.sigma0, self.clock_every, self.switch_gain, self.win = alpha, gamma_alpha, sigma0, clock_every, switch_gain, win
        self.name = "d" if pacing == "unaligned" else "d'"
        base = P.sa4["sa4_fg4_alone"]["lat_p99_ms"]
        pts = [(0.0, 1.0)] + sorted((r["duty"] if r["duty"] > 0 else 1.0, r["lat_p99_ms"] / base) for k, r in P.sa4.items() if r["fg_ms"] == 4.0 and r["duty"] > 0 or k == "sa4_fg4_m2")
        self._M = sorted(dict(pts).items())

    def M(self, d):
        xs, ys = zip(*self._M)
        return float(np.interp(d, xs, ys))

    def reset(self, ctx):
        self.period, self.deadline = ctx["period_ms"], ctx["deadline_ms"]
        self.c_hat, self.sigma, self.gamma, self.tick, self.extra = None, self.sigma0, 1.0, 0, 0.0
        self.clock = float(self.P.UNLOCKED_MHZ)
        self.w5, self.idle = Window(self.win), IdleDetector()
        self.plan = {}
        self._prev_pred = None
        self.pbias, self._prev_power = 0.0, None
        return Action(clock=self.clock, pacing=self.pacing, duty=0.2, guard_ms=1.0)

    # ---- calibration
    def _calibrate(self, obs):
        P = self.P
        lat = obs.lat_ms
        self.w5.add(lat)
        if len(lat) == 0:
            return
        w = self.w5.lat()
        x = (np.percentile(w, 10) if self.pacing == "unaligned" else np.median(w)) / P.fg_ratio(obs.clock_mhz)
        self.c_hat = x if self.c_hat is None else self.c_hat + self.alpha * (x - self.c_hat)
        if self.pacing == "aligned" and len(w) >= 6:
            self.sigma = float(np.clip(0.7 * self.sigma + 0.3 * (np.std(w) / np.mean(w)), 0.02, 0.3))
        if self.pacing == "unaligned" and self._prev_pred and len(lat) >= 3:
            r = float(np.percentile(lat, 95)) / self._prev_pred
            self.gamma = float(np.clip(self.gamma * r ** self.gamma_alpha, 0.3, 6.0))
        if self.power_budget_w is not None and self._prev_power is not None and obs.power_w > 0:
            self.pbias += 0.05 * ((obs.power_w - self._prev_power) - self.pbias)         # observed minus planned GPU power, EWMA
        if obs.n_missed > 0:
            self.extra = min(self.extra + 1.0, 6.0)
        else:
            self.extra = max(self.extra - 0.1, 0.0)

    # ---- prediction and decision
    def _power(self, f, u, bg_busy):
        P = self.P
        return u * P.fg_power_w(f) + bg_busy * P.bg_power_w(f) + max(0.0, 1.0 - u - bg_busy) * P.p_idle_w

    def _candidates(self, clocks):
        P = self.P
        for f in clocks:
            alone = self.c_hat * P.fg_ratio(f)
            u = alone / self.period
            tok_ms = 1000.0 / P.tok_s(f)
            if self.pacing == "unaligned":
                for d in DUTIES:
                    q95 = alone * (1 + 1.64 * self.sigma) * self.M(d) * self.gamma
                    tok = d * P.tok_s(f) * max(0.0, 1.0 - u)
                    yield f, dict(clock=f, duty=float(d), guard_ms=0.0, n_tok=0, pred_q95_ms=q95, pred_tok=tok, pred_power=self._power(f, u, tok * tok_ms / 1000.0))
            else:
                guard = max(0.3, 3.0 * self.sigma * alone + 0.2) + self.extra
                n = max(0, int(np.floor((self.period - alone - guard) / tok_ms)))
                q95 = alone * (1 + 1.64 * self.sigma)
                for d in (A_DUTIES if self.power_budget_w is not None else (1.0,)):
                    n_eff = min(n, d * self.period / tok_ms) if self.power_budget_w is not None else n         # duty gap limits the tokens per frame
                    tok = n_eff * 1000.0 / self.period
                    yield f, dict(clock=f, duty=float(d), guard_ms=float(guard), n_tok=n, pred_q95_ms=q95, pred_tok=tok, pred_power=self._power(f, u, n_eff * tok_ms / self.period))

    def _decide(self, search_all):
        P = self.P
        clocks = ALLOWED_CLOCKS(P) if search_all else (self.clock,)
        best = best_cur = None
        for f, c in self._candidates(clocks):
            if c["pred_q95_ms"] > self.safety * self.deadline:
                continue
            if self.power_budget_w is not None and c["pred_power"] + self.pbias > self.power_budget_w:
                continue
            c["objective"] = c["pred_tok"] - (1e-3 if self.power_budget_w is not None else self.lam) * c["pred_power"]       # budget mode: maximise tokens, power only breaks ties
            if best is None or c["objective"] > best["objective"] + 1e-9:
                best = c
            if f == self.clock and (best_cur is None or c["objective"] > best_cur["objective"]):
                best_cur = c
        if best is not None and best["clock"] != self.clock and best_cur is not None and best["objective"] - best_cur["objective"] < self.switch_gain:
            best = best_cur
        if best is None:                                     # nothing meets the bound: fastest clock, least interference
            f = ALLOWED_CLOCKS(P)[-1]
            alone = self.c_hat * P.fg_ratio(f)
            best = dict(clock=f, duty=DUTIES[0], guard_ms=max(0.3, 3.0 * self.sigma * alone + 0.2) + self.extra, n_tok=0,
                        pred_q95_ms=alone * (1 + 1.64 * self.sigma) * (self.M(DUTIES[0]) * self.gamma if self.pacing == "unaligned" else 1.0), pred_tok=0.0,
                        pred_power=self._power(f, alone / self.period, 0.0), objective=float("-inf"))
        return best

    def act(self, obs):
        self.tick += 1
        self._calibrate(obs)
        if self.idle.update(obs):
            self.clock = float(knee_clock(self.P))
            self.plan = dict(clock=self.clock, duty=1.0, guard_ms=0.0, n_tok=0, pred_q95_ms=0.0, pred_tok=0.0, pred_power=0.0, idle=True)
            self._prev_pred = None
            return Action(clock=self.clock, pacing=self.pacing, duty=1.0, guard_ms=0.0)
        if self.c_hat is None:
            return Action(clock=self.clock, pacing=self.pacing, duty=0.2, guard_ms=1.0)
        best = self._decide(search_all=(self.tick % self.clock_every == 0))
        self.clock = float(best["clock"])
        self.plan = best
        self._prev_power = best["pred_power"]
        self._prev_pred = best["pred_q95_ms"] if self.pacing == "unaligned" else None
        return Action(clock=self.clock, pacing=self.pacing, duty=best["duty"], guard_ms=best["guard_ms"])
