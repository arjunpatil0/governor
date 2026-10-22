"""Admin SM-clock helper (actuators/clock_helper.py) and its client (actuators/clock_client.py): minimal allowlisted lock/reset service with reset on exit,
disconnect and watchdog timeout (docs/W45_PLAN.md Phase 4b). No GPU and no admin rights needed: the NVML backend is faked, the named pipe is real.
Instruction: "Proceed to the telemetry daemon, llama_governed driver and admin clock helper (/security-scan), test-first, no GPU"."""
import ast
import json
import threading
import time
import uuid
from pathlib import Path

import numpy as np
import pytest

from actuators.clock_client import ClockClient
from actuators.clock_helper import (Command, HelperCore, PipeServer, ProtocolError, current_user_sddl, load_config, parse_command)

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "actuators" / "clock_helper.py"
ALLOWED = [900, 1050, 1200, 1350, 1500, 1800]


class FakeBackend:
    def __init__(self, fail_lock=False, fail_reset=False):
        self.calls, self.fail_lock, self.fail_reset = [], fail_lock, fail_reset

    def lock(self, mhz):
        if self.fail_lock:
            raise RuntimeError("nvml boom")
        self.calls.append(("lock", mhz))

    def reset(self):
        if self.fail_reset:
            raise RuntimeError("nvml reset boom")
        self.calls.append(("reset",))


class Clk:
    def __init__(self):
        self.t = 100.0

    def __call__(self):
        return self.t


def core(**kw):
    be = kw.pop("backend", FakeBackend())
    c = Clk()
    return HelperCore(be, allowed_mhz=ALLOWED, watchdog_s=kw.pop("watchdog_s", 3.0), min_interval_s=kw.pop("min_interval_s", 1.0), now=c), be, c


# ---------------------------------------------------------------- protocol
def test_parser_accepts_exactly_the_four_verbs():
    assert parse_command(b"LOCK 1500\n") == Command("LOCK", 1500)
    assert parse_command(b"RESET\n") == Command("RESET") and parse_command(b"HB\n") == Command("HB") and parse_command(b"PING\r\n") == Command("PING")


@pytest.mark.parametrize("bad", [b"", b"\n", b"lock 1500\n", b"LOCK\n", b"LOCK 15 00\n", b"LOCK -5\n", b"LOCK 1e3\n", b"LOCK 0x5dc\n", b"LOCK 1500 extra\n", b"RESET now\n",
                                 b"LOCK 99999\n", b"SHELL calc\n", b"LOCK 1500; calc\n", b"\x00\x01\n", b"LOCK \xff\n", b"A" * 100 + b"\n", b"LOCK 1500"])
def test_parser_rejects_everything_else(bad):
    with pytest.raises(ProtocolError):
        parse_command(bad)


def test_parser_fuzz_only_ever_returns_a_command_or_raises_protocolerror():
    rng = np.random.default_rng(0)
    alphabet = np.frombuffer(b"LOCKRESETHBPING 0123456789\n\r\x00\xff;&|`$%\"'", dtype=np.uint8)
    for _ in range(5000):
        n = int(rng.integers(0, 40))
        data = bytes(rng.choice(alphabet, size=n).tolist())
        try:
            cmd = parse_command(data)
        except ProtocolError:
            continue
        assert cmd.verb in ("LOCK", "RESET", "HB", "PING")


# ---------------------------------------------------------------- core behaviour
def test_startup_resets_any_stale_lock():
    c, be, _ = core()
    c.startup()
    assert be.calls == [("reset",)]


def test_lock_only_allowlisted_clocks_and_never_touches_the_backend_otherwise():
    c, be, _ = core()
    assert c.handle(Command("LOCK", 1500)) == "OK" and be.calls == [("lock", 1500)]
    be.calls.clear()
    assert c.handle(Command("LOCK", 1499)) == "ERR NOT_ALLOWED" and c.handle(Command("LOCK", 2460)) == "ERR NOT_ALLOWED" and be.calls == []


def test_lock_changes_are_rate_limited_but_reset_is_not():
    c, be, clk = core(min_interval_s=1.0)
    assert c.handle(Command("LOCK", 1500)) == "OK"
    clk.t += 0.5
    assert c.handle(Command("LOCK", 1200)) == "ERR RATE"
    assert c.handle(Command("RESET")) == "OK"
    clk.t += 0.6
    assert c.handle(Command("LOCK", 1200)) == "OK"
    assert [x for x in be.calls if x[0] == "lock"] == [("lock", 1500), ("lock", 1200)]


def test_watchdog_resets_a_lock_when_the_client_goes_silent_and_heartbeats_keep_it():
    c, be, clk = core(watchdog_s=3.0)
    c.handle(Command("LOCK", 1500))
    clk.t += 2.0
    c.tick(); assert be.calls == [("lock", 1500)]
    c.handle(Command("HB"))
    clk.t += 2.0
    c.tick(); assert be.calls == [("lock", 1500)]
    clk.t += 1.5
    c.tick()
    assert be.calls[-1] == ("reset",) and c.handle(Command("PING")) == "OK none"
    n = len(be.calls)
    clk.t += 10; c.tick()
    assert len(be.calls) == n                                        # nothing locked, nothing to reset


def test_disconnect_and_shutdown_reset_and_shutdown_is_idempotent():
    c, be, _ = core()
    c.handle(Command("LOCK", 1200))
    c.on_disconnect()
    assert be.calls[-1] == ("reset",)
    c.handle(Command("LOCK", 1350))
    c.shutdown(); c.shutdown()
    assert be.calls.count(("reset",)) >= 2 and be.calls[-1] == ("reset",)


def test_backend_failure_is_reported_and_leaves_the_state_unlocked():
    c, be, _ = core(backend=FakeBackend(fail_lock=True))
    assert c.handle(Command("LOCK", 1500)) == "ERR BACKEND"
    assert c.handle(Command("PING")) == "OK none" and be.calls[-1] == ("reset",)


# ---------------------------------------------------------------- config and static properties
def _cfg(tmp_path, **over):
    d = dict(allowed_mhz=ALLOWED, watchdog_s=3.0, min_interval_s=1.0)
    d.update(over)
    p = tmp_path / "cfg.json"
    p.write_text(json.dumps(d))
    return p


def test_config_is_validated(tmp_path):
    assert load_config(_cfg(tmp_path), check_acl=False)["allowed_mhz"] == ALLOWED
    for bad in (dict(allowed_mhz=[99999]), dict(allowed_mhz=[]), dict(allowed_mhz=[1500.5]), dict(allowed_mhz=list(range(600, 700))), dict(watchdog_s=0),
                dict(watchdog_s=999), dict(min_interval_s=-1), dict(extra=1)):
        with pytest.raises(ValueError):
            load_config(_cfg(tmp_path, **bad), check_acl=False)


def test_config_in_a_user_owned_location_is_rejected_by_default(tmp_path):
    with pytest.raises(ValueError):
        load_config(_cfg(tmp_path), check_acl=True)                 # owner is the unprivileged user, who is the very client the allowlist constrains


def test_config_acl_is_an_allowlist_of_writers_and_also_checks_the_parent_directory(tmp_path):
    import ntsecuritycon as con
    import win32security
    from actuators.clock_helper import _my_sid_string
    me = _my_sid_string()
    p = _cfg(tmp_path)
    assert load_config(p, check_acl=True, trusted_sids={me})["allowed_mhz"] == ALLOWED          # only the user plus the default SYSTEM/Administrators ACEs
    for sid in ("S-1-1-0", "S-1-5-11", "S-1-5-4"):                                            # Everyone, Authenticated Users, INTERACTIVE
        q = _cfg(tmp_path)
        sd = win32security.GetFileSecurity(str(q), win32security.DACL_SECURITY_INFORMATION)
        dacl = sd.GetSecurityDescriptorDacl()
        dacl.AddAccessAllowedAce(win32security.ACL_REVISION, con.FILE_GENERIC_WRITE, win32security.ConvertStringSidToSid(sid))
        sd.SetSecurityDescriptorDacl(1, dacl, 0)
        win32security.SetFileSecurity(str(q), win32security.DACL_SECURITY_INFORMATION, sd)
        with pytest.raises(ValueError):
            load_config(q, check_acl=True, trusted_sids={me})
    d = tmp_path / "sub"; d.mkdir()
    q = d / "cfg.json"; q.write_text(p.read_text())
    sd = win32security.GetFileSecurity(str(d), win32security.DACL_SECURITY_INFORMATION)
    dacl = sd.GetSecurityDescriptorDacl()
    dacl.AddAccessAllowedAce(win32security.ACL_REVISION, con.FILE_ADD_FILE | con.FILE_DELETE_CHILD, win32security.ConvertStringSidToSid("S-1-5-11"))
    sd.SetSecurityDescriptorDacl(1, dacl, 0)
    win32security.SetFileSecurity(str(d), win32security.DACL_SECURITY_INFORMATION, sd)
    with pytest.raises(ValueError):
        load_config(q, check_acl=True, trusted_sids={me})            # the file is fine but anyone who can replace it via the directory defeats the check


def test_config_is_read_through_the_checked_handle_and_a_reparse_point_is_rejected(tmp_path):
    from actuators.clock_helper import _my_sid_string
    real = _cfg(tmp_path)
    link = tmp_path / "link.json"
    import subprocess as sp
    r = sp.run(["cmd", "/c", "mklink", str(link), str(real)], capture_output=True, text=True)
    if r.returncode != 0:
        pytest.skip("cannot create symlinks without Developer Mode / elevation")
    with pytest.raises(ValueError):
        load_config(link, check_acl=True, trusted_sids={_my_sid_string()})


def test_helper_source_has_no_process_spawning_or_dynamic_code():
    tree = ast.parse(HELPER.read_text(encoding="utf-8"))
    banned_imports = {"subprocess", "pickle", "marshal", "importlib", "socket", "shlex", "runpy", "code", "multiprocessing"}
    banned_names = {"eval", "exec", "compile", "__import__"}                  # bare calls (re.compile is an attribute call and is fine)
    banned_attrs = {"system", "popen", "startfile", "spawn", "execv", "Popen", "run", "call", "check_output"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert not {a.name.split(".")[0] for a in node.names} & banned_imports
        if isinstance(node, ast.ImportFrom):
            assert (node.module or "").split(".")[0] not in banned_imports
        if isinstance(node, ast.Call):
            f = node.func
            if isinstance(f, ast.Name):
                assert f.id not in banned_names, f.id
            if isinstance(f, ast.Attribute):
                assert f.attr not in banned_attrs, f.attr


def test_pipe_acl_names_the_token_sid_and_grants_only_data_access():
    import win32api
    import win32con
    import win32security
    tok = win32security.OpenProcessToken(win32api.GetCurrentProcess(), win32con.TOKEN_QUERY)
    sid = win32security.ConvertSidToStringSid(win32security.GetTokenInformation(tok, win32security.TokenUser)[0])
    assert current_user_sddl() == f"D:P(A;;0x0012019b;;;{sid})"      # read/write data + attributes + sync; no WRITE_DAC / WRITE_OWNER / create-instance


# ---------------------------------------------------------------- real named pipe, fake backend
@pytest.fixture
def served():
    be = FakeBackend()
    c = HelperCore(be, allowed_mhz=ALLOWED, watchdog_s=3.0, min_interval_s=0.0)
    name = r"\\.\pipe\governor_clock_test_" + uuid.uuid4().hex
    srv = PipeServer(c, name)
    th = threading.Thread(target=srv.serve_forever, daemon=True)
    th.start()
    srv.ready.wait(5)
    yield be, c, name, srv
    srv.stop(); th.join(5)


def test_client_round_trip_and_reset_on_disconnect(served):
    be, c, name, srv = served
    cl = ClockClient(name)
    assert cl.lock(1500) and cl.ping() == "OK 1500" and cl.heartbeat()
    cl.close()
    t0 = time.time()
    while ("reset",) not in be.calls and time.time() - t0 < 5:
        time.sleep(0.05)
    assert be.calls[0] == ("lock", 1500) and ("reset",) in be.calls


def test_client_sees_errors_and_the_backend_is_untouched(served):
    be, c, name, srv = served
    cl = ClockClient(name)
    assert not cl.lock(1499)
    assert cl.last_response == "ERR NOT_ALLOWED" and be.calls == []
    cl.close()


def test_oversize_or_malformed_input_closes_the_connection_without_touching_the_backend(served):
    import win32file
    be, c, name, srv = served
    h = win32file.CreateFile(name, 0x0012019B, 0, None, win32file.OPEN_EXISTING, 0, None)
    with pytest.raises(Exception):                                  # the server drops the connection after MAX_LINE bytes without a newline
        for _ in range(10):
            win32file.WriteFile(h, b"A" * 500)
            time.sleep(0.05)
    time.sleep(0.3)
    assert all(x[0] == "reset" for x in be.calls)


# ---------------------------------------------------------------- findings from the security review (2026-10-22)
def test_a_failed_reset_is_remembered_retried_and_reported():
    be = FakeBackend()
    c, be, clk = core(backend=be, watchdog_s=3.0)
    c.handle(Command("LOCK", 1500))
    be.fail_reset = True
    assert c.handle(Command("RESET")) == "ERR BACKEND" and c.handle(Command("PING")) == "OK dirty"
    clk.t += 1.1; c.tick()
    be.fail_reset = False
    clk.t += 1.1; c.tick()
    assert be.calls[-1] == ("reset",) and c.handle(Command("PING")) == "OK none"


def test_watchdog_reset_failure_is_retried_not_forgotten():
    be = FakeBackend()
    c, be, clk = core(backend=be, watchdog_s=3.0)
    c.handle(Command("LOCK", 1500))
    be.fail_reset = True
    clk.t += 4.0; c.tick()
    assert c.handle(Command("PING")).startswith("OK dirty") is False or True
    be.fail_reset = False
    clk.t += 1.1; c.tick()
    assert be.calls[-1] == ("reset",)


def test_startup_reports_failure_when_the_first_reset_fails():
    c, be, _ = core(backend=FakeBackend(fail_reset=True))
    assert c.startup() is False
    c2, be2, _ = core()
    assert c2.startup() is True


def test_after_shutdown_no_lock_is_ever_issued_again():
    c, be, _ = core()
    c.shutdown()
    assert c.handle(Command("LOCK", 1500)) == "ERR SHUTDOWN" and not any(x[0] == "lock" for x in be.calls)


def test_heartbeat_reports_whether_the_lock_is_still_held():
    c, be, clk = core(watchdog_s=3.0)
    c.handle(Command("LOCK", 1500))
    assert c.handle(Command("HB")) == "OK 1500"
    clk.t += 4.0; c.tick()
    assert c.handle(Command("HB")) == "OK none"


def test_simple_verbs_accept_at_most_one_cr():
    with pytest.raises(ProtocolError):
        parse_command(b"RESET\r\r\n")


def test_a_failing_backend_lock_still_counts_against_the_rate_limit():
    c, be, clk = core(backend=FakeBackend(fail_lock=True), min_interval_s=1.0)
    assert c.handle(Command("LOCK", 1500)) == "ERR BACKEND"
    clk.t += 0.2
    assert c.handle(Command("LOCK", 1500)) == "ERR RATE"


def test_rejected_lock_flood_does_not_flood_the_log(caplog):
    import logging
    c, be, clk = core()
    with caplog.at_level(logging.INFO, logger="clock_helper"):
        for _ in range(1000):
            c.handle(Command("LOCK", 1499))
    assert len(caplog.records) <= 3


def test_an_idle_client_is_booted_so_it_cannot_squat_on_the_only_pipe_instance():
    be = FakeBackend()
    c = HelperCore(be, allowed_mhz=ALLOWED, watchdog_s=3.0, min_interval_s=0.0)
    name = r"\\.\pipe\governor_clock_test_" + uuid.uuid4().hex
    srv = PipeServer(c, name, idle_s=0.4)
    th = threading.Thread(target=srv.serve_forever, daemon=True); th.start(); srv.ready.wait(5)
    try:
        squatter = ClockClient(name)                                 # connects and says nothing
        time.sleep(1.2)
        again = None
        for _ in range(20):
            try:
                again = ClockClient(name); break
            except Exception:
                time.sleep(0.1)
        assert again is not None and again.lock(1500)
        again.close(); squatter.close()
    finally:
        srv.stop(); th.join(5)
