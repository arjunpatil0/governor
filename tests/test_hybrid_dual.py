"""d'B shares ONE action space with every other controller: clock x {aligned guard/duty, unaligned duty} (reviewer 2026-10-23 blocker 2, trial_static: at c0m 6.68 ms aligned pacing gives 0 tok/s).
The hybrid's active branch must therefore choose unaligned duty pacing when the aligned plan admits no token, and aligned pacing when it does, without flapping; the idle branch stays the eB rule.
Run on the frozen simulator as a unit-test harness (NOT an evaluation).
Instruction (Arjun, 2026-10-23 / reviewer): "BLOCKER before tuning d'B: all controllers ... share one action space ... fix d'B test-first"."""
import dataclasses
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from controllers.hybrid import HybridController  # noqa: E402
from sim.params import load_params  # noqa: E402
from sim.plant import Plant, summarise  # noqa: E402
from sim.scenarios import build  # noqa: E402

P = load_params()


def run(cost, scene="S0", dur=40000.0, seed=1, margin=0.2):
    sc = build(scene, duration_ms=dur)
    base = sc.fg.cost_ms
    sc = dataclasses.replace(sc, fg=dataclasses.replace(sc.fg, cost_ms=lambda t, c=cost, b=base: b(t) * c / 7.0))
    ctl = HybridController(P, 60.0, safety=1.0 - margin, switch_gain=2.0, clock_every=20)
    res = Plant(P, sc, seed=seed).run(ctl)
    return summarise(res), res, ctl


def pacings(res):
    return [a.pacing for _, a in res.actions]


def test_light_frames_keep_aligned_pacing_and_a_high_token_rate():
    s, res, _ = run(5.0)
    pc = pacings(res)
    assert pc.count("aligned") / len(pc) > 0.9 and s["bg_tok_s"] > 25.0 and s["miss_frac"] <= 0.01


def test_when_aligned_admits_no_token_the_hybrid_uses_unaligned_duty_pacing_and_still_makes_tokens():
    s, res, _ = run(10.0, margin=0.4)                        # the aligned-only hybrid delivered 0 tok/s here (measured before the fix); the margin is the d'B safety knob (T3b tunes it)
    pc = pacings(res)
    assert pc.count("unaligned") / len(pc) > 0.5
    assert s["bg_tok_s"] >= 2.0 and s["miss_frac"] <= 0.03


def test_a_larger_margin_is_a_safer_knob_in_the_unaligned_regime():
    lo = run(10.0, margin=0.1)[0]
    hi = run(10.0, margin=0.4)[0]
    assert hi["miss_frac"] < lo["miss_frac"] and hi["bg_tok_s"] < lo["bg_tok_s"]


def test_the_pacing_mode_does_not_flap_in_a_steady_scene():
    for cost in (5.0, 9.0, 10.0):
        _, res, _ = run(cost)
        pc = pacings(res)
        assert sum(1 for a, b in zip(pc, pc[1:]) if a != b) <= 6, cost


def test_the_stepping_scene_keeps_the_slo_with_both_modes_available():
    s, res, _ = run(9.0, scene="S1", dur=60000.0, margin=0.4)
    assert s["miss_frac"] <= 0.03 and s["bg_tok_s"] > 3.0


def test_actions_stay_inside_the_shared_action_space():
    _, res, _ = run(10.0)
    for _, a in res.actions:
        assert a.pacing in ("aligned", "unaligned") and 0.0 < a.duty <= 1.0 and a.guard_ms >= 0.0 and a.clock >= 900.0
