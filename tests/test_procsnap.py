"""Process snapshot written to meta.json at run start (name + CPU%), so background apps (WhatsApp, Discord, Chrome) are on record."""
import os

import procsnap


class FakeProc:
    def __init__(self, name, cpu):
        self._n, self._c = name, cpu
        self.info = {"name": name}

    def cpu_percent(self, interval=None):
        return self._c


def test_aggregates_by_name_sorted_by_cpu_and_counts_instances():
    procs = [FakeProc("Discord.exe", 1.5), FakeProc("Discord.exe", 0.5), FakeProc("WhatsApp.exe", 0.0), FakeProc("chrome.exe", 7.0)]
    snap = procsnap.snapshot(interval=0, procs=lambda attrs: procs)
    assert [s["name"] for s in snap] == ["chrome.exe", "Discord.exe", "WhatsApp.exe"]
    d = {s["name"]: s for s in snap}
    assert d["Discord.exe"]["count"] == 2 and abs(d["Discord.exe"]["cpu_pct"] - 2.0) < 1e-9


def test_real_snapshot_contains_this_python_process():
    snap = procsnap.snapshot(interval=0.1)
    assert any(os.path.basename(s["name"]).lower().startswith("python") for s in snap)
    assert all(set(s) == {"name", "count", "cpu_pct"} for s in snap)


def test_process_that_vanishes_is_skipped():
    class Gone(FakeProc):
        def cpu_percent(self, interval=None):
            raise ProcessLookupError("gone")
    snap = procsnap.snapshot(interval=0, procs=lambda attrs: [Gone("x.exe", 0), FakeProc("y.exe", 1.0)])
    assert [s["name"] for s in snap] == ["y.exe"]
