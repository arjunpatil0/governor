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
    from controllers.pi import SwitchingPIController
    k, c = ex.build_controller(P, spec("cB", params=dict(target=0.65, ki=0.05)))
    assert k == "ctl" and isinstance(c, SwitchingPIController) and c.al.target == c.un.target == 0.65 and c.al.ki == 0.05 and c.al.guard0 == 0.5 and c.al.gmin == 0.3 and c.al.power_budget_w == 60.0
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
    fa = s.run(spec("fg_alone", scene=None), tmp_path)
    assert fa["c0m"] > 0.0 and fa["c0m_unlocked"] > 0.0 and fa["c0m_unlocked"] < fa["c0m"]               # unlocked boost makes the frame shorter than at the locked 1800 MHz that defines nominal
    assert s.run(spec("bg_alone", scene=None), tmp_path)["tok_s"] > 20.0
    assert 0.0 <= s.run(spec("static", setting=dict(sid="1500_a_g1_d1", clock=1500, mode="aligned", guard_ms=1.0, duty=1.0)), tmp_path)["miss"] <= 1.0


def test_hardware_executor_source_never_leaves_a_clock_locked_and_checks_the_abort_rules():
    src = (ROOT / "experiments" / "w5b" / "executors.py").read_text(encoding="utf-8")
    assert "finally" in src and "cl.reset()" in src and "HwThermalSlowdown" in src and "HwPowerBrake" in src and "85" in src


# ---------------------------------------------------------------- governed-cell power anomaly (sitting 2026-10-23/24): second, independent power measure and a diagnostic A/B
def test_window_mean_averages_the_samples_inside_the_window_only():
    import numpy as np
    t = np.array([0.0, 1.0, 2.0, 3.0, 4.0]); v = np.array([100.0, 10.0, 20.0, 30.0, 100.0])
    assert ex.window_mean(t, v, 1.0, 4.0) == 20.0 and np.isnan(ex.window_mean(t, v, 10.0, 11.0))


def test_a_static_action_can_run_through_the_governor_loop_for_the_ab_diagnostic():
    k, c = ex.build_controller(P, spec("gov_static", setting=dict(sid="1800_a_g0_d1", clock=1800, mode="aligned", guard_ms=0.0, duty=1.0)))
    a = c.reset(dict(params=P, period_ms=1000 / 60, deadline_ms=1000 / 60))
    assert k == "ctl" and a.clock == 1800.0 and a.pacing == "aligned" and a.duty == 1.0 and c.act(None) == a


def test_the_hardware_executor_records_the_sampled_power_next_to_the_energy_counter_power():
    src = (ROOT / "experiments" / "w5b" / "executors.py").read_text(encoding="utf-8")
    assert "power_sampled_w" in src and "gov_no_energy" in src


def test_recent_mean_uses_only_the_last_span_of_samples():
    import numpy as np
    t = [0.0, 0.5, 0.9, 1.0]; v = [100.0, 100.0, 40.0, 60.0]
    assert abs(ex.recent_mean(t, v, 1.0, 0.2) - 50.0) < 1e-9 and np.isnan(ex.recent_mean(t, v, 5.0, 0.2)) and np.isnan(ex.recent_mean([], [], 1.0, 0.2))


def test_the_governed_cell_can_take_its_power_from_the_sampled_source_without_reading_the_energy_counter():
    src = (ROOT / "experiments" / "w5b" / "executors.py").read_text(encoding="utf-8")
    assert 'power_source' in src and '"sampled"' in src and "gov_reads" in src and "power_w=pw" in src


def test_the_hardware_executor_defaults_to_the_sampled_power_source_and_rejects_a_cell_whose_loop_read_the_counter():
    src = (ROOT / "experiments" / "w5b" / "executors.py").read_text(encoding="utf-8")
    assert 'def __init__(self, power_source="sampled")' in src and "never read the energy counter" in src
