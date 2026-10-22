"""Governed driver pace-block policy (workloads/background/pace_view.h, used by llama_governed_bench.cpp). Smoke 2 (journal 0041) showed tokens starting at the moments the fg
publishes (1 ms before each frame and at frame completion) whatever the guard; hypothesis: the driver treated a FAILED seqlock read (writer mid-write) as 'fg idle'.
The legacy mode of the probe reproduces the driver as it was; the view mode is the fix: a failed read keeps the last good value. A Python writer emulates the frame loop (60 Hz,
busy at -1 ms, not busy at +6.8 ms, always a finite next arrival). No GPU.
Instruction: "explain the guard-0 overrun from the token durations, recommend the learned-guard design"."""
import subprocess
import threading
import time
import uuid

from telemetry.ring import SeqBlock
from test_shm_cpp import ROOT, build, nm

PERIOD = 1.0 / 60.0


def run_probe(tmp_path, mode, seconds=3.0):
    exe = tmp_path / "probe_pace_view.exe"
    if not exe.exists():
        build(tmp_path, ROOT / "tests" / "cpp" / "probe_pace_view.cpp", exe)
        subprocess.run([str(exe), "Local\\gov_none_" + uuid.uuid4().hex, "0.1", "view"], capture_output=True, timeout=120)          # warm the fresh exe (journal 0036)
    pace = SeqBlock(nm(), 3, create=True)
    stop = threading.Event()

    def writer():
        t0 = time.perf_counter() + 0.05
        k = 0
        while not stop.is_set():
            ts = t0 + k * PERIOD
            while time.perf_counter() < ts - 0.001:
                time.sleep(0.0005)
            pace.write([1.0, ts + PERIOD, time.perf_counter()])                       # frame_started
            while time.perf_counter() < ts + 0.0068:
                time.sleep(0.0005)
            pace.write([0.0, ts + PERIOD, time.perf_counter()])                       # frame_done
            k += 1

    th = threading.Thread(target=writer, daemon=True); th.start()
    time.sleep(0.2)
    r = subprocess.run([str(exe), pace.name, str(seconds), mode], capture_output=True, text=True, timeout=60)
    stop.set(); th.join(2)
    assert r.returncode == 0, r.stdout + r.stderr
    f = r.stdout.split()
    return dict(zip(f[0::2], map(int, f[1::2])))


def test_legacy_driver_policy_sees_phantom_idle_while_the_writer_is_mid_write(tmp_path):
    out = run_probe(tmp_path, "legacy")
    assert out["FAILED_READS"] > 0 and out["PHANTOM_IDLE"] > 0, out          # the mechanism is real: failed reads are interpreted as 'fg idle'


def test_pace_view_never_reports_idle_while_the_fg_publishes_a_finite_next_arrival(tmp_path):
    out = run_probe(tmp_path, "view")
    assert out["PHANTOM_IDLE"] == 0 and out["BUSY_POLLS"] > 0, out


def test_the_governed_driver_uses_the_pace_view_not_a_bare_read():
    src = (ROOT / "workloads" / "background" / "llama_governed_bench.cpp").read_text(encoding="utf-8")
    assert "pview.get(" in src and "pace.read(" not in src


def test_the_governed_driver_uses_the_clean_token_estimate_and_logs_both_estimates():
    src = (ROOT / "workloads" / "background" / "llama_governed_bench.cpp").read_text(encoding="utf-8")
    assert "tokest::TokenEstimate" in src and "west.value()" in src and "tok_est_ms" not in src
    assert "est_ewma_ms" in src and "est_clean_ms" in src and "overlapped" in src
