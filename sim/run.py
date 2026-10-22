"""Run controllers against the plant over scenarios x seeds (docs/W45_SIM_PROTOCOL.md). Simulation only.
Tuning seeds 100-109, evaluation seeds 200-229. Parameters chosen on tuning seeds are stored in data/sim_tuned.json before evaluation."""
import concurrent.futures as cf
import json
from pathlib import Path

import numpy as np
import pandas as pd

from controllers.model import ModelController
from controllers.none import NoGovernor
from controllers.pi import PIController
from controllers.static import IdleDropController, StaticController
from sim.plant import Action, Plant, summarise
from sim.scenarios import SCENARIOS, build

ROOT = Path(__file__).resolve().parents[1]
TUNING_SEEDS = tuple(range(100, 110))
EVAL_SEEDS = tuple(range(200, 230))
CONTROLLERS = ("a", "b", "b'", "c", "c'", "d", "d'")
TUNED_PATH = ROOT / "data" / "sim_tuned.json"


def load_tuned(path=TUNED_PATH):
    return json.loads(Path(path).read_text(encoding="utf-8")) if Path(path).exists() else {}


def make_controller(P, name, scenario, tuned, budget=None):
    if name == "a":
        return NoGovernor(P)
    if name in ("b", "b'"):
        a = tuned["static"][scenario][name]
        return StaticController(Action(**a), name=name)
    if name == "bj'":                                   # follow-up: per-scenario aligned static re-tuned under token jitter
        return StaticController(Action(**tuned["static_jit"][scenario]["b'"]), name=name)
    if name in ("g", "g'"):                             # follow-up: scenario-agnostic static
        return StaticController(Action(**tuned["global"][name]), name=name)
    if name == "e":                                     # follow-up: aligned scenario-agnostic static + idle-triggered clock drop
        return IdleDropController(P, Action(**tuned["global"]["g'"]))
    if name in ("b'B", "g'B", "eB", "c'B", "d'B"):       # power-budget variants (primary objective since 2026-10-22; post-hoc rerun of the frozen study)
        key = str(int(budget))
        if name == "b'B":
            return StaticController(Action(**tuned["budget"][key]["static"][scenario]), name=name)
        if name == "g'B":
            return StaticController(Action(**tuned["budget"][key]["global"]), name=name)
        if name == "eB":
            return IdleDropController(P, Action(**tuned["budget"][key]["global"]))
        kw = dict(tuned.get("params", {}).get(name[:-1], {}), power_budget_w=float(budget))      # frozen constants of c' / d' plus the budget
        return PIController(P, "aligned", **kw) if name == "c'B" else ModelController(P, "aligned", **kw)
    pacing = "unaligned" if name in ("c", "d") else "aligned"
    kw = tuned.get("params", {}).get(name, {})
    return PIController(P, pacing, **kw) if name in ("c", "c'") else ModelController(P, pacing, **kw)


def run_one(args):
    P, name, scenario, seed, tuned, jitter, budget = args
    sc = build(scenario, jitter=jitter)
    s = summarise(Plant(P, sc, seed=seed).run(make_controller(P, name, scenario, tuned, budget)))
    return dict(controller=name, scenario=scenario, seed=seed, jitter=jitter, budget=budget, **s)


def run_matrix(P, controllers, scenarios, seeds, tuned, workers=8, jitter=False, budget=None):
    jobs = [(P, c, s, seed, tuned, jitter, budget) for s in scenarios for c in controllers for seed in seeds]
    with cf.ProcessPoolExecutor(max_workers=workers) as ex:
        rows = list(ex.map(run_one, jobs, chunksize=4))
    return pd.DataFrame(rows)
