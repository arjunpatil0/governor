"""(b) Best static setting: a fixed Action chosen offline by a grid search on tuning seeds."""
import numpy as np

from controllers.common import ALLOWED_CLOCKS
from sim.plant import Action, Plant, summarise
from sim.scenarios import build

LAMBDA = 0.5                                  # objective: bg tok/s - LAMBDA * GPU power (W), docs/W45_SIM_PROTOCOL.md
DUTIES = (0.05, 0.1, 0.15, 0.2, 0.25, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0)
GUARDS = (0.0, 0.5, 1.0, 1.5, 2.0, 3.0, 4.0)


class StaticController:
    def __init__(self, action, name="b"):
        self.a, self.name = action, name

    def reset(self, ctx=None):
        return self.a

    def act(self, obs):
        return self.a


def tune_static(P, scenario, pacing, seeds, duration_ms=None, miss_max=0.01, clocks=None):
    """Grid search over (clock x duty) [unaligned] or (clock x guard) [aligned]. Feasible = miss fraction <= miss_max on EVERY tuning seed.
    Returns dict(action, tok_s, power_w, miss_max_seen, objective, feasible). If nothing is feasible the least-missing setting is returned with feasible False."""
    sc = build(scenario) if duration_ms is None else build(scenario, duration_ms)
    knob = DUTIES if pacing == "unaligned" else GUARDS
    best = None
    least = None
    for clk in (clocks or ALLOWED_CLOCKS(P)):
        for k in knob:
            a = Action(clock=clk, pacing=pacing, duty=k) if pacing == "unaligned" else Action(clock=clk, pacing=pacing, guard_ms=k)
            ss = [summarise(Plant(P, sc, seed=s).run(a)) for s in seeds]
            miss = max(x["miss_frac"] for x in ss)
            tok, pw = float(np.mean([x["bg_tok_s"] for x in ss])), float(np.mean([x["power_w"] for x in ss]))
            row = dict(action=a, tok_s=tok, power_w=pw, miss_max_seen=miss, objective=tok - LAMBDA * pw)
            if miss <= miss_max and (best is None or row["objective"] > best["objective"]):
                best = row
            if least is None or miss < least["miss_max_seen"]:
                least = row
    return dict(best, feasible=True) if best else dict(least, feasible=False)
