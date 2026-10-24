"""W5b tuning sitting (experiments/w5b/tune.py): the unattended loop around the pure plan of tune_lib - refusals (uptime / AC / Armoury mode / clean tree / Chrome), resumable cell storage,
incident handling (two consecutive failures stop the sitting), decisions.json, the stop report when the gate fails.
Instruction (Arjun, 2026-10-23): "give me the T1-T3 session commands, set up to run unattended overnight (fresh-restart check, helper start, chained blocks), plus the morning checks"."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "experiments" / "w5b")); sys.path.insert(0, str(ROOT / "tests"))
import tune  # noqa: E402
from test_w5b_tune_lib import fake_world  # noqa: E402


class Stub:
    name = "stub"

    def __init__(self, fake, fail_ids=()):
        self.fake, self.fail_ids, self.calls = fake, set(fail_ids), []

    def run(self, spec, cdir):
        self.calls.append(spec["id"])
        if spec["id"] in self.fail_ids:
            raise RuntimeError("boom")
        return self.fake(spec)

    def between_cells(self):
        pass


def test_refusals_cover_uptime_ac_armoury_tree_and_chrome():
    ok = dict(armoury_mode="Performance", plugged=True, uptime_s=600, max_uptime_s=7200, porcelain="?? data/w5b/\n", chrome=False)
    assert tune.refusal(**ok) is None
    assert "armoury" in tune.refusal(**dict(ok, armoury_mode=None)).lower()
    assert "battery" in tune.refusal(**dict(ok, plugged=False))
    assert "restart" in tune.refusal(**dict(ok, uptime_s=7201)).lower()
    assert "clean" in tune.refusal(**dict(ok, porcelain=" M a.py\n"))
    assert "Chrome" in tune.refusal(**dict(ok, chrome=True))


def test_a_full_sitting_writes_every_cell_and_the_decisions(tmp_path):
    ex = Stub(fake_world(good_c0=8))
    s = tune.run_sitting(tmp_path, ex, log=lambda *a: None)
    assert s["stop"] is None and s["finished"] is True
    d = json.loads((tmp_path / "decisions.json").read_text(encoding="utf-8"))
    assert d["c0"] == 8 and d["d_b"].startswith("deferred")
    cells = list((tmp_path / "cells").glob("*/cell.json"))
    assert len(cells) == len(ex.calls) and json.loads(cells[0].read_text(encoding="utf-8"))["executor"] == "stub"


def test_a_limited_sitting_resumes_without_rerunning_finished_cells(tmp_path):
    ex1 = Stub(fake_world(good_c0=8))
    s1 = tune.run_sitting(tmp_path, ex1, limit=5, log=lambda *a: None)
    assert s1["finished"] is False and len(ex1.calls) == 5
    ex2 = Stub(fake_world(good_c0=8))
    tune.run_sitting(tmp_path, ex2, log=lambda *a: None)
    assert not set(ex1.calls) & set(ex2.calls) and (tmp_path / "decisions.json").exists()


def test_two_consecutive_failures_stop_the_sitting_and_are_logged_as_incidents(tmp_path):
    ex = Stub(fake_world(good_c0=8), fail_ids=("t1_bgalone_llama32_1b", "t1_bgalone_llama32_3b", "t1_bgalone_phi35_mini"))
    s = tune.run_sitting(tmp_path, ex, log=lambda *a: None)
    assert s["stop"] and "two consecutive" in s["stop"]
    inc = list((tmp_path / "cells").glob("*/incident.json"))
    assert len(inc) == 2 and "boom" in inc[0].read_text(encoding="utf-8")


def test_a_failed_gate_writes_the_stop_report_and_decisions(tmp_path):
    s = tune.run_sitting(tmp_path, Stub(fake_world(good_c0=99)), log=lambda *a: None)
    assert s["stop"] and "no c0" in s["stop"]
    assert json.loads((tmp_path / "decisions.json").read_text(encoding="utf-8"))["stop"].startswith("no c0")


def test_a_deadline_stops_the_sitting_between_cells_and_it_resumes(tmp_path):
    ex = Stub(fake_world(good_c0=8))
    s = tune.run_sitting(tmp_path, ex, deadline=0.0, log=lambda *a: None)             # already past: not a single cell is started
    assert s["finished"] is False and "deadline" in s["stop"] and ex.calls == []


def test_a_resume_in_the_same_boot_is_recognised_and_a_reboot_is_not():
    from datetime import datetime, timezone
    boot = 1_700_000_000.0
    meta = dict(boot_utc=datetime.fromtimestamp(boot, timezone.utc).isoformat())
    assert tune.is_resume(meta, boot + 1.0) and not tune.is_resume(meta, boot + 3600.0) and not tune.is_resume({}, boot)


def test_a_t3b_sitting_runs_through_the_planner_hook_and_writes_its_decisions(tmp_path):
    import tune_lib as tl
    s = tune.run_sitting(tmp_path, Stub(fake_world(good_c0=7)), log=lambda *a: None, planner=lambda r: tl.next_batch_t3b(r, 7))
    d = json.loads((tmp_path / "decisions.json").read_text(encoding="utf-8"))
    assert s["finished"] and d["c0"] == 7 and d["d_b"]["margin"] == 0.2 and d["c_b"]["rule_met"] is True


# ---------------------------------------------------------------- power source for the Governor loop (plan addendum O-4)
def test_the_power_source_for_t3b_comes_from_the_diagnostic_gate_and_is_refused_without_it(tmp_path):
    import pytest
    none = tmp_path / "no_o5.md"                                                                   # isolate from the real docs/W5B_ADDENDUM_O5.md
    assert tune.resolve_power_source("t1t3", "auto", tmp_path, o5_path=none) == "energy"            # the first sitting is not changed retroactively
    with pytest.raises(SystemExit):
        tune.resolve_power_source("t3b", "auto", tmp_path, o5_path=none)                           # no gate result: T3b must not guess
    (tmp_path / "power_source.json").write_text(json.dumps(dict(power_source="sampled", verdict="CONFIRMED_PHANTOM")))
    assert tune.resolve_power_source("t3b", "auto", tmp_path, o5_path=none) == "sampled"
    (tmp_path / "power_source.json").write_text(json.dumps(dict(power_source=None, verdict="STOP")))
    with pytest.raises(SystemExit):
        tune.resolve_power_source("t3b", "auto", tmp_path, o5_path=none)
    assert tune.resolve_power_source("t3b", "energy", tmp_path, o5_path=none) == "energy"                          # an explicit choice is honoured (and recorded)


# ---------------------------------------------------------------- addendum O-5 (post hoc): governed T3b / evaluation cells use the sampled power source and never read the energy counter
def test_with_addendum_o5_an_explicit_sampled_source_is_allowed_for_t3b_despite_a_stop_verdict_and_energy_is_refused(tmp_path):
    import pytest
    o5 = tmp_path / "O5.md"
    diag = tmp_path / "diag"; diag.mkdir()
    (diag / "power_source.json").write_text(json.dumps(dict(power_source=None, verdict="STOP")))
    with pytest.raises(SystemExit):
        tune.resolve_power_source("t3b", "auto", diag, o5_path=o5)                                  # auto still honours the gate: STOP -> refused
    with pytest.raises(SystemExit):
        tune.resolve_power_source("t3b", "sampled", diag, o5_path=o5)                               # explicit override needs addendum O-5 to exist
    o5.write_text("addendum O-5 (post hoc)")
    assert tune.resolve_power_source("t3b", "sampled", diag, o5_path=o5) == "sampled"
    with pytest.raises(SystemExit):
        tune.resolve_power_source("t3b", "energy", diag, o5_path=o5)                                # O-5: governed cells never read the counter
    with pytest.raises(SystemExit):
        tune.resolve_power_source("t3b", "auto", diag, o5_path=o5)                                  # auto with a STOP verdict stays refused even with O-5
    assert tune.resolve_power_source("t1t3", "auto", diag, o5_path=o5) == "energy"                  # the finished first sitting is not re-labelled
