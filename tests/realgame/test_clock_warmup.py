"""Clock load test: warm-up is split from the timed load (real-hardware defect: torch import and CUDA init took longer than the 5 s sampling window). Fakes only."""
import threading
import time
from types import SimpleNamespace

import pytest

from tools.realgame import clockcheck as cc


class Ts:
    def __init__(self):
        self.t = 0.0
        self.lock = threading.Lock()

    def now(self):
        return self.t

    def sleep(self, s):
        self.t += s


class Reader:
    def __init__(self, load_sm=2295, pstate_loaded=0, reasons_loaded=0x4):
        self.loaded = threading.Event()
        self.load_sm, self.pstate_loaded, self.reasons_loaded = load_sm, pstate_loaded, reasons_loaded

    def sm_clock(self):
        return self.load_sm if self.loaded.is_set() else 210

    def pstate(self):
        return self.pstate_loaded if self.loaded.is_set() else 8

    def clock_reasons(self):
        return self.reasons_loaded if self.loaded.is_set() else 1

    def enforced_power_limit_w(self):
        return 100.0


def run(reader, load_fn, **kw):
    ts = Ts()

    def sleep(s):
        ts.sleep(s)
        if ts.t >= cc.IDLE_INFO_S:
            reader.loaded.wait(0.2)

    return cc.load_test(reader, load_fn, clock=ts.now, sleep=sleep, **kw), ts


def test_slow_init_load_fn_still_samples_the_load_clocks():
    rd, seen = Reader(), {}
    holder = {}

    def load_fn(seconds, ready=None):
        seen["seconds"] = seconds
        holder["ts"].t += 7.0                      # 7 s of fake init time before the load really runs
        rd.loaded.set()
        ready.set()
    ts = Ts()
    holder["ts"] = ts

    def sleep(s):
        ts.sleep(s)
        if ts.t >= cc.IDLE_INFO_S:
            rd.loaded.wait(0.2)
    res = cc.load_test(rd, load_fn, clock=ts.now, sleep=sleep)
    assert res["load_error"] is None and res["max_sm_mhz"] == 2295
    assert res["n_load_samples"] >= 95 and set(res["info"]["pstate_load"]) == {0}
    assert seen["seconds"] == pytest.approx(cc.LOAD_S + 1.0)       # the load covers the whole sampling window


def test_samples_are_taken_only_after_ready():
    rd = Reader()
    release = threading.Event()

    def load_fn(seconds, ready):
        release.wait(2.0)
        rd.loaded.set()
        ready.set()
    threading.Timer(0.2, release.set).start()
    res, _ = run(rd, load_fn)
    assert res["max_sm_mhz"] == 2295 and 210 not in [res["max_sm_mhz"]]
    assert res["info"]["pstate_load"] == [0]


def test_load_fn_without_ready_still_works_and_gets_load_s():
    rd, seen = Reader(), {}

    def load_fn(seconds):
        seen["s"] = seconds
        rd.loaded.set()
    res, _ = run(rd, load_fn)
    assert seen["s"] == cc.LOAD_S and res["load_error"] is None and res["max_sm_mhz"] == 2295 and 95 <= res["n_load_samples"] <= 105


def test_ready_timeout_records_error_and_fails():
    rd = Reader()
    stop = threading.Event()

    def load_fn(seconds, ready):
        stop.wait(5.0)                             # never signals ready
    res, _ = run(rd, load_fn, ready_timeout_s=0.1)
    stop.set()
    assert res["load_error"] == "load warm-up did not finish in time"
    problems = cc.verdict([], res)
    assert problems and "load warm-up did not finish in time" in problems[0]


def test_load_fn_error_before_ready_does_not_wait_for_timeout():
    rd = Reader()

    def load_fn(seconds, ready):
        raise RuntimeError("no cuda")
    t0 = time.monotonic()
    res, _ = run(rd, load_fn)
    assert time.monotonic() - t0 < 5.0 and "no cuda" in res["load_error"]


def test_verdict_idle_looking_load_gets_the_did_not_reach_gpu_text():
    load = {"max_sm_mhz": 210, "load_error": None, "info": {"pstate_load": [8], "clock_reasons_mask_or": 0x1}}
    problems = cc.verdict([], load)
    assert len(problems) == 1 and "the load did not reach the GPU (still P8 and idle during the load); this is not a clock lock" in problems[0]
    assert "locked" not in problems[0]


@pytest.mark.parametrize("info", [{"pstate_load": [8, 0], "clock_reasons_mask_or": 0x1}, {"pstate_load": [8], "clock_reasons_mask_or": 0x5}, {"pstate_load": [0], "clock_reasons_mask_or": 0x1}])
def test_verdict_keeps_the_old_text_when_not_idle_looking(info):
    problems = cc.verdict([], {"max_sm_mhz": 1500, "load_error": None, "info": info})
    assert len(problems) == 1 and "clocks look limited or locked" in problems[0]


def test_verdict_boundaries_unchanged_even_with_idle_info():
    idle = {"pstate_load": [8], "clock_reasons_mask_or": 0x1}
    assert cc.verdict([], {"max_sm_mhz": 1980, "load_error": None, "info": idle})
    assert cc.verdict([], {"max_sm_mhz": 1981, "load_error": None, "info": idle}) == []
    assert cc.verdict([], {"max_sm_mhz": 1980, "load_error": None, "info": {}})


def test_default_load_fn_warms_up_signals_ready_then_runs_timed_loop_after_ready():
    calls = []

    class T:
        def __matmul__(self, o):
            calls.append("matmul")
            return T()
    torch = SimpleNamespace(float16="fp16", cuda=SimpleNamespace(is_available=lambda: True, synchronize=lambda: calls.append("sync"), empty_cache=lambda: calls.append("empty")),
                            randn=lambda *a, **k: (calls.append("randn"), T())[1])
    ready = threading.Event()
    real_set = ready.set
    ready.set = lambda: (calls.append("ready"), real_set())
    t = [0.0]

    def clock():
        calls.append("clock")
        t[0] += 0.1
        return t[0]
    cc.default_load_fn(1.0, ready=ready, torch_module=torch, clock=clock)
    assert ready.is_set()
    i = calls.index("ready")
    assert "matmul" in calls[:i] and "sync" in calls[:i] and calls[:i].count("randn") == 2
    assert "clock" not in calls[:i]                    # the end time is taken AFTER the ready signal
    assert calls[i:].count("matmul") >= 2 and calls[-2:] == ["sync", "empty"]


def test_default_load_fn_sets_nothing_without_ready_param():
    torch = SimpleNamespace(cuda=SimpleNamespace(is_available=lambda: False))
    with pytest.raises(RuntimeError):
        cc.default_load_fn(1.0, torch_module=torch)
