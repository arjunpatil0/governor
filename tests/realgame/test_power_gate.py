"""Amendment 19 (replaced): the enforced power limit is a recorded covariate. The only gate is the clock check (max enforced limit during the load >= 94 W) and the static nvidia-smi
power fields must not change between sweep start and a cell start. Fakes only; nothing here touches the GPU."""
import json
import re
import threading
from pathlib import Path

import pytest

import rg_synth
from test_amend18_22 import FakeTimeSrc
from test_cell import Clock, FakeProbes, FakeSampler, make_cfg, make_deps
from test_review2 import main_args
from tools.realgame import cell as c
from tools.realgame import clockcheck as cc
from tools.realgame import run as r

PKG = Path(__file__).resolve().parents[2] / "tools" / "realgame"

SMI = """
==============NVSMI LOG==============

GPU 00000000:01:00.0
    GPU Power Readings
        Average Power Draw                : N/A
        Instantaneous Power Draw          : 7.10 W
        Current Power Limit               : {cur} W
        Requested Power Limit             : N/A
        Default Power Limit               : {dflt} W
        Min Power Limit                   : {mn} W
        Max Power Limit                   : {mx} W
    Power Samples
        Duration                          : 2.00 sec
"""


def smi(cur="80.00", dflt="80.00", mn="5.00", mx="140.00"):
    return SMI.format(cur=cur, dflt=dflt, mn=mn, mx=mx)


# ------------------------------------------------------------------ clock check gate
class Rd:
    def __init__(self, limits=(95.0,), load_sm=2100):
        self.limits, self.load_sm, self.i = list(limits), load_sm, 0
        self.loaded = threading.Event()

    def sm_clock(self):
        return self.load_sm if self.loaded.is_set() else 210

    def pstate(self):
        return 0

    def clock_reasons(self):
        return 0

    def enforced_power_limit_w(self):
        v = self.limits[min(self.i, len(self.limits) - 1)]
        self.i += 1
        if isinstance(v, Exception):
            raise v
        return v

    def load_fn(self, seconds):
        self.loaded.set()


def check(rd):
    ts = FakeTimeSrc()

    def sleep(s):
        ts.sleep(s)
        if ts.t >= cc.IDLE_INFO_S:
            rd.loaded.wait(1.0)
    return cc.run_check(rd, rd.load_fn, helper_fn=lambda: [], clock=ts.now, sleep=sleep)


def test_gate_constant_and_threshold_record():
    assert cc.POWER_LIMIT_GATE_W == 94.0 and cc.THRESHOLDS["power_limit_gate_w"] == 94.0


def test_93_99_refuses_and_text_mentions_armoury_crate():
    problems, state = check(Rd([93.99]))
    assert len(problems) == 1 and "93.99" in problems[0] and "94 W" in problems[0] and "Armoury Crate" in problems[0] and "Performance is expected" in problems[0]
    assert state["load_test"]["power_limit_max_w"] == 93.99


def test_94_0_passes_and_records_min_max_count():
    problems, state = check(Rd([90.0, 94.0, 92.0, 80.0]))
    assert problems == []
    lt = state["load_test"]
    assert lt["power_limit_max_w"] == 94.0 and lt["info"]["enforced_limit_w_max"] == 94.0 and lt["info"]["enforced_limit_w_min"] == 80.0
    assert lt["info"]["enforced_limit_w_n"] >= 90


def test_max_over_the_load_decides_not_the_last_reading():
    problems, state = check(Rd([100.0] * 5 + [50.0]))
    assert problems == [] and state["load_test"]["power_limit_max_w"] == 100.0


def test_limit_reader_error_refuses_with_clear_message():
    problems, state = check(Rd([RuntimeError("nvml dead")]))
    assert len(problems) == 1 and "enforced power limit" in problems[0] and "nvml dead" in problems[0] and state["load_test"]["power_limit_max_w"] is None


def test_verdict_without_power_field_refuses():
    assert cc.verdict([], {"max_sm_mhz": 2100, "load_error": None, "info": {}})
    assert cc.verdict([], {"max_sm_mhz": 2100, "load_error": None, "power_limit_max_w": 94.0, "info": {}}) == []


def test_clock_check_json_carries_the_new_fields(tmp_path):
    _, state = check(Rd([95.0]))
    doc = r.write_clock_check(tmp_path, "passed", state, [])
    on_disk = json.loads((tmp_path / "clock_check.json").read_text())
    assert doc["power_limit_max_w"] == 95.0 == on_disk["power_limit_max_w"] and on_disk["info"]["enforced_limit_w_n"] > 0
    assert on_disk["thresholds"]["power_limit_gate_w"] == 94.0


# ------------------------------------------------------------------ static power fields
def test_parse_power_static_reads_values_and_raw_lines():
    p = c.parse_power_static(smi())
    assert (p["default_power_limit_w"], p["min_power_limit_w"], p["max_power_limit_w"], p["current_power_limit_w"]) == (80.0, 5.0, 140.0, 80.0)
    assert any("Default Power Limit" in l for l in p["raw_lines"]) and len(p["raw_lines"]) == 4


@pytest.mark.parametrize("text", ["", "garbage", smi(dflt="N/A"), smi(mn="abc")])
def test_parse_power_static_unparseable_raises_clear_message(text):
    with pytest.raises(c.PowerStaticError, match="(?i)power"):
        c.parse_power_static(text)


class PsProbes(FakeProbes):
    def __init__(self, text=None, **kw):
        super().__init__(**kw)
        self.text = text if text is not None else smi()

    def nvidia_smi_power_text(self):
        if isinstance(self.text, Exception):
            raise self.text
        return self.text


REF = c.parse_power_static(smi())


def cfg_ref(tmp_path, ref=REF):
    return make_cfg(tmp_path, power_static_ref=ref)


def test_preflight_unchanged_passes(tmp_path):
    assert c.preflight(cfg_ref(tmp_path), PsProbes()) is None


def test_preflight_current_limit_change_alone_passes(tmp_path):
    assert c.preflight(cfg_ref(tmp_path), PsProbes(smi(cur="95.00"))) is None


@pytest.mark.parametrize("kw,needle", [(dict(dflt="90.00"), "default"), (dict(mn="6.00"), "min"), (dict(mx="130.00"), "max"), (dict(mx="140.60"), "max")])
def test_preflight_refuses_changed_static_fields(tmp_path, kw, needle):
    with pytest.raises(c.PreflightError) as e:
        c.preflight(cfg_ref(tmp_path), PsProbes(smi(**kw)))
    assert needle in str(e.value).lower() and "power" in str(e.value).lower()


def test_preflight_within_half_watt_passes(tmp_path):
    assert c.preflight(cfg_ref(tmp_path), PsProbes(smi(dflt="80.50"))) is None


def test_preflight_unparseable_or_failing_nvidia_smi_refuses(tmp_path):
    for t in ("nonsense", RuntimeError("no smi")):
        with pytest.raises(c.PreflightError, match="(?i)power"):
            c.preflight(cfg_ref(tmp_path), PsProbes(t))


def test_preflight_without_ref_still_requires_parseable(tmp_path):
    assert c.preflight(make_cfg(tmp_path), PsProbes()) is None
    with pytest.raises(c.PreflightError):
        c.preflight(make_cfg(tmp_path), PsProbes("nonsense"))


def test_no_power_limit_threshold_in_preflight_any_enforced_value_passes(tmp_path):
    class P(PsProbes):
        def power_limit_w(self):
            return 40.0
    assert c.preflight(cfg_ref(tmp_path), P()) is None


def test_preflight_prints_elevated_line(tmp_path, capsys):
    c.preflight(cfg_ref(tmp_path), PsProbes())
    assert "elevated: false" in capsys.readouterr().out


def make_cell(tmp_path, text=None, order=None):
    clock = Clock()
    cfg = cfg_ref(tmp_path)
    d, _ = make_deps(cfg, clock, order=order)
    d.probes = PsProbes(text)
    return cfg, d, clock


def test_run_cell_records_static_fields_at_cell_start(tmp_path):
    cfg, d, _ = make_cell(tmp_path)
    res = c.run_cell("SOLO", 0, tmp_path / "cell", cfg, d)
    doc = json.loads((tmp_path / "cell" / "result.json").read_text())
    assert doc["power_static_cell_start"]["default_power_limit_w"] == 80.0 and res["power_static_cell_start"]["max_power_limit_w"] == 140.0
    assert "power_limit_w_start" not in doc and "power_limit_target_w" not in doc


@pytest.mark.parametrize("text", [smi(dflt="90.00"), smi(mn="1.00"), smi(mx="150.00"), "nonsense"])
def test_run_cell_refuses_before_launch_on_static_change_or_unparseable(tmp_path, text):
    order = []
    cfg, d, _ = make_cell(tmp_path, text, order)
    with pytest.raises(RuntimeError, match="(?i)power"):
        c.run_cell("UNGATED", 0, tmp_path / "cell", cfg, d)
    assert order == [] and not (tmp_path / "cell" / "result.json").exists()


def test_run_cell_current_limit_change_alone_passes(tmp_path):
    cfg, d, _ = make_cell(tmp_path, smi(cur="95.00"))
    assert c.run_cell("SOLO", 0, tmp_path / "cell", cfg, d)["power_static_cell_start"]["current_power_limit_w"] == 95.0


# ------------------------------------------------------------------ per-cell enforced limit covariates
class LimitNvml:
    def __init__(self, base, values):
        self.base, self.values = base, list(values)

    def __getattr__(self, k):
        return getattr(self.base, k)

    def power_limit_w(self):
        v = self.values.pop(0) if len(self.values) > 1 else self.values[0]
        if isinstance(v, Exception):
            raise v
        return v


class LimSampler(FakeSampler):
    def __init__(self, clock, lim):
        super().__init__(clock)
        self.limit = [lim[i % len(lim)] for i in range(len(self.t))]


def test_result_records_start_end_min_max_and_never_refuses(tmp_path):
    cfg, d, clock = make_cell(tmp_path)
    d.nvml = LimitNvml(d.nvml, [60.0, 55.0])
    d.make_sampler = lambda nv: LimSampler(clock, [70.0, 90.0, None, 80.0])
    res = c.run_cell("SOLO", 0, tmp_path / "cell", cfg, d)
    doc = json.loads((tmp_path / "cell" / "result.json").read_text())
    assert doc["enforced_limit_w_start"] == 60.0 and doc["enforced_limit_w_end"] == 55.0 and doc["enforced_limit_w_min"] == 70.0 and doc["enforced_limit_w_max"] == 90.0
    assert res["enforced_limit_w_max"] == 90.0 and not any(k.startswith("power_limit_w") for k in doc)


def test_unreadable_limit_does_not_fail_the_cell(tmp_path):
    cfg, d, _ = make_cell(tmp_path)
    d.nvml = LimitNvml(d.nvml, [RuntimeError("dead")])
    res = c.run_cell("SOLO", 0, tmp_path / "cell", cfg, d)
    assert res["enforced_limit_w_start"] is None and res["enforced_limit_w_end"] is None and res["enforced_limit_w_min"] is None


def test_start_limit_is_read_before_the_llm_spawn(tmp_path):
    order = []
    cfg, d, _ = make_cell(tmp_path, order=order)

    class N(LimitNvml):
        def power_limit_w(self):
            order.append("limit")
            return 90.0
    d.nvml = N(d.nvml, [90.0])
    c.run_cell("UNGATED", 0, tmp_path / "cell", cfg, d)
    assert order.index("limit") < next(i for i, o in enumerate(order) if isinstance(o, tuple) and o[0] == "spawn")


def test_sampler50_samples_the_enforced_limit():
    class Nv:
        def sm_clock(self): return 1500
        def throttle(self): return 0
        def temp_c(self): return 60.0
        def power_w(self): return 50.0
        def power_limit_w(self): return 91.5

    class G:
        def ok(self, w): return True
    s = c.Sampler50(Nv(), 0.05, guard=G())
    s.sample_once()
    assert s.limit == [91.5]

    class Bad(Nv):
        def power_limit_w(self): raise RuntimeError("x")
    s = c.Sampler50(Bad(), 0.05, guard=G())
    s.sample_once()
    assert s.limit == [None]


def test_analyze_summary_carries_covariates(tmp_path):
    from tools.realgame import analyze as a
    cell_dir = tmp_path / "cell"
    cfg, d, _ = make_cell(tmp_path)
    d.nvml = LimitNvml(d.nvml, [60.0, 55.0])
    c.run_cell("SOLO", 0, cell_dir, cfg, d)
    out = a.cell_summary(cell_dir)
    assert out["enforced_limit_w_start"] == 60.0 and out["enforced_limit_w_end"] == 55.0 and "enforced_limit_w_min" in out and "enforced_limit_w_max" in out


# ------------------------------------------------------------------ CLI and records
def test_options_removed(tmp_path):
    for opt, val in (("--power-limit-w", "90"), ("--power-limit-tol-w", "2")):
        with pytest.raises(SystemExit):
            r.main(main_args(tmp_path, "--dry-run", "--igpu-vk-index", "1", opt, val), probes=PsProbes())
    assert not hasattr(make_cfg(tmp_path), "power_limit_w")


@pytest.mark.parametrize("alone", [False, True])
def test_run_meta_records_power_static_and_elevated(tmp_path, alone):
    rg_synth.write_fresh_clock_check(tmp_path / "run")
    seen = {}
    import tools.realgame.run as rr
    orig = rr.run_sweep
    rr.run_sweep = lambda cfg, run_dir, order, runner, **k: seen.update(cfg=cfg, **k)
    try:
        extra = ["--llm-alone"] if alone else []
        assert r.main(main_args(tmp_path, "--igpu-vk-index", "1", "--run-dir", str(tmp_path / "run"), *extra), probes=PsProbes(game=not alone), runner=lambda *x: None) == 0
    finally:
        rr.run_sweep = orig
    rec = json.loads((tmp_path / "run" / "run_meta.json").read_text()) if alone else seen["records"]
    assert rec["power_static"]["default_power_limit_w"] == 80.0 and rec["power_static"]["current_power_limit_w"] == 80.0 and rec["power_static"]["raw_lines"]
    assert rec["elevated"] is False
    if not alone:
        assert seen["cfg"].power_static_ref["max_power_limit_w"] == 140.0


# ------------------------------------------------------------------ source scan
def test_no_decision_rule_references_power_limit_fields():
    pat = re.compile(r"power_limit|power_static|enforced_limit|enforced_power|PowerLimit", re.I)
    for n in ("decision.py", "metrics.py"):
        assert not pat.search((PKG / n).read_text(encoding="utf-8")), n
    src = (PKG / "analyze.py").read_text(encoding="utf-8")
    assert not re.search(r"power_limit|power_static|enforced_power|PowerLimit", src, re.I)
    lines = [l for l in src.splitlines() if "enforced_limit" in l]
    assert len(lines) == 1 and not re.search(r"\b(if|and|or|not|assert)\b|[<>]|==|!=", lines[0].split("#")[0])      # one pass-through line, never a condition


class FakeNv:
    def __init__(self, enforced=None, mgmt=None):
        self.enforced, self.mgmt = enforced, mgmt

    def nvmlDeviceGetEnforcedPowerLimit(self, h):
        if self.enforced is None:
            raise RuntimeError("not supported")
        return self.enforced

    def nvmlDeviceGetPowerManagementLimit(self, h):
        if self.mgmt is None:
            raise RuntimeError("not supported")
        return self.mgmt


def test_nvml_power_limit_prefers_enforced_then_management_else_raises():
    assert c.nvml_power_limit_w(FakeNv(enforced=92770, mgmt=80000), 0) == pytest.approx(92.77)
    assert c.nvml_power_limit_w(FakeNv(mgmt=95000), 0) == 95.0
    with pytest.raises(RuntimeError, match="(?i)power limit"):
        c.nvml_power_limit_w(FakeNv(), 0)
