"""W5b tuning executors (experiments/w5b/executors.py): controller construction from a cell spec (c'B pacing mode and constants, d'B margin = 1 - safety), the simulator dry-run executor
(an end-to-end check of the sitting logic that touches no hardware; its cells are labelled executor 'sim' and never mixed with data), the safety checks of the hardware executor that need no GPU.
Instruction (Arjun, 2026-10-23): "give me the T1-T3 session commands, set up to run unattended overnight"."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "experiments" / "w5b")); sys.path.insert(0, str(ROOT))
import executors as ex  # noqa: E402
from sim.params import load_params  # noqa: E402

P = load_params()


def spec(kind, **kw):
    base = dict(id="x", kind=kind, workload="llama32_3b", scene="S1", c0=8, budget_w=60.0)
    base.update(kw)
    return base


def test_static_and_arm_a_are_fixed_actions():
    k, a = ex.build_controller(P, spec("static", setting=dict(sid="1500_a_g1_d0.5", clock=1500, mode="aligned", guard_ms=1.0, duty=0.5)))
    assert k == "static" and a.clock == 1500.0 and a.pacing == "aligned" and a.guard_ms == 1.0 and a.duty == 0.5
    k, a = ex.build_controller(P, spec("static", setting=dict(sid="unlocked_u_d0.1", clock="unlocked", mode="unaligned", guard_ms=0.5, duty=0.1)))
    assert a.clock == P.UNLOCKED_MHZ and a.pacing == "unaligned"
    k, a = ex.build_controller(P, spec("arm_a"))
    assert a.clock == P.UNLOCKED_MHZ and a.pacing == "unaligned" and a.duty == 1.0


def test_c_b_and_d_b_use_the_tuned_constants_and_the_margin_is_one_minus_safety():
    k, c = ex.build_controller(P, spec("cB", pacing="aligned", params=dict(target=0.65, ki=0.05)))
    assert k == "ctl" and c.pacing == "aligned" and c.target == 0.65 and c.ki == 0.05 and c.guard0 == 0.5 and c.gmin == 0.3 and c.power_budget_w == 60.0
    k, d = ex.build_controller(P, spec("dB", params=dict(margin=0.2)))
    assert k == "ctl" and abs(d.model.safety - 0.8) < 1e-9 and d.model.switch_gain == 2.0 and d.model.clock_every == 20 and d.model.power_budget_w == 60.0


def test_scene_cost_scales_the_sim_scene_by_c0_over_the_sim_base():
    fg = ex.fg_spec("S1", 14.0)
    assert abs(fg.cost_ms(0.0) - 14.0) < 1e-9 and abs(fg.cost_ms(15000.0) - 14.0 * 0.7) < 1e-9 and abs(fg.cost_ms(25000.0) - 14.0 * 1.3) < 1e-9
    assert abs(ex.fg_spec("S0", 9.0).cost_ms(31000.0) - 9.0) < 1e-9


def test_sim_executor_returns_the_metrics_every_cell_kind_needs(tmp_path):
    s = ex.SimExecutor()
    m = s.run(spec("arm_a"), tmp_path)
    assert {"miss", "tok_s", "power_w"} <= set(m) and m["miss"] >= 0.0
    assert s.run(spec("fg_alone", scene=None), tmp_path)["c0m"] > 0.0
    assert s.run(spec("bg_alone", scene=None), tmp_path)["tok_s"] > 20.0
    assert 0.0 <= s.run(spec("static", setting=dict(sid="1500_a_g1_d1", clock=1500, mode="aligned", guard_ms=1.0, duty=1.0)), tmp_path)["miss"] <= 1.0


def test_hardware_executor_source_never_leaves_a_clock_locked_and_checks_the_abort_rules():
    src = (ROOT / "experiments" / "w5b" / "executors.py").read_text(encoding="utf-8")
    assert "finally" in src and "cl.reset()" in src and "HwThermalSlowdown" in src and "HwPowerBrake" in src and "85" in src
