"""The sampled-power guard (telemetry/power_guard.py, docs/AUDIT_590W.md): a reading above 1.5x the card's maximum power limit (the 588 to 590 W NVML glitch) is rejected at collection time in the experiment
sampler, left out of recent_mean (the Governor's steering input), kept visible in the stored record (per-bin max, rejected samples) and dropped by the dashboard. Fakes only, no GPU.
Instruction (Arjun, 2026-11-07): "Add a unit test with an injected 588 W sample." """
import sys
import tempfile
from pathlib import Path

import numpy as np
import pytest

from telemetry.power_guard import FALLBACK_MAX_LIMIT_W, PowerGuard

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "experiments" / "w4_smoke"))
sys.path.insert(0, str(ROOT / "experiments" / "w5b"))


def test_limit_is_1_5x_the_nvml_max_limit_with_a_stated_fallback():
    class Nv:
        def nvmlDeviceGetPowerManagementLimitConstraints(self, h):
            return (5000, 140000)

    g = PowerGuard.from_nvml(Nv(), None)
    assert g.limit_w == pytest.approx(210.0) and g.source == "nvml"
    assert g.ok(209.9) and not g.ok(210.1) and not g.ok(588.21) and not g.ok(-3.0) and not g.ok(None) and g.ok(0.0)

    class Broken:
        def nvmlDeviceGetPowerManagementLimitConstraints(self, h):
            raise RuntimeError("Not Supported")

    f = PowerGuard.from_nvml(Broken(), None)
    assert f.source == "fallback" and f.limit_w == pytest.approx(1.5 * FALLBACK_MAX_LIMIT_W)


def test_filter_carries_the_last_good_value_counts_and_keeps_the_raw_glitch():
    g = PowerGuard(140.0)
    assert g.filter(588.21) == (None, False)                                  # nothing good yet: no value
    assert g.filter(60.0) == (60.0, True)
    assert g.filter(588.21) == (60.0, False)                                  # carried
    assert g.filter(61.0) == (61.0, True)
    assert g.rejected == 2 and g.rejected_values == [588.21, 588.21] and g.describe()["limit_w"] == 210.0


class FakeNv:
    """NVML with a scripted power sequence in mW; 588210 mW is the injected glitch."""
    NVML_CLOCK_SM = 1

    def __init__(self, mw):
        self.mw = list(mw)

    def nvmlDeviceGetPowerManagementLimitConstraints(self, h):
        return (5000, 140000)

    def nvmlDeviceGetClockInfo(self, h, which):
        return 1800

    def nvmlDeviceGetPowerUsage(self, h):
        return self.mw.pop(0)


def test_sampler_rejects_an_injected_588_w_sample_and_records_it():
    import smoke
    s = smoke.NvmlSampler(nv=FakeNv([60000, 61000, 588210, 62000, 588210]), h=object())
    for _ in range(5):
        s.sample_once()
    assert s.pw == [60.0, 61.0, 61.0, 62.0, 62.0]                             # the glitch never enters the series; the previous good value stands in
    assert len(s.t) == len(s.sm) == len(s.pw) == 5
    assert s.guard.rejected == 2 and s.rej_w == [588.21, 588.21] and len(s.rej_t) == 2
    assert max(s.pw) < 100.0


def test_sampler_skips_a_glitch_before_any_good_sample():
    import smoke
    s = smoke.NvmlSampler(nv=FakeNv([588210, 60000]), h=object())
    s.sample_once()
    s.sample_once()
    assert s.pw == [60.0] and s.guard.rejected == 1


def test_recent_mean_ignores_a_glitch_that_reached_it_unfiltered():
    import executors as ex
    t = [0.80, 0.85, 0.90, 0.95, 1.00]
    v = [60.0, 60.0, 588.21, 60.0, 60.0]
    assert ex.recent_mean(t, v, 1.0, 0.25) == pytest.approx((60 * 4 + 588.21) / 5)          # unguarded: the old behaviour, a 100 W step in the steering signal
    assert ex.recent_mean(t, v, 1.0, 0.25, max_w=210.0) == pytest.approx(60.0)              # guarded: the glitch is left out
    assert np.isnan(ex.recent_mean(t, [588.21] * 5, 1.0, 0.25, max_w=210.0))                 # only glitches in the span: nan, so the loop keeps its last good value


def test_per_bin_max_makes_a_single_bad_sample_visible_beside_the_mean():
    import executors as ex
    t = [0.1, 0.2, 0.3, 0.6, 0.7]
    v = [60.0, 588.21, 60.0, 61.0, 62.0]
    _, mean = ex.trace_bins(t, v, 0.0, 1.0, step_s=0.5)
    mx = ex.trace_bins_max(t, v, 0.0, 1.0, step_s=0.5)
    assert mx.tolist() == [588.21, 62.0] and mean[0] == pytest.approx((60 + 588.21 + 60) / 3)
    assert np.isnan(ex.trace_bins_max([], [], 0.0, 1.0, step_s=0.5)).all()


def test_dashboard_live_source_applies_the_same_guard():
    import tests.test_dashboard_server as T
    import tools.dashboard.sources as src
    with tempfile.TemporaryDirectory() as d:
        own, sess, p, fields = T.make_live(Path(d))

        class Glitchy:
            vals = iter([50.0, 588.21, 52.0])

            def read(self):
                return next(self.vals), 1800.0

        live = src.LiveSource(src.read_session(p), poller=Glitchy(), guard=PowerGuard(140.0))
        ms = [live.tick(0.05) for _ in range(3)]
        assert [len(m["events"]["power"]) for m in ms] == [1, 0, 1]
        assert ms[-1]["stats"]["power_glitches"] == 1 and ms[-1]["stats"]["power_w"] == pytest.approx(51.0)
