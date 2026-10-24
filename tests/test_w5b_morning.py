"""Morning check of a W5b tuning sitting (experiments/w5b/morning.py): counts, incidents, per-cell flags, the c0 search, the decisions, the manifest, the helper log tail hint.
Instruction (Arjun, 2026-10-23): "give me the T1-T3 session commands ... plus the morning checks"."""
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "experiments" / "w5b"))
from morning import check  # noqa: E402


def write_cell(d, cid, **metrics):
    c = d / "cells" / cid
    c.mkdir(parents=True)
    (c / "cell.json").write_text(json.dumps(dict(id=cid, spec=dict(id=cid, kind="static"), metrics=dict(dict(miss=0.0, tok_s=10.0, power_w=40.0), **metrics), executor="hw", wall_s=100.0)))


def test_clean_sitting_reports_no_problems(tmp_path):
    write_cell(tmp_path, "a"); write_cell(tmp_path, "b")
    (tmp_path / "decisions.json").write_text(json.dumps(dict(c0=8, stop=None, executor="hw", c0_search=[], d_b=dict(margin=0.2, rule_met=True), c_b=dict(rule_met=True), g_b={})))
    (tmp_path / "meta.json").write_text(json.dumps(dict(armoury_mode="Performance", battery_charge_mode="Balanced 80%", uptime_s=300)))
    man = {str(p.relative_to(tmp_path)).replace(chr(92), "/"): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(tmp_path.rglob("*")) if p.is_file()}
    (tmp_path / "manifest.json").write_text(json.dumps(man))
    r = check(tmp_path)
    assert r["problems"] == [] and r["cells"] == 2 and r["decisions"]["c0"] == 8


def test_incidents_flags_missing_decisions_and_manifest_mismatch_are_reported(tmp_path):
    write_cell(tmp_path, "a", thermal_reason_bits=64, clock_ok=False, abandoned=10, ring_dropped=2, temp_after_c=84)
    inc = tmp_path / "cells" / "b"; inc.mkdir(parents=True); (inc / "incident.json").write_text("{}")
    (tmp_path / "manifest.json").write_text(json.dumps({"cells/a/cell.json": "0" * 64}))
    r = check(tmp_path)
    p = " | ".join(r["problems"])
    assert "incident" in p and "decisions.json" in p and "manifest" in p
    f = " | ".join(r["flags"])
    assert "thermal" in f and "clock_ok" in f and "abandoned" in f and "ring_dropped" in f and "temp" in f


def test_energy_and_sampled_power_that_disagree_fail_the_check_except_in_diagnostic_cells(tmp_path):
    write_cell(tmp_path, "a", power_w=90.0, power_sampled_w=45.0)
    write_cell(tmp_path, "b", power_w=50.0, power_sampled_w=48.0)
    write_cell(tmp_path, "diag_gov_static", power_w=90.0, power_sampled_w=45.0)
    r = check(tmp_path)
    p = " | ".join(r["problems"])
    assert "a: energy-counter power 90.0 W vs sampled 45.0 W" in p and "b:" not in p and "diag_gov_static: energy" not in p


# ---------------------------------------------------------------- diagnostic gate for block T3b (plan addendum O-4)
from morning import diag_gate  # noqa: E402


def arm(d, cid, e, m, tok=20.0, reads=0.0):
    write_cell(d, cid, power_w=e, power_sampled_w=m, tok_s=tok, gov_reads_per_s=reads)


def arms(d, e_s=45.0, e_g=87.0, e_n=45.0, e_c=88.0, e_cs=44.0, m=45.0, r=10.0):
    arm(d, "diag_static", e_s, m)
    arm(d, "diag_gov_static", e_g, m, reads=r)
    arm(d, "diag_gov_static_noenergy", e_n, m)
    arm(d, "diag_cb", e_c, m, tok=3.0, reads=r)
    arm(d, "diag_cb_sampled", e_cs, 45.0, tok=18.0)


def test_phantom_energy_confirmed_selects_the_sampled_power_source(tmp_path):
    arms(tmp_path)                                                         # +42 W on both arms with 10 reads/s (4.2 J each), none on the no-reads and static arms
    g = diag_gate(tmp_path)
    assert g["ok"] is True and g["verdict"] == "CONFIRMED_PHANTOM" and g["power_source"] == "sampled"
    assert abs(g["predicted_inflation_w"] - 42.0) < 1e-9 and abs(g["observed_inflation_w"] - 42.0) < 1e-9
    assert json.loads((tmp_path / "power_source.json").read_text(encoding="utf-8"))["power_source"] == "sampled"
    assert any("diag_gov_static" in line and "87.0" in line for line in g["lines"])


def test_no_anomaly_keeps_the_energy_source(tmp_path):
    arms(tmp_path, e_g=46.0, e_c=45.0)
    g = diag_gate(tmp_path)
    assert g["ok"] is True and g["verdict"] == "NO_ANOMALY" and g["power_source"] == "energy"


def test_an_anomaly_that_the_phantom_does_not_explain_stops_the_run(tmp_path):
    arms(tmp_path, e_n=85.0)                                               # the no-reads arm is also inflated: a new problem
    g = diag_gate(tmp_path)
    assert g["ok"] is False and g["verdict"] == "STOP" and g["power_source"] is None and any("no-reads" in r or "noenergy" in r for r in g["reasons"])
    arms2 = tmp_path / "b"; arms2.mkdir()
    arms(arms2, e_g=60.0, e_c=60.0)                                        # inflated by 15 W, but 10 reads/s predict 42 W: not the phantom
    assert diag_gate(arms2)["verdict"] == "STOP"


def test_the_sampled_source_must_itself_look_right_on_the_c_b_arm(tmp_path):
    arms(tmp_path, e_cs=80.0)                                              # the fix arm still disagrees with its sampled power
    g = diag_gate(tmp_path)
    assert g["ok"] is False and any("diag_cb_sampled" in r for r in g["reasons"])
    assert diag_gate(tmp_path / "nowhere")["ok"] is False


def test_cells_without_a_sampled_power_stop_the_gate_instead_of_crashing(tmp_path):
    for cid in ("diag_static", "diag_gov_static", "diag_gov_static_noenergy", "diag_cb", "diag_cb_sampled"):
        write_cell(tmp_path, cid, power_w=45.0)
    g = diag_gate(tmp_path)
    assert g["ok"] is False and any("power_sampled_w missing" in r for r in g["reasons"])
