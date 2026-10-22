"""Start-up clock reset (actuators/startup_reset.py; decision 5: the governor always resets clock locks at start to cover a hard-killed helper) and the warm-up registry for
freshly built executables (workloads/common/exe_warm.py; decision 4: a never-seen exe may be pre-executed by the endpoint scanner). Fake runners, no GPU, no admin.
Instruction: "Governor start-up always runs a clock reset (nvidia-smi -rgc / -rmc) to cover a hard-killed helper"."""
import json
import subprocess
import uuid

import pytest

from actuators.startup_reset import reset_clocks
from controllers.runtime import Governor
from telemetry.obs_builder import ObsBuilder
from telemetry.ring import SeqBlock, SharedRing
from workloads.common.exe_warm import ensure_warm


class Runner:
    def __init__(self, rc=0):
        self.calls, self.rc = [], rc

    def __call__(self, argv, **kw):
        self.calls.append(list(argv))
        return subprocess.CompletedProcess(argv, self.rc, "", "")


class Client:
    def __init__(self, ok=True):
        self.ok, self.calls = ok, []

    def reset(self):
        self.calls.append("reset")
        return self.ok


def test_elevated_start_resets_the_helper_and_both_nvidia_smi_locks_with_fixed_argv():
    r, c = Runner(), Client()
    rep = reset_clocks(c, runner=r, is_admin=True)
    assert c.calls == ["reset"] and r.calls == [["nvidia-smi", "-rgc"], ["nvidia-smi", "-rmc"]]
    assert rep["helper"] is True and rep["rgc"] is True and rep["rmc"] is True


def test_unelevated_start_uses_only_the_helper_and_says_so():
    r, c = Runner(), Client()
    rep = reset_clocks(c, runner=r, is_admin=False)
    assert r.calls == [] and rep["rgc"] == "skipped: not elevated" and rep["helper"] is True


def test_no_working_channel_is_an_error_not_a_warning():
    with pytest.raises(RuntimeError):
        reset_clocks(Client(ok=False), runner=Runner(rc=1), is_admin=True)
    with pytest.raises(RuntimeError):
        reset_clocks(None, runner=Runner(), is_admin=False)           # not elevated and no helper: nothing could have reset the clock


def test_one_failing_channel_is_reported_but_tolerated_if_another_worked():
    rep = reset_clocks(Client(ok=True), runner=Runner(rc=1), is_admin=True)
    assert rep["helper"] is True and rep["rgc"] is False


def nm():
    return "Local\\gov_test_" + uuid.uuid4().hex


class Act:
    def __init__(self):
        self.calls = []

    def apply(self, a):
        self.calls.append(a)


class Ctl:
    def reset(self, ctx):
        return "initial"


def test_governor_start_runs_the_clock_reset_before_anything_else():
    order = []
    act = Act()
    gov = Governor(Ctl(), ObsBuilder(16.7, 16.7), act, SharedRing(nm(), 8, 3, create=True), SharedRing(nm(), 8, 1, create=True), 16.7, 16.7)
    gov.start(0.0, startup_reset=lambda: order.append("reset"))
    assert order == ["reset"] and act.calls == ["initial"]


def test_governor_does_not_start_if_the_clock_reset_fails():
    act = Act()
    gov = Governor(Ctl(), ObsBuilder(16.7, 16.7), act, SharedRing(nm(), 8, 3, create=True), SharedRing(nm(), 8, 1, create=True), 16.7, 16.7)

    def bad():
        raise RuntimeError("no channel")
    with pytest.raises(RuntimeError):
        gov.start(0.0, startup_reset=bad)
    assert act.calls == []


def test_exe_is_warmed_once_per_hash_and_never_again(tmp_path):
    exe = tmp_path / "a.exe"; exe.write_bytes(b"MZ-one")
    reg = tmp_path / "reg.json"
    r = Runner()
    assert ensure_warm(exe, ["--warm"], reg, runner=r) is True and len(r.calls) == 1 and r.calls[0][0] == str(exe)
    assert ensure_warm(exe, ["--warm"], reg, runner=r) is False and len(r.calls) == 1
    copy = tmp_path / "b.exe"; copy.write_bytes(b"MZ-one")
    assert ensure_warm(copy, ["--warm"], reg, runner=r) is False                    # same bytes: already seen
    exe.write_bytes(b"MZ-two")
    assert ensure_warm(exe, ["--warm"], reg, runner=r) is True and len(r.calls) == 2
    assert len(json.loads(reg.read_text())) == 2
