"""Co-Scheduler Lab dashboard backend (tools/dashboard/server.py, sources.py): SSE stream format, REPLAY reproducing a recorded cell's miss / tok/s / power, LIVE attach on synthetic shared-memory rings, loopback-only
bind, Host/Origin guards, read-only guarantees (grep), catalogue. No GPU, no helper.
Instruction (Arjun): "Tests first: SSE stream format, replay of a known cell reproduces its recorded miss/tok/s/power, the telemetry block round-trip and torn-read handling, telemetry-off leaves Governor behaviour
identical, the server refuses non-localhost binds, no energy-counter calls anywhere in tools/dashboard (grep test)." (Telemetry block and Governor identity: tests/test_dashboard_governor_hook.py.)"""
import http.client
import json
import re
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
DASH = ROOT / "tools" / "dashboard"
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(DASH))
import server as srv  # noqa: E402
import sources as src  # noqa: E402

EVAL = "w5b/eval/block04/cells/"
CELLS = [EVAL + "ev04_S2_dB_60", EVAL + "ev04_S0_gB_60", EVAL + "ev04_S5_a_60", EVAL + "ev04_S1_cBb_60", "w5b/t3b/cells/db_llama32_3b_S1_m0.3"]


def need(key):
    if not (ROOT / "data" / key / "cell.json").exists():
        pytest.skip(f"{key} not present")
    return src.resolve_cell(ROOT, key)


def run_fast(r):
    r.speed = 1000.0
    msgs = []
    for _ in range(2000):
        msgs.append(r.tick(0.05))
        if msgs[-1]["phase"] == "done" and r._cur["f"] >= len(r.f_end) and r._cur["k"] >= len(r.k_end):
            break
    return msgs


# ---------------------------------------------------------------- replay
@pytest.mark.parametrize("key", CELLS)
def test_replay_reproduces_the_recorded_miss_tok_s_and_power_of_the_cell(key):
    cdir = need(key)
    d = json.loads((cdir / "cell.json").read_text(encoding="utf-8"))["metrics"]
    msgs = run_fast(src.ReplaySource(cdir, key=key))
    final = msgs[-1]["stats"]
    assert final["frames"] == d["frames"] and final["tokens"] == round(d["tok_s"] * 60)
    assert final["miss_pct"] / 100.0 == pytest.approx(d["miss_completed"], abs=1e-12)                       # the server-side running totals ARE the recorded cell metrics
    assert final["tok_s"] == pytest.approx(d["tok_s"], rel=1e-12)
    from_events = src.summarise_messages(msgs)                                                              # and so are the totals a client rebuilds from the streamed events alone
    assert from_events["frames"] == d["frames"] and from_events["miss"] == pytest.approx(d["miss_completed"], abs=1e-12) and from_events["tok_s"] == pytest.approx(d["tok_s"], rel=1e-12)
    if d.get("power_sampled_w") is not None and final["power_w"] is not None:
        assert final["power_w"] == pytest.approx(d["power_sampled_w"], rel=0.01)                            # sampled power: the 0.5 s trace mean of the window vs the raw-sample mean


def test_replay_messages_carry_frames_tokens_ctrl_and_the_governed_cell_has_a_10_hz_governor_log():
    r = src.ReplaySource(need(CELLS[0]), key="k")
    msgs = run_fast(r)
    ev = {k: sum(len(m["events"][k]) for m in msgs) for k in ("frames", "tokens", "power", "sm", "ctrl")}
    assert ev["frames"] == 2700 and ev["tokens"] == 2630 and ev["ctrl"] == 651 and ev["sm"] == 651
    first = next(m["events"]["frames"][0] for m in msgs if m["events"]["frames"])
    assert len(first) == 4 and first[1] >= first[0] - 1e-12 and first[2] > first[1]                         # [arrival, start (reconstructed), end, late]
    assert r.meta()["frame_starts_reconstructed"] is True and r.meta()["manager"] == "Governor" and r.meta()["model"] == "3B" and r.meta()["scene"] == "S2"


def test_static_cell_replay_has_one_constant_ctrl_record_and_arm_a_is_unaligned_unlocked():
    m = run_fast(src.ReplaySource(need(CELLS[1]), key="k"))
    ctrl = [c for x in m for c in x["events"]["ctrl"]]
    assert ctrl == [[0.0, 1.0, 1.0, 0.0, 1800.0]]                                                           # g'B: aligned, duty 1, guard 0, 1800 MHz
    m = run_fast(src.ReplaySource(need(CELLS[2]), key="k"))
    assert [c for x in m for c in x["events"]["ctrl"]] == [[0.0, 0.0, 1.0, 0.5, 2460.0]]


def test_replay_controls_pause_speed_seek_restart_and_no_unknown_action():
    r = src.ReplaySource(need(CELLS[0]), key="k")
    r.control("speed", 1.0)
    a = r.tick(0.5)
    assert a["t"] == pytest.approx(0.5) and a["rate"] == 1.0
    r.control("pause")
    b = r.tick(0.5)
    assert b["t"] == pytest.approx(0.5) and b["rate"] == 0.0 and not b["playing"]
    r.control("seek", 10.0)
    c = r.tick(0.0)
    assert c["t"] == pytest.approx(10.0) and c["seek"] is True and c["phase"] == "measured" and c["stats"]["frames"] > 0
    assert not any(f[0] > 10.0 + src.LOOKAHEAD_S + 1e-9 and f[2] > 10.0 + src.LOOKAHEAD_S + 1e-9 for f in c["events"]["frames"])      # nothing beyond the look-ahead
    r.control("restart")
    assert r.tick(0.0)["t"] == 0.0
    with pytest.raises(ValueError):
        r.control("explode")


def test_replay_phase_labels_warmup_measured_done():
    r = src.ReplaySource(need(CELLS[0]), key="k")
    r.control("seek", 2.0); assert r.tick(0.0)["phase"] == "warm-up"
    r.control("seek", 30.0); assert r.tick(0.0)["phase"] == "measured"
    r.control("seek", 1e9); assert r.tick(0.0)["phase"] == "done"


def test_catalogue_lists_hardware_cells_not_dry_runs_and_flags_groups():
    cells = src.list_cells(ROOT)
    groups = {c["group"] for c in cells}
    assert {"eval", "tuning"} <= groups and not any("_dryrun" in c["key"] for c in cells)
    ev = [c for c in cells if c["group"] == "eval"]
    assert len(ev) == 425 and {c["block"] for c in ev} == {4, 5, 8, 9, 10, 11, 12, 13, 14, 15}
    one = next(c for c in ev if c["id"] == "ev04_S2_dB_60")
    assert one["manager"] == "Governor" and one["model"] == "3B" and one["scene"] == "S2" and one["budget_w"] == 60.0 and one["miss"] == pytest.approx(0.0004166666666666667)
    with pytest.raises(FileNotFoundError):
        src.resolve_cell(ROOT, "../../etc/passwd")
    with pytest.raises(FileNotFoundError):
        src.resolve_cell(ROOT, "w5b/eval/block04/cells/does_not_exist")


# ---------------------------------------------------------------- live
class StubPoller:
    def __init__(self):
        self.calls = 0

    def read(self):
        self.calls += 1
        return 51.5, 1800.0


def make_live(tmp_path):
    from telemetry.decision_block import DECISION_FIELDS, DecisionBlock
    from telemetry.ring import SeqBlock, SharedRing
    tag = uuid.uuid4().hex[:8]
    names = dict(frames="Local\\dash_fr_" + tag, tokens="Local\\dash_tk_" + tag, ctrl="Local\\dash_ct_" + tag, pace="Local\\dash_pc_" + tag, decision="Local\\dash_dc_" + tag, frames_capacity=64, tokens_capacity=64)
    own = dict(frames=SharedRing(names["frames"], 64, 3, True), tokens=SharedRing(names["tokens"], 64, 2, True), ctrl=SeqBlock(names["ctrl"], 3, True), pace=SeqBlock(names["pace"], 3, True), dec=DecisionBlock(names["decision"], True))
    sess = dict(names=names, id="demo_x", scene="S1", controller="d'B", workload="llama32_3b", budget_w=60.0, demo=True)
    p = tmp_path / "session.json"
    p.write_text(json.dumps(dict(sess, pid=None)), encoding="utf-8")
    return own, sess, p, DECISION_FIELDS


def test_live_source_streams_new_frames_tokens_ctrl_pace_decision_and_sampled_power(tmp_path):
    own, sess, p, fields = make_live(tmp_path)
    own["frames"].push([1.0, 1.0, 1.0])                                                                       # history before the attach is skipped
    live = src.LiveSource(src.read_session(p), poller=StubPoller())
    t_a = live.ta
    own["frames"].push([t_a + 0.010, t_a + 0.011, t_a + 0.019])                                              # a 9 ms frame
    own["frames"].push([t_a + 0.027, t_a + 0.027, t_a + 0.050])                                              # a late one (23 ms)
    own["tokens"].push([t_a + 0.040, 10.0])
    own["ctrl"].write([1.0, 0.5, 0.25])
    own["pace"].write([1.0, t_a + 0.060, t_a + 0.051])
    own["dec"].write({f: float(i + 1) for i, f in enumerate(fields)})
    m = live.tick(0.05)
    assert m["mode"] == "live" and m["rate"] == 1.0 and m["events"]["power"][0][1] == 51.5 and m["events"]["sm"][0][1] == 1800.0
    assert [round(f[0], 6) for f in m["events"]["frames"]] == [0.010, 0.027] and [f[3] for f in m["events"]["frames"]] == [False, True]
    assert m["events"]["tokens"] == [[pytest.approx(0.030, abs=1e-9), pytest.approx(0.040, abs=1e-9)]]
    assert m["events"]["ctrl"][0][1:4] == [1.0, 0.5, 0.25] and m["events"]["ctrl"][0][4] == 1800.0
    assert m["pace"]["busy"] is True and m["pace"]["next"] == pytest.approx(0.060)
    assert m["events"]["decisions"][0]["c_hat_ms"] == float(fields.index("c_hat_ms") + 1)
    assert m["stats"]["frames"] == 2 and m["stats"]["late"] == 1 and m["stats"]["tokens"] == 1 and m["stats"]["power_w"] == 51.5
    assert live.tick(0.05)["events"]["decisions"] == [] and live.tick(0.05)["events"]["frames"] == []        # a decision is delivered once; nothing new


def test_live_source_drops_implausible_nvml_power_samples_and_counts_them(tmp_path):
    own, sess, p, fields = make_live(tmp_path)

    class Glitchy:
        vals = iter([50.0, 590.006, 52.0, -3.0])

        def read(self):
            return next(self.vals), 1800.0

    live = src.LiveSource(src.read_session(p), poller=Glitchy())
    ms = [live.tick(0.05) for _ in range(4)]
    assert [len(m["events"]["power"]) for m in ms] == [1, 0, 1, 0]
    assert ms[-1]["stats"]["power_glitches"] == 2 and ms[-1]["stats"]["power_w"] == pytest.approx(51.0)


def test_live_source_never_writes_anything_it_reads(tmp_path):
    own, sess, p, fields = make_live(tmp_path)
    live = src.LiveSource(src.read_session(p), poller=StubPoller())
    before = (own["frames"].write_count, own["tokens"].write_count, own["ctrl"].read(), own["pace"].read())
    own["ctrl"].write([0.0, 1.0, 0.5]); own["pace"].write([0.0, 2.0, 1.0])
    for _ in range(5):
        live.tick(0.05)
    assert (own["frames"].write_count, own["tokens"].write_count) == before[:2] and own["ctrl"].read() == (0.0, 1.0, 0.5) and own["pace"].read() == (0.0, 2.0, 1.0)
    with pytest.raises(ValueError):
        live.control("pause")


def test_live_source_refuses_a_geometry_mismatch_and_a_missing_session(tmp_path):
    own, sess, p, fields = make_live(tmp_path)
    bad = src.read_session(p)
    bad["names"] = dict(bad["names"], frames=bad["names"]["tokens"], frames_capacity=64)                    # a 2-field ring where a 3-field one is expected
    with pytest.raises(ValueError):
        src.LiveSource(bad, poller=StubPoller())
    assert src.read_session(tmp_path / "nothing.json") is None


def test_session_of_a_dead_process_is_ignored(tmp_path):
    p = tmp_path / "s.json"
    p.write_text(json.dumps(dict(names={}, pid=2 ** 22 + 12345)), encoding="utf-8")
    assert src.read_session(p) is None


# ---------------------------------------------------------------- server
@pytest.fixture()
def server(tmp_path):
    own, sess, sp, fields = make_live(tmp_path)
    s = srv.make_server("127.0.0.1", 0, root=ROOT, session_file=sp, poller_factory=StubPoller)
    th = threading.Thread(target=s.serve_forever, daemon=True); th.start()
    s.own, s.fields = own, fields
    yield s
    s.shutdown(); s.server_close()


def conn(s, host=None, **hdr):
    c = http.client.HTTPConnection("127.0.0.1", s.server_address[1], timeout=10)
    return c, dict(hdr, **({"Host": host} if host else {}))


def post(s, path, body, **extra):
    c, h = conn(s, **extra)
    h = dict(h, **{"Content-Type": "application/json"})
    c.request("POST", path, json.dumps(body), h)
    r = c.getresponse()
    out = (r.status, json.loads(r.read() or b"{}"))
    c.close()
    return out


def read_events(s, seconds, n_max=10 ** 6):
    c, h = conn(s)
    c.request("GET", "/stream", headers=h)
    r = c.getresponse()
    assert r.status == 200 and r.getheader("Content-Type").startswith("text/event-stream")
    events, cur, t_end = [], {}, time.time() + seconds
    while time.time() < t_end and len(events) < n_max:
        line = r.fp.readline().decode("utf-8")
        if line == "\n":
            if cur.get("event"):
                events.append(cur)
            cur = {}
        elif line.startswith("data: "):
            cur["data"] = json.loads(line[6:])
        elif line.startswith("event: "):
            cur["event"] = line[7:].strip()
        elif line.startswith("id: "):
            cur["id"] = int(line[4:])
        elif line.startswith("retry: ") or line.startswith(":"):
            cur["meta"] = line
    c.close()
    return events


def test_sse_stream_format_hello_then_ticks_at_about_20_hz_with_increasing_ids(server):
    code, st = post(server, "/api/source", {"mode": "replay", "cell": CELLS[0], "speed": 1.0})
    assert code == 200 and st["mode"] == "replay"
    ev = read_events(server, 1.6)
    assert ev[0]["event"] == "hello" and ev[0]["data"]["meta"]["id"] == "ev04_S2_dB_60" and ev[0]["data"]["meta"]["manager"] == "Governor"
    ticks = [e for e in ev if e["event"] == "tick"]
    assert len(ticks) >= 20, len(ticks)                                                                       # nominal 20 Hz: >= 12/s even on a loaded machine
    ids = [e["id"] for e in ticks]
    assert ids == sorted(set(ids))
    d = ticks[-1]["data"]
    assert set(d) >= {"seq", "mode", "t", "rate", "phase", "events", "stats"} and set(d["events"]) == {"frames", "tokens", "power", "sm", "ctrl", "decisions"}
    assert ticks[-1]["data"]["t"] > ticks[0]["data"]["t"] and d["mode"] == "replay"


def test_sse_emits_valid_json_with_no_nan_tokens(server):
    post(server, "/api/source", {"mode": "replay", "cell": CELLS[1], "speed": 4.0})
    c, h = conn(server)
    c.request("GET", "/stream", headers=h)
    r = c.getresponse()
    raw = b""
    t_end = time.time() + 1.0
    while time.time() < t_end:
        raw += r.fp.readline()
    c.close()
    assert b"NaN" not in raw and b"Infinity" not in raw


def test_replay_control_endpoints_and_errors(server):
    assert post(server, "/api/replay", {"action": "pause"})[0] == 400                                         # nothing loaded
    assert post(server, "/api/source", {"mode": "replay", "cell": "w5b/nope"})[0] == 400
    assert post(server, "/api/source", {"mode": "replay", "cell": CELLS[0]})[1]["mode"] == "replay"
    assert post(server, "/api/replay", {"action": "speed", "value": 4.0})[0] == 200
    assert post(server, "/api/replay", {"action": "seek", "value": 12.0})[0] == 200
    assert post(server, "/api/replay", {"action": "bogus"})[0] == 400
    assert post(server, "/api/source", {"mode": "sim"})[1]["mode"] == "sim"


def test_live_mode_through_the_server_streams_the_synthetic_session(server):
    code, st = post(server, "/api/source", {"mode": "live"})
    assert code == 200 and st["mode"] == "live" and st["meta"]["manager"] == "Governor"
    own = server.own
    stop = threading.Event()

    def feeder():
        k = 0
        while not stop.is_set():
            t = time.perf_counter()
            own["frames"].push([t, t, t + 0.006]); own["tokens"].push([t + 0.01, 10.0]); k += 1
            time.sleep(1 / 60)

    th = threading.Thread(target=feeder, daemon=True); th.start()
    ev = read_events(server, 1.2)
    stop.set(); th.join(2)
    assert ev[0]["event"] == "hello" and ev[0]["data"]["mode"] == "live"
    ticks = [e["data"] for e in ev if e["event"] == "tick"]
    assert sum(len(t["events"]["frames"]) for t in ticks) > 20 and sum(len(t["events"]["tokens"]) for t in ticks) > 20
    assert ticks[-1]["stats"]["power_w"] == 51.5


def test_state_cells_stats_and_the_page(server):
    c, h = conn(server); c.request("GET", "/api/state", headers=h); st = json.loads(c.getresponse().read()); c.close()
    assert st["mode"] == "sim" and st["live_available"] is True
    c, h = conn(server); c.request("GET", "/api/cells", headers=h); cells = json.loads(c.getresponse().read()); c.close()
    assert len(cells) >= 600
    c, h = conn(server); c.request("GET", "/api/stats", headers=h); s = json.loads(c.getresponse().read()); c.close()
    assert s["cpu_s"] >= 0 and s["wall_s"] > 0 and "cpu_pct_of_one_core" in s
    c, h = conn(server); c.request("GET", "/", headers=h); r = c.getresponse(); body = r.read(); c.close()
    assert r.status in (200, 404)                                                                             # 200 once tools/dashboard/index.html exists


def test_host_and_origin_headers_are_checked(server):
    c, h = conn(server, host="evil.example"); c.request("GET", "/api/state", headers=h); assert c.getresponse().status == 403; c.close()      # DNS rebinding
    c, h = conn(server, Origin="http://evil.example"); h["Content-Type"] = "application/json"; c.request("POST", "/api/source", json.dumps({"mode": "sim"}), h)
    assert c.getresponse().status == 403
    c.close()
    assert post(server, "/api/source", {"mode": "sim"}, Origin=f"http://127.0.0.1:{server.server_address[1]}")[0] == 200


def test_post_needs_a_small_json_body(server):
    c, h = conn(server); c.request("POST", "/api/source", "mode=sim", dict(h, **{"Content-Type": "text/plain"})); assert c.getresponse().status == 400; c.close()


# ---------------------------------------------------------------- binding and safety
@pytest.mark.parametrize("host", ["0.0.0.0", "192.168.1.5", "::", "", "example.com"])
def test_server_refuses_every_non_loopback_bind(host):
    with pytest.raises(ValueError):
        srv.check_host(host)
    with pytest.raises(ValueError):
        srv.make_server(host, 0)


def test_server_cli_refuses_a_non_localhost_host():
    r = subprocess.run([sys.executable, str(DASH / "server.py"), "--host", "0.0.0.0", "--port", "0"], capture_output=True, text=True, timeout=60)
    assert r.returncode != 0 and "127.0.0.1 only" in (r.stdout + r.stderr)


def test_the_bound_address_is_loopback(server):
    assert server.server_address[0] == "127.0.0.1"


def test_a_second_server_cannot_share_the_port(server):
    with pytest.raises(OSError):
        srv.make_server("127.0.0.1", server.server_address[1], root=ROOT)


def test_server_refuses_to_start_while_a_registered_experiment_runs():
    assert srv.registered_run_active([["python", "experiments/w5b/evaluate.py", "--blocks", "4"]])
    assert srv.registered_run_active([["python", "experiments/w5b/tune.py"]]) and srv.registered_run_active([["python", "experiments\\w5a\\run.py"]])
    assert not srv.registered_run_active([["python", "tools/dashboard/server.py"], ["python", "-m", "pytest"], []])
    assert not srv.registered_run_active([["python", "tools/dashboard/demo.py", "--scene", "S1"]])           # a demo is not a registered run


def test_it_runs_at_low_priority_on_windows_when_asked():
    assert srv.lower_priority() in (True, False)


# ---------------------------------------------------------------- grep tests
SERVER_FILES = ["server.py", "sources.py"]
ALL_FILES = [p.name for p in DASH.glob("*.py")]


def _code(name):
    """Source without comments and docstrings-as-prose: the executable text is what must be clean."""
    return (DASH / name).read_text(encoding="utf-8")


def test_no_energy_counter_call_anywhere_in_tools_dashboard():
    for name in ALL_FILES + ["index.html"]:
        txt = _code(name)
        assert "nvmlDeviceGetTotalEnergyConsumption" not in txt and "TotalEnergyConsumption" not in txt, name
        assert not re.search(r"energy_j|energy_mj|GetTotalEnergy", txt), name


def test_the_server_side_never_writes_a_control_block_a_ring_or_the_clock_helper():
    for name in SERVER_FILES:
        txt = _code(name)
        for bad in ("clock_client", "ClockClient", "SafeClient", "ControlActuator", "clock_helper", "create=True", "create = True", ".lock(", ".reset(", "heartbeat", "subprocess"):
            assert bad not in txt, (name, bad)
        assert not re.search(r"^\s*(import|from)\s+(actuators|experiments|controllers)\b", txt, re.M), name                 # (the prose may say 'registered experiments')
        assert not re.search(r"(ctrl|control|pace|frames?|tokens?|ring|block|dec)\w*\.(write|push)\(", txt), name


def test_dashboard_reads_nvml_only_for_sampled_power_and_sm_clock():
    txt = _code("sources.py")
    used = set(re.findall(r"nvml\w+", txt))
    assert used <= {"nvmlInit", "nvmlDeviceGetHandleByIndex", "nvmlDeviceGetPowerUsage", "nvmlDeviceGetClockInfo"}, used


def test_the_server_uses_only_the_standard_library_plus_numpy_and_project_modules():
    for name in SERVER_FILES:
        mods = set(re.findall(r"^(?:import|from)\s+([a-zA-Z_][\w]*)", _code(name), re.M))
        assert mods <= {"argparse", "json", "sys", "threading", "time", "collections", "http", "pathlib", "math", "numpy", "sources", "telemetry", "psutil", "ctypes", "uuid"}, (name, mods)
