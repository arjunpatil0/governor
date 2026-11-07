"""Per-process GPU memory reader (telemetry/vram.py): NVML process list + PDH counter merge, adapter (LUID) choice, sampler and summary. Fakes only, no GPU.
Instruction (Arjun, 2026-11-07): "A few focused tests (yolo loop timing logic, protocol publishing, VRAM reader), not an exhaustive suite." """
import re
from collections import namedtuple
from pathlib import Path
from types import SimpleNamespace

import pytest

from telemetry import vram
from telemetry.vram import MIB, VramPoller, VramReader, merge, nvml_process_mib, parse_pdh, pick_luid

NV, IGPU = "0x00000000_0x0001524f", "0x00000000_0x00013f8c"


def inst(pid, luid, phys=0):
    return f"pid_{pid}_luid_{luid}_phys_{phys}"


def test_nvml_figures_none_and_sentinels_are_not_available_never_zero():
    procs = [SimpleNamespace(pid=1, usedGpuMemory=None), SimpleNamespace(pid=2, usedGpuMemory=(1 << 64) - 1), SimpleNamespace(pid=3, usedGpuMemory=300 * (1 << 20)), SimpleNamespace(pid=4, usedGpuMemory=0)]
    assert nvml_process_mib(procs) == {1: None, 2: None, 3: 300.0, 4: 0.0}


def test_pdh_parse_sums_phys_entries_and_skips_other_instances():
    by = parse_pdh({inst(10, NV): 100.0, inst(10, NV, phys=1): 50.0, inst(10, IGPU): 7.0, "_Total": 999.0})
    assert by == {NV: {10: 150.0}, IGPU: {10: 7.0}}


def test_adapter_is_the_luid_where_nvml_processes_appear_and_pdh_fills_the_figures():
    by = parse_pdh({inst(10, NV): 400 * MIB, inst(20, NV): 900 * MIB, inst(10, IGPU): 5 * MIB, inst(30, IGPU): 80 * MIB, inst(40, IGPU): 80 * MIB})   # the iGPU has more processes in total
    nvml = {10: None, 20: None}
    luid = pick_luid(by, list(nvml))
    assert luid == NV
    procs = merge(nvml, by, luid)
    assert procs[10] == dict(mib=400.0, source="pdh") and procs[20] == dict(mib=900.0, source="pdh")
    assert 30 not in procs                                                # only NVML-listed processes are reported
    assert pick_luid(by, []) is None                                      # nothing on NVIDIA: nothing is guessed
    assert pick_luid(by, [10], preferred=IGPU.upper()) == IGPU            # an explicit LUID wins
    assert merge({7: None}, by, NV)[7] == dict(mib=None, source="n/a")    # no PDH entry: unknown, not 0
    assert merge({10: 123.0}, by, NV)[10] == dict(mib=123.0, source="nvml")   # NVML's own figure is used when it has one


Mem = namedtuple("Mem", "total used free")


class FakeNvml:
    def __init__(self, compute, graphics=()):
        self.compute, self.graphics = compute, list(graphics)

    def nvmlDeviceGetMemoryInfo(self, h):
        return Mem(8188 * (1 << 20), 3000 * (1 << 20), 5188 * (1 << 20))

    def nvmlDeviceGetComputeRunningProcesses(self, h):
        return self.compute

    def nvmlDeviceGetGraphicsRunningProcesses(self, h):
        return self.graphics


class FakePdh:
    def __init__(self, values):
        self.values = values

    def read(self):
        return self.values


def test_reader_reports_totals_and_per_process_memory():
    nv = FakeNvml([SimpleNamespace(pid=10, usedGpuMemory=None)], [SimpleNamespace(pid=10, usedGpuMemory=None), SimpleNamespace(pid=11, usedGpuMemory=None)])   # pid 10 in both lists: once
    r = VramReader(nv, None, FakePdh({inst(10, NV): 500 * MIB, inst(11, NV): 100 * MIB}), name_of=lambda pid: f"p{pid}", clock=lambda: 5.0)
    s = r.read()
    assert s["total_mib"] == 8188.0 and s["used_mib"] == 3000.0 and s["luid"] == NV and s["t"] == 5.0
    assert s["procs"] == {10: dict(mib=500.0, source="pdh", name="p10"), 11: dict(mib=100.0, source="pdh", name="p11")}


def test_reader_without_pdh_lists_processes_with_no_figure():
    r = VramReader(FakeNvml([SimpleNamespace(pid=10, usedGpuMemory=None)]), None, None, name_of=lambda p: None)
    assert r.read()["procs"][10]["mib"] is None


class SeqReader:
    def __init__(self, samples):
        self.samples, self.i = samples, 0

    def read(self):
        if self.i >= len(self.samples):
            raise RuntimeError("gone")
        s = self.samples[self.i]
        self.i += 1
        return s


def samp(t, used, **mib):
    """A reader sample; keyword names are p<pid>=MiB."""
    return dict(t=t, total_mib=8188.0, used_mib=used, luid=NV, procs={int(k[1:]): dict(mib=m, source="pdh", name=None) for k, m in mib.items()})


def test_poller_summary_over_a_window_and_failed_reads_are_counted():
    p = VramPoller(reader=SeqReader([samp(1.0, 1000, p7=300.0), samp(2.0, 1500, p7=500.0), samp(3.0, 1200, p7=400.0), samp(9.0, 8000, p7=9999.0)]), start=False)
    for _ in range(5):
        p.poll_once()                                                     # the 5th read raises
    assert p.errors == 1 and len(p.samples) == 4 and p.latest["t"] == 9.0
    s = p.summary([7, 8], 0.5, 3.5)
    assert s[7] == dict(peak_mib=500.0, median_mib=400.0, n=3)
    assert s[8] == dict(peak_mib=None, median_mib=None, n=0)              # a process that never appeared
    assert s["system"] == dict(peak_mib=1500, total_mib=8188.0, n=3)


def test_poller_without_nvml_stays_empty(monkeypatch):
    monkeypatch.setattr(vram, "default_reader", lambda luid=None: (_ for _ in ()).throw(RuntimeError("no NVML")))
    p = VramPoller()
    assert p.latest is None and p.reader is None
    p.stop()


def test_vram_module_never_calls_the_energy_counter():
    txt = Path(vram.__file__).read_text(encoding="utf-8")
    assert not re.search(r"GetTotalEnergy|energy_j|energy_mj", txt)
