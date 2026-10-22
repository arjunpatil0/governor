"""telemetry/nvml_source.py (NVML sensor source for the daemon) and telemetry/fg_publisher.py (foreground frame publisher for the rings and the pace block).
Fake NVML, no GPU. Instruction: "Proceed to the telemetry daemon, llama_governed driver and admin clock helper (/security-scan), test-first, no GPU"."""
import math
import uuid

import pytest

from telemetry.fg_publisher import FramePublisher
from telemetry.nvml_source import NvmlSource
from telemetry.ring import SeqBlock, SharedRing


class FakeNv:
    NVML_CLOCK_SM, NVML_CLOCK_MEM, NVML_TEMPERATURE_GPU = 1, 2, 0

    def nvmlDeviceGetPowerUsage(self, h): return 61500
    def nvmlDeviceGetClockInfo(self, h, k): return {1: 1500, 2: 8001}[k]
    def nvmlDeviceGetTemperature(self, h, k): return 67
    def nvmlDeviceGetTotalEnergyConsumption(self, h): return 123456
    def nvmlDeviceGetCurrentClocksEventReasons(self, h): return 0x4


def nm():
    return "Local\gov_test_" + uuid.uuid4().hex


def test_nvml_source_reports_the_fields_in_si_units_and_the_reason_mask():
    v = NvmlSource(FakeNv(), object())()
    assert v == dict(power_w=61.5, sm_mhz=1500, mem_mhz=8001, temp_c=67, energy_j=123.456, reasons=4)


def test_nvml_source_fails_loudly_if_a_binding_is_missing():
    class Broken(FakeNv):
        nvmlDeviceGetTotalEnergyConsumption = None
    with pytest.raises(Exception):
        NvmlSource(Broken(), object())()


def test_frame_publisher_writes_the_ring_and_the_pace_block():
    ring, pace = SharedRing(nm(), 16, 3, create=True), SeqBlock(nm(), 3, create=True)
    pub = FramePublisher(ring, pace)
    pub.frame_started(t_now=10.000, t_next=10.0167)
    assert pace.read() == (1.0, 10.0167, 10.000)
    pub.frame_done(t_sched=10.0, t_start=10.001, t_end=10.007, t_next=10.0167, t_now=10.007)
    assert pace.read() == (0.0, 10.0167, 10.007)
    rec, _ = SharedRing(ring.name, 16, 3, create=False).read_new()
    assert rec.tolist() == [[10.0, 10.001, 10.007]]
    pub.idle(t_now=11.0)
    v = pace.read()
    assert v[0] == 0.0 and math.isinf(v[1]) and v[2] == 11.0
