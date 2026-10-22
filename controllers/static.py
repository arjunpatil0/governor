"""(b) Best static setting: a fixed Action chosen offline by a grid search on tuning seeds.
Two objectives: the frozen lambda objective (bg tok/s - 0.5 W, SLO-feasible) and, since 2026-10-22, the PRIMARY one: maximise bg tok/s subject to the SLO AND a mean-GPU-power budget
(power_budget_w; feasible = the budget holds on every tuning seed). In budget mode the aligned grid also searches the duty throttle."""
import numpy as np

from controllers.common import ALLOWED_CLOCKS, IdleDetector, knee_clock
from sim.plant import Action, Plant, summarise
from sim.scenarios import build

LAMBDA = 0.5                                  # objective: bg tok/s - LAMBDA * GPU power (W), docs/W45_SIM_PROTOCOL.md
DUTIES = (0.05, 0.1, 0.15, 0.2, 0.25, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0)
GUARDS = (0.0, 0.5, 1.0, 1.5, 2.0, 3.0, 4.0)
BUDGET_DUTIES = (0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0)
BUDGET_GUARDS = (0.0, 0.5)


class StaticController:
    def __init__(self, action, name="b"):
        self.a, self.name = action, name

    def reset(self, ctx=None):
        return self.a

    def act(self, obs):
        return self.a


def _grid(pacing, budget):
    if pacing == "unaligned":
        return [dict(duty=d) for d in DUTIES]
    if budget is None:
        return [dict(guard_ms=g) for g in GUARDS]
    return [dict(guard_ms=g, duty=d) for g in BUDGET_GUARDS for d in BUDGET_DUTIES]


def _search(P, scs, pacing, seeds, miss_max, clocks, power_budget_w):
    best = least = None
    for clk in (clocks or ALLOWED_CLOCKS(P)):
        for kn in _grid(pacing, power_budget_w):
            a = Action(clock=clk, pacing=pacing, **kn)
            miss = pmax = 0.0
            toks, pws = [], []
            for sc in scs:
                ss = [summarise(Plant(P, sc, seed=s).run(a)) for s in seeds]
                miss = max(miss, max(x["miss_frac"] for x in ss)); pmax = max(pmax, max(x["power_w"] for x in ss))
                toks.append(np.mean([x["bg_tok_s"] for x in ss])); pws.append(np.mean([x["power_w"] for x in ss]))
            tok, pw = float(np.mean(toks)), float(np.mean(pws))
            obj = tok - 1e-3 * pw if power_budget_w is not None else tok - LAMBDA * pw
            row = dict(action=a, tok_s=tok, power_w=pw, power_max_seen=pmax, miss_max_seen=miss, objective=obj)
            ok = miss <= miss_max and (power_budget_w is None or pmax <= power_budget_w)
            if ok and (best is None or obj > best["objective"]):
                best = row
            key = (max(miss, 0.0), max(0.0, pmax - (power_budget_w or 1e9)))
            if least is None or key < least["_key"]:
                least = dict(row, _key=key)
    if best:
        return dict(best, feasible=True)
    least.pop("_key")
    return dict(least, feasible=False)


def tune_static(P, scenario, pacing, seeds, duration_ms=None, miss_max=0.01, clocks=None, jitter=False, power_budget_w=None):
    """Grid search over (clock x duty) [unaligned] or (clock x guard [x duty throttle in budget mode]) [aligned]. Feasible = miss fraction <= miss_max on EVERY tuning seed
    (and mean power <= power_budget_w on every seed when a budget is given). If nothing is feasible the least-violating setting is returned with feasible False."""
    sc = build(scenario, jitter=jitter) if duration_ms is None else build(scenario, duration_ms, jitter=jitter)
    return _search(P, [sc], pacing, seeds, miss_max, clocks, power_budget_w)


def tune_static_global(P, pacing, seeds, scenarios, duration_ms=None, miss_max=0.01, clocks=None, jitter=False, power_budget_w=None):
    """One scenario-agnostic setting: feasible iff the SLO (and the budget) hold on every tuning seed in EVERY listed scenario; objective = mean over scenarios."""
    scs = [build(s, jitter=jitter) if duration_ms is None else build(s, duration_ms, jitter=jitter) for s in scenarios]
    return _search(P, scs, pacing, seeds, miss_max, clocks, power_budget_w)


class IdleDropController:
    """The simplest dynamic design: one fixed Action while the fg runs, knee clock with a free background when no frames arrive (5 ticks), fixed Action again at once."""
    name = "e"

    def __init__(self, P, action):
        self.P, self.a = P, action

    def reset(self, ctx=None):
        self.idle = IdleDetector()
        return self.a

    def act(self, obs):
        if self.idle.update(obs):
            return Action(clock=float(knee_clock(self.P)), pacing=self.a.pacing, duty=1.0, guard_ms=0.0)
        return self.a
