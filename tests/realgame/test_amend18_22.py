"""Amendments 18 (clock load test), 19 (power cap), 20 (power audit), 21 (records), 22 (elevation). All with fakes; nothing here touches the GPU."""
import json
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

import rg_synth
from test_amend import ClockProbes
from test_cell import Clock, FakeProbes, FakeSampler, make_cfg, make_deps
from test_review2 import main_args
from tools.realgame import analyze as a
from tools.realgame import cell as c
from tools.realgame import clockcheck as cc
from tools.realgame import run as r

ROOT = Path(__file__).resolve().parents[2]


# ================================================================= 18. load test
class FakeTimeSrc:
    def __init__(self):
        self.t = 0.0

    def now(self):
        return self.t

    def sleep(self, s):
        self.t += s


class FakeClockReader:
    """sm_clock() gives idle_sm until the fake load has started, then load_sm. enforced_power_limit_w / reasons / pstate are information."""

    def __init__(self, load_sm=2100, idle_sm=1980, fail_sm=False, limit_w=95.0, reasons=0x4):
        self.load_sm, self.idle_sm, self.fail_sm, self.limit_w, self.reasons = load_sm, idle_sm, fail_sm, limit_w, reasons
        self.loaded = threading.Event()
        self.loads = 0

    def sm_clock(self):
        if self.fail_sm:
            raise RuntimeError("nvml gone")
        return self.load_sm if self.loaded.is_set() else self.idle_sm

    def pstate(self):
        return 0 if self.loaded.is_set() else 8

    def clock_reasons(self):
        return self.reasons if self.loaded.is_set() else 1

    def enforced_power_limit_w(self):
        return self.limit_w

    def load_fn(self, seconds):
        self.loads += 1
        self.seconds = seconds
        self.loaded.set()

    def failing_load_fn(self, seconds):
        self.loaded.set()
        raise RuntimeError("torch.cuda is not available")


def check(reader, load_fn=None, helper=(), **kw):
    ts = FakeTimeSrc()

    def sleep(s):
        ts.sleep(s)
        if ts.t >= cc.IDLE_INFO_S and load_fn is not reader.failing_load_fn:
            reader.loaded.wait(1.0)          # let the load thread start: the fake time does not wait for real threads
    return cc.run_check(reader, load_fn or reader.load_fn, helper_fn=lambda: list(helper), clock=ts.now, sleep=sleep, **kw), ts


def test_max_sm_1980_fails_1981_passes():
    (problems, state), _ = check(FakeClockReader(load_sm=1980))
    assert problems and state["max_sm_mhz"] == 1980 and "1980" in problems[0]
    (problems, state), _ = check(FakeClockReader(load_sm=1981))
    assert problems == [] and state["max_sm_mhz"] == 1981


def test_thresholds_recorded():
    assert cc.PASS_SM_MHZ_ABOVE == 1980
    t = cc.THRESHOLDS
    assert t["max_sm_mhz_above"] == 1980 and t["load_s"] == 5.0 and t["sample_interval_s"] == 0.05 and t["idle_info_s"] == 3.0 and t["constant_min_samples"] == 200


def test_helper_pipe_fails_even_with_high_clock():
    (problems, state), _ = check(FakeClockReader(load_sm=2500), helper=["named pipe is listed"])
    assert state["max_sm_mhz"] == 2500 and len(problems) == 1 and "clock helper" in problems[0] and state["helper_present"] == ["named pipe is listed"]


def test_load_fn_error_fails_the_check():
    rd = FakeClockReader(load_sm=2500)
    (problems, state), _ = check(rd, load_fn=rd.failing_load_fn)
    assert any("load test failed" in p and "torch.cuda is not available" in p for p in problems)
    assert state["load_test"]["load_error"] and "torch.cuda is not available" in state["load_test"]["load_error"]


def test_reader_error_fails_the_check():
    (problems, state), _ = check(FakeClockReader(fail_sm=True))
    assert problems and state["max_sm_mhz"] is None


def test_idle_samples_are_information_only():
    rd = FakeClockReader(load_sm=2100, idle_sm=1999)                 # a high idle clock: the OLD heuristic called this locked
    (problems, state), ts = check(rd)
    assert problems == []
    info = state["load_test"]["info"]
    assert info["idle_sm_mhz"] and set(info["idle_sm_mhz"]) == {1999} and ts.t >= 3.0 + 5.0 - 0.1
    assert info["pstate_idle"] == [8]


def test_info_block_records_pstate_power_limit_and_reasons_mask_during_load():
    (problems, state), _ = check(FakeClockReader(limit_w=95.0, reasons=0x4))
    info = state["load_test"]["info"]
    assert info["power_limit_w"] == 95.0 and info["clock_reasons_mask_or"] & 0x4 and info["pstate_load"] == [0]
    assert problems == []                                                 # a power limit of 92.77 is information here (the cell rule is amendment 19)


def test_load_is_asked_for_5_s_and_sampled_every_50_ms():
    rd = FakeClockReader()
    (_, state), ts = check(rd)
    assert rd.seconds == 5.0 and rd.loads == 1
    n = state["load_test"]["n_load_samples"]
    assert 95 <= n <= 105


def test_no_inconclusive_status_remains():
    src = (ROOT / "tools" / "realgame" / "clockcheck.py").read_text()
    assert "inconclusive" not in src and "probe_idle" not in src and "IDLE_SM_MHZ_ABOVE" not in src and "query_reader" not in src


def test_default_load_fn_fails_loudly_without_cuda():
    torch = SimpleNamespace(cuda=SimpleNamespace(is_available=lambda: False))
    with pytest.raises(RuntimeError, match="(?i)cuda.*no CPU fallback"):
        cc.default_load_fn(1.0, torch_module=torch)


def test_default_load_fn_runs_fp16_matmuls_then_synchronizes_and_empties_cache():
    calls = []

    class T:
        def __matmul__(self, o):
            calls.append("matmul")
            return T()
    torch = SimpleNamespace(float16="fp16", cuda=SimpleNamespace(is_available=lambda: True, synchronize=lambda: calls.append("sync"), empty_cache=lambda: calls.append("empty")),
                            randn=lambda *a, **k: (calls.append(("randn", a, k.get("dtype"), k.get("device"))), T())[1])
    t = [0.0]

    def clock():
        t[0] += 0.1
        return t[0]
    cc.default_load_fn(1.0, torch_module=torch, clock=clock)
    assert calls.count("matmul") >= 2 and calls[-2:] == ["sync", "empty"] and ("randn", (8192, 8192), "fp16", "cuda") in calls


def test_default_load_fn_cleans_up_even_if_a_kernel_fails():
    calls = []

    class T:
        def __matmul__(self, o):
            raise RuntimeError("CUDA error")
    torch = SimpleNamespace(float16="fp16", cuda=SimpleNamespace(is_available=lambda: True, synchronize=lambda: calls.append("sync"), empty_cache=lambda: calls.append("empty")),
                            randn=lambda *a, **k: T())
    with pytest.raises(RuntimeError, match="CUDA error"):
        cc.default_load_fn(1.0, torch_module=torch)
    assert calls == ["sync", "empty"]


# ----- the cell-level and run.py wiring of the load test
def test_clock_state_check_applies_verdict_to_probe_results():
    p = ClockProbes(game=False, load={"max_sm_mhz": 1980, "load_error": None, "power_limit_max_w": 95.0, "info": {}})
    problems, state = c.clock_state_check(p, "game.exe", run_load=True)
    assert problems and state["max_sm_mhz"] == 1980 and p.load_calls == 1
    p = ClockProbes(game=False, load={"max_sm_mhz": None, "load_error": "RuntimeError: no cuda", "info": {}})
    assert any("no cuda" in x for x in c.clock_state_check(p, "game.exe", run_load=True)[0])
    p = ClockProbes(game=False, helper=["pipe"], load={"max_sm_mhz": 2500, "load_error": None, "power_limit_max_w": 95.0, "info": {}})
    assert len(c.clock_state_check(p, "game.exe", run_load=True)[0]) == 1
    p = ClockProbes(game=False)
    problems, state = c.clock_state_check(p, "game.exe")                # no load: helper only
    assert problems == [] and p.load_calls == 0 and state["load_test"] is None


def test_check_clocks_file_carries_the_documented_fields(tmp_path):
    run = tmp_path / "run"
    load = {"max_sm_mhz": 2010, "load_error": None, "n_load_samples": 100, "power_limit_max_w": 95.0, "info": {"idle_sm_mhz": [210], "power_limit_w": 95.0, "clock_reasons_mask_or": 4, "pstate_idle": [8]}}
    assert r.main(main_args(tmp_path, "--check-clocks", "--run-dir", str(run)), probes=ClockProbes(game=False, load=load)) == 0
    doc = json.loads((run / "clock_check.json").read_text())
    for k in ("status", "timestamp", "max_sm_mhz", "thresholds", "info", "problems"):
        assert k in doc, k
    assert doc["status"] == "passed" and doc["max_sm_mhz"] == 2010 and doc["info"]["power_limit_w"] == 95.0 and doc["thresholds"]["max_sm_mhz_above"] == 1980


def test_check_clocks_refused_file_lists_problem(tmp_path):
    run = tmp_path / "run"
    load = {"max_sm_mhz": 1700, "load_error": None, "power_limit_max_w": 95.0, "info": {}}
    assert r.main(main_args(tmp_path, "--check-clocks", "--run-dir", str(run)), probes=ClockProbes(game=False, load=load)) == 2
    doc = json.loads((run / "clock_check.json").read_text())
    assert doc["status"] == "refused" and doc["max_sm_mhz"] == 1700 and doc["problems"]


def test_high_idle_clock_does_not_fail_the_cell_flow(tmp_path):
    clock = Clock()
    cfg = make_cfg(tmp_path)
    d, _ = make_deps(cfg, clock)
    d.probes = ClockProbes(game=False)
    assert c.run_cell("LLM_ALONE", 0, tmp_path / "cell", cfg, d)["arm"] == "LLM_ALONE"


# ================================================================= 20. power audit
SCANNED = ("decision.py", "metrics.py", "analyze.py")
SAMPLED_POWER_TOKENS = ("sampled_power", "power_rejected", "power_usage", "powerusage", "sampler.power", ".power_w(", "nvmlDeviceGetPowerUsage")


def test_decision_metrics_analyze_never_reference_sampled_power():
    for n in SCANNED:
        low = (ROOT / "tools" / "realgame" / n).read_text(encoding="utf-8").lower()
        for tok in SAMPLED_POWER_TOKENS:
            assert tok.lower() not in low, (n, tok)


def test_analyze_cell_summary_power_is_the_result_power_w_field_only(tmp_path):
    d = tmp_path / "c"
    d.mkdir()
    (d / "result.json").write_text(json.dumps({"arm": "SOLO", "rep": 0, "t_open": 0.0, "t_close": 1.0, "power_w": 80.0, "energy_j": 80.0, "sampled_power_mean_w": 999.0, "power_rejected": 3}))
    s = a.cell_summary(d)
    assert s["power_w"] == 80.0 and "sampled_power_mean_w" not in s and "power_rejected" not in s


class PowerNvml:
    def __init__(self, values):
        self.values = list(values)

    def sm_clock(self):
        return 1500

    def throttle(self):
        return 0

    def temp_c(self):
        return 60.0

    def power_w(self):
        v = self.values.pop(0)
        if isinstance(v, Exception):
            raise v
        return v


def guard140():
    from telemetry.power_guard import PowerGuard
    return PowerGuard(140.0)


def test_sampler_rejects_the_588_w_glitch_counts_it_and_keeps_normal_samples():
    s = c.Sampler50(PowerNvml([70.0, 588.0, 72.0, 210.0, 210.01]), 0.05, guard=guard140())
    for _ in range(5):
        s.sample_once()
    assert s.power == [70.0, None, 72.0, 210.0, None] and s.power_rejected == [False, True, False, False, True]
    assert s.power_errors == 0


def test_sampler_read_error_is_counted_not_swallowed_silently():
    s = c.Sampler50(PowerNvml([RuntimeError("x"), 70.0]), 0.05, guard=guard140())
    s.sample_once()
    s.sample_once()
    assert s.power_errors == 1 and s.power == [None, 70.0] and s.power_rejected == [False, False]


def test_sampler_stats_count_only_the_window_and_report_mean_of_accepted():
    s = c.Sampler50(PowerNvml([]), 0.05, guard=guard140())
    s.t = [1.0, 2.0, 3.0, 4.0, 5.0]
    s.sm, s.throttle, s.temp = [1500] * 5, [0] * 5, [60] * 5
    s.power = [None, 60.0, None, 80.0, 99.0]
    s.power_rejected = [True, False, True, False, False]
    st = c._sampler_stats(s, 2.0, 5.0)                                  # samples at 2, 3, 4
    assert st["sampled_power_n"] == 2 and st["sampled_power_mean_w"] == 70.0 and st["power_rejected"] == 1


def test_sampler_stats_without_power_samples():
    st = c._sampler_stats(FakeSampler(Clock()), 1000.0, 1010.0)
    assert st["sampled_power_n"] == 0 and st["sampled_power_mean_w"] is None and st["power_rejected"] == 0


class PowerSampler(FakeSampler):
    def __init__(self, clock, values, rejected):
        super().__init__(clock)
        n = len(self.t)
        self.power = [values[i % len(values)] for i in range(n)]
        self.power_rejected = [rejected[i % len(rejected)] for i in range(n)]


@pytest.mark.parametrize("arm,game", [("SOLO", True), ("UNGATED", True), ("LLM_ALONE", False)])
def test_result_power_w_is_energy_over_elapsed_whatever_the_samples_say(tmp_path, arm, game):
    clock = Clock()
    cfg = make_cfg(tmp_path)
    d, _ = make_deps(cfg, clock)
    d.probes = FakeProbes(game=game)
    d.make_sampler = lambda nv: PowerSampler(clock, [588.0, 10.0, None], [False, False, True])
    res = c.run_cell(arm, 0, tmp_path / "cell", cfg, d)
    te0, te1 = res["energy_read_t"]
    assert res["power_w"] == pytest.approx(res["energy_j"] / (te1 - te0)) and res["power_w"] == pytest.approx(90.0)
    on_disk = json.loads((tmp_path / "cell" / "result.json").read_text())
    for k in ("sampled_power_n", "sampled_power_mean_w", "power_rejected"):
        assert k in on_disk, k
    assert on_disk["power_rejected"] > 0 and on_disk["sampled_power_n"] > 0


def test_energy_comes_from_exactly_two_counter_reads_per_window(tmp_path):
    clock = Clock()
    cfg = make_cfg(tmp_path)
    d, _ = make_deps(cfg, clock)
    reads = []
    real = d.nvml.energy_mj
    d.nvml.energy_mj = lambda: (reads.append(clock.now()), real())[1]
    c.run_cell("SOLO", 0, tmp_path / "cell", cfg, d)
    assert len(reads) == 2


# ================================================================= 21. records
def test_idle_vram_is_read_before_the_llm_is_launched(tmp_path):
    clock, order = Clock(), []
    cfg = make_cfg(tmp_path)
    d, _ = make_deps(cfg, clock, order=order)
    real = d.nvml.vram_used_mb
    d.nvml.vram_used_mb = lambda: (order.append(("vram",)), real())[1]
    res = c.run_cell("UNGATED", 0, tmp_path / "cell", cfg, d)
    assert order[0] == ("vram",) and order[1][0] == "spawn"
    assert res["idle_vram_mib"] == 2048.0
    assert json.loads((tmp_path / "cell" / "result.json").read_text())["idle_vram_mib"] == 2048.0
    assert json.loads((tmp_path / "cell" / "meta.json").read_text())["idle_vram_mib"] == 2048.0


def test_idle_vram_is_the_value_at_cell_start_not_the_later_reading(tmp_path):
    clock = Clock()
    cfg = make_cfg(tmp_path)
    d, _ = make_deps(cfg, clock)
    vals = iter([300.0, 5000.0, 5001.0, 5002.0])
    d.nvml.vram_used_mb = lambda: next(vals)
    res = c.run_cell("UNGATED", 0, tmp_path / "cell", cfg, d)
    assert res["idle_vram_mib"] == 300.0 and res["vram_mb"]["start"] == 5000.0


def test_sweep_start_records_content():
    rec = c.sweep_start_records(FakeProbes())
    assert rec["nvidia_smi_processes"] == "NVSMI FAKE TABLE\nProcesses: none\n"
    assert rec["display_active"] == "Disabled" and rec["display_mode"] == "Disabled"
    assert rec["nvml_name"] == "FAKE RTX 4070 Laptop GPU" and rec["nvml_driver_version"] == "999.99" and rec["vram_total_mib"] == 8188.0


def test_sweep_start_records_survive_failures_and_say_so():
    class Bad(FakeProbes):
        def nvidia_smi_text(self):
            raise OSError("no tool")

        def nvml_identity(self):
            raise RuntimeError("no nvml")
    rec = c.sweep_start_records(Bad())
    assert "unavailable" in rec["nvidia_smi_processes"] and "no tool" in rec["nvidia_smi_processes"]
    assert "unavailable" in str(rec["nvml_name"]) and rec["display_active"] == "Disabled"


def test_nvidia_smi_is_resolved_by_full_path_with_fixed_argv_and_no_shell(monkeypatch, tmp_path):
    exe = tmp_path / "System32" / "nvidia-smi.exe"
    exe.parent.mkdir()
    exe.write_text("x")
    calls = []

    def fake_run(argv, **kw):
        calls.append((argv, kw))
        return SimpleNamespace(stdout="TABLE\n", returncode=0)
    monkeypatch.setattr(c.subprocess, "run", fake_run)
    monkeypatch.setenv("SystemRoot", str(tmp_path))
    monkeypatch.setattr(c, "_NVSMI_EXTRA", ())
    assert c.SystemProbes().nvidia_smi_text() == "TABLE\n"
    argv, kw = calls[0]
    assert argv == [str(exe)] and not kw.get("shell")
    calls.clear()
    monkeypatch.setattr(c.subprocess, "run", lambda argv, **kw: (calls.append(argv), SimpleNamespace(stdout="Disabled, Enabled\n", returncode=0))[1])
    got = c.SystemProbes().nvidia_smi_display()
    assert got == {"display_active": "Disabled", "display_mode": "Enabled"}
    assert calls[0] == [str(exe), "--query-gpu=display_active,display_mode", "--format=csv,noheader"]


def test_nvidia_smi_missing_raises(monkeypatch, tmp_path):
    monkeypatch.setenv("SystemRoot", str(tmp_path))
    monkeypatch.setattr(c, "_NVSMI_EXTRA", ())
    with pytest.raises(RuntimeError, match="nvidia-smi"):
        c.SystemProbes().nvidia_smi_text()


def run_main_with(tmp_path, *extra, probes=None):
    rg_synth.write_fresh_clock_check(tmp_path / "run")
    runner = lambda arm, rep, out, cfg: (out.mkdir(parents=True, exist_ok=True), (out / "result.json").write_text(json.dumps({"arm": arm, "rep": rep, "frame": {"p99": 20.0, "hitch_share": 0.1}})))
    return r.main(main_args(tmp_path, "--run-dir", str(tmp_path / "run"), "--drop-igpu", "synthetic", "--reps", "1", *extra), probes=probes or FakeProbes(), runner=runner)


def test_run_meta_has_the_records_for_the_sweep_and_for_llm_alone(tmp_path):
    assert run_main_with(tmp_path) == 0
    meta = json.loads((tmp_path / "run" / "run_meta.json").read_text())
    assert meta["nvidia_smi_processes"].startswith("NVSMI FAKE") and meta["display_active"] == "Disabled" and meta["display_mode"] == "Disabled"
    assert meta["nvml_name"].startswith("FAKE") and meta["nvml_driver_version"] == "999.99" and meta["vram_total_mib"] == 8188.0
    t2 = tmp_path / "two"
    t2.mkdir()
    assert run_main_with(t2, "--llm-alone", probes=FakeProbes(game=False)) == 0
    meta = json.loads((t2 / "run" / "run_meta.json").read_text())
    assert meta["nvidia_smi_processes"].startswith("NVSMI FAKE") and meta["display_active"] == "Disabled" and meta["nvml_name"].startswith("FAKE")


def test_second_invocation_keeps_the_first_records_in_history(tmp_path):
    assert run_main_with(tmp_path) == 0
    assert run_main_with(tmp_path, "--llm-alone", probes=FakeProbes(game=False)) == 0
    meta = json.loads((tmp_path / "run" / "run_meta.json").read_text())
    assert len(meta["earlier_start_records"]) == 1 and meta["earlier_start_records"][0]["nvidia_smi_processes"].startswith("NVSMI")


# ================================================================= 22. elevation
class ElevProbes(FakeProbes):
    def __init__(self, elevated, **kw):
        super().__init__(**kw)
        self.elevated = elevated

    def is_elevated(self):
        return self.elevated


@pytest.mark.parametrize("arm,game", [("SOLO", True), ("UNGATED", True), ("LLM_ALONE", False)])
@pytest.mark.parametrize("elev", [True, False])
def test_result_json_records_elevated(tmp_path, arm, game, elev):
    clock = Clock()
    cfg = make_cfg(tmp_path)
    d, _ = make_deps(cfg, clock)
    d.probes = ElevProbes(elev, game=game)
    res = c.run_cell(arm, 0, tmp_path / "cell", cfg, d)
    assert res["elevated"] is elev and json.loads((tmp_path / "cell" / "result.json").read_text())["elevated"] is elev


def set_elevation(root, alone, arms):
    for p in Path(root).rglob("result.json"):
        doc = json.loads(p.read_text())
        doc["elevated"] = alone if doc["arm"] == "LLM_ALONE" else arms
        p.write_text(json.dumps(doc))


def test_analyze_states_same_elevation(tmp_path):
    rg_synth.build_tree(tmp_path / "t")
    set_elevation(tmp_path / "t", True, True)
    s = a.analyze(tmp_path / "t")
    assert s["elevation"]["same"] is True and s["elevation"]["llm_alone"] is True and s["elevation"]["arms"] == [True]
    md = a._markdown(s)
    assert "same elevation" in md and "differ" not in md


def test_analyze_prints_sentence_when_elevation_differs(tmp_path, capsys):
    rg_synth.build_tree(tmp_path / "t")
    set_elevation(tmp_path / "t", False, True)
    s = a.analyze(tmp_path / "t")
    assert s["elevation"]["same"] is False
    assert "differ" in s["elevation"]["sentence"] and "not elevated" in s["elevation"]["sentence"]
    assert s["elevation"]["sentence"] in a._markdown(s)
    assert a.main(["--run-dir", str(tmp_path / "t"), "--out", str(tmp_path / "out"), "--no-plots"]) == 0
    assert "differ" in capsys.readouterr().out


def test_analyze_unknown_elevation_is_not_called_the_same(tmp_path):
    rg_synth.build_tree(tmp_path / "t")
    for p in Path(tmp_path / "t").rglob("result.json"):
        doc = json.loads(p.read_text())
        doc.pop("elevated", None)
        p.write_text(json.dumps(doc))
    s = a.analyze(tmp_path / "t")
    assert s["elevation"]["same"] is False and "unknown" in s["elevation"]["sentence"]
