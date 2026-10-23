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
