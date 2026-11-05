"""tools/dashboard/demo.py: the demo launcher's planning, output-directory and safety rules (no GPU; the hardware run itself is not testable here).
Instruction (Arjun): "tools/dashboard/demo.py runs ONE scene with a chosen model and manager through the existing hardware executor (helper required, same preflight checks), with telemetry on ... Mark demo runs as demos
in their meta.json and keep their output out of data/w5b/eval ... Do not change any registered result, constants.json, the evaluation runner, or the driver exe." """
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DASH = ROOT / "tools" / "dashboard"
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(DASH)); sys.path.insert(0, str(ROOT / "experiments" / "w5b"))
import demo  # noqa: E402
import eval_lib as el  # noqa: E402

FROZEN_SHA = "f7b99650efe7fea9d392a1aee2e49a18a84a00fe69d56fb4e41bf562cc6fb4a9"


def const():
    return demo.load_frozen_constants()


def test_the_frozen_constants_file_is_unchanged_and_loaded_with_its_hash_check():
    assert hashlib.sha256((ROOT / "data" / "w5b" / "constants.json").read_bytes()).hexdigest() == FROZEN_SHA
    assert const()["c0"] == 7


@pytest.mark.parametrize("scene,manager,model", [("S1", "dB", "3b"), ("S0", "gB", "1b"), ("S2", "eB", "phi"), ("S5", "dB", "8b"), ("S1d", "cBb", "3b"), ("S1", "a", "3b")])
def test_plan_is_the_evaluation_cell_with_only_model_id_and_demo_flag_changed(scene, manager, model):
    c = const()
    spec, out = demo.plan(scene, model, manager, 60.0, c, stamp="20261106T000000Z")
    tpl = next(x for x in el.block_cells(4, c, seed_block=4) if x["scene"] == scene and x["controller"] == demo.MANAGERS[manager] and x["budget_w"] == 60.0)
    diff = {k for k in set(spec) | set(tpl) if spec.get(k) != tpl.get(k)}
    assert diff <= {"id", "workload", "demo", "exploratory", "block"}, diff
    assert spec["demo"] is True and spec["id"].startswith("demo_") and spec["workload"] == demo.MODELS[model]
    for k in ("kind", "setting", "params", "steer_budget_w", "headroom_w", "c0", "origin_ms", "budget_w"):
        assert spec.get(k) == tpl.get(k), k                                                                      # the controller and its frozen constants are exactly the registered ones
    assert out == demo.DEMO_ROOT / ("20261106T000000Z_" + spec["id"])


def test_plan_rejects_unknown_choices_and_arm_a_at_35_w():
    c = const()
    for bad in (("S9", "3b", "dB", 60.0), ("S1", "70b", "dB", 60.0), ("S1", "3b", "zz", 60.0), ("S1", "3b", "dB", 45.0), ("S1", "3b", "a", 35.0)):
        with pytest.raises(ValueError):
            demo.plan(*bad, c)


def test_a_shorter_measured_window_is_recorded_in_the_spec():
    spec, _ = demo.plan("S1", "3b", "dB", 60.0, const(), measure_s=30)
    assert spec["measure_s"] == 30.0


def test_output_stays_out_of_the_registered_evaluation_tree():
    assert demo.check_out_dir(demo.DEMO_ROOT / "x").parts[-2:] == ("dashboard_demos", "x")
    for bad in (ROOT / "data" / "w5b" / "eval", ROOT / "data" / "w5b" / "eval" / "block04", ROOT / "data" / "w5b" / "eval" / "block99" / "cells" / "x"):
        with pytest.raises(ValueError):
            demo.check_out_dir(bad)
    assert "w5b" not in str(demo.DEMO_ROOT) and "w5b" not in str(demo.SESSION_FILE)


def test_session_registry_has_the_ring_names_and_marks_a_demo():
    spec, _ = demo.plan("S1", "3b", "dB", 60.0, const())
    names = dict(frames="a", tokens="b", ctrl="c", pace="d", decision="e")
    reg = demo.session_registry(names, spec, pid=4242)
    assert json.loads(json.dumps(reg))["names"] == names and reg["demo"] is True and reg["pid"] == 4242 and reg["controller"] == "d'B" and reg["workload"] == "llama32_3b"


def test_cli_rejects_unknown_choices():
    r = subprocess.run([sys.executable, str(DASH / "demo.py"), "--scene", "S9", "--model", "3b", "--manager", "dB"], capture_output=True, text=True, timeout=60)
    assert r.returncode == 2 and "invalid choice" in r.stderr


def test_demo_uses_the_registered_preflight_marks_meta_and_resets_the_telemetry_default():
    src = (DASH / "demo.py").read_text(encoding="utf-8")
    assert "from tune import refusal" in src and "refusal(a.armoury_mode" in src and "chrome_running" in src and "procsnap" in src      # the same refusal rules as evaluate.py
    assert 'meta.update(demo=True' in src and "Governor.default_telemetry = None" in src and "check_out_dir" in src
    assert "data/dashboard_demos" in src and "data/w5b/eval" in src                                              # documented in the docstring: output goes to the first, never the second


def test_the_registered_runner_executor_and_driver_know_nothing_of_the_dashboard():
    for rel in ("experiments/w5b/evaluate.py", "experiments/w5b/executors.py", "experiments/w5b/eval_lib.py", "controllers/model.py", "controllers/hybrid.py", "controllers/pi.py"):
        txt = (ROOT / rel).read_text(encoding="utf-8")
        assert "dashboard" not in txt and "decision_block" not in txt and "default_telemetry" not in txt, rel
    drv = (ROOT / "workloads" / "background" / "llama_governed_bench.cpp").read_text(encoding="utf-8")
    assert "dashboard" not in drv


def test_no_energy_counter_call_in_the_demo_launcher():
    assert "TotalEnergy" not in (DASH / "demo.py").read_text(encoding="utf-8")
