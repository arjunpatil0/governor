from pathlib import Path

import pytest

from tools.realgame import presentmon as pm

SAMPLE = Path(__file__).parent / "data" / "pm_sample_synthetic.csv"
HZ = 10_000_000.0   # synthetic assumption for the synthetic sample only
GOLD = ("Application,ProcessID,SwapChainAddress,PresentRuntime,SyncInterval,PresentFlags,AllowsTearing,PresentMode,FrameType,CPUStartQPC,FrameTime,CPUBusy,CPUWait,GPULatency,GPUTime,GPUBusy,"
        "GPUWait,VideoBusy,DisplayLatency,DisplayedTime,AnimationError,AnimationTime,MsFlipDelay,AllInputToPhotonLatency,ClickToPhotonLatency,InstrumentedLatency")
MIN = "SwapChainAddress,PresentMode,CPUStartQPC,{ft},{lat},{busy},DisplayedTime\n"


def mini(ft="FrameTime", lat="GPULatency", busy="GPUBusy", rows=("0xA,Flip,100,16.6,1.0,8.0,16.6",)):
    return MIN.format(ft=ft, lat=lat, busy=busy) + "\n".join(rows) + "\n"


def test_sample_has_26_gold_columns_and_is_synthetic():
    header = SAMPLE.read_text().splitlines()[0]
    assert header == GOLD and len(header.split(",")) == 26
    assert "synthetic" in SAMPLE.name


def test_parse_sample_path():
    frames = pm.parse_csv(SAMPLE)
    assert len(frames) == 30
    f0 = frames[0]
    assert f0.t_cpu_start == 1_000_000_000.0          # raw counts, not seconds
    assert f0.frame_ms == pytest.approx(16.667)
    assert f0.gpu_latency_ms == pytest.approx(1.176)
    assert f0.gpu_busy_ms == pytest.approx(8.466)
    assert f0.displayed is True and f0.swapchain == "0x0000000000000001"
    assert f0.present_mode == "Hardware: Independent Flip"


def test_dropped_frame_kept():
    frames = pm.parse_csv(SAMPLE)
    assert [f.displayed for f in frames].count(False) == 1 and not frames[5].displayed


def test_parse_text_and_str_path():
    assert len(pm.parse_csv(SAMPLE.read_text())) == 30
    assert len(pm.parse_csv(str(SAMPLE))) == 30


def test_readme_names_accepted():
    f = pm.parse_csv(mini("MsBetweenAppStart", "MsGPULatency", "MsGPUBusy"))[0]
    assert (f.frame_ms, f.gpu_latency_ms, f.gpu_busy_ms) == (16.6, 1.0, 8.0)


def test_unknown_column_raises():
    with pytest.raises(pm.UnknownColumnError, match="Bogus"):
        pm.parse_csv(mini().replace("PresentMode", "Bogus"))


def test_missing_logical_field_raises():
    with pytest.raises(pm.MissingColumnError, match="gpu_busy_ms"):
        pm.parse_csv("CPUStartQPC,FrameTime,GPULatency,DisplayedTime\n1,2,3,4\n")
    with pytest.raises(pm.MissingColumnError, match="cpu_start"):
        pm.parse_csv("CPUStartTime,FrameTime,GPULatency,GPUBusy,DisplayedTime\n1,2,3,4,5\n")


def test_alias_conflict_raises_and_agreement_ok():
    both = "CPUStartQPC,FrameTime,MsBetweenAppStart,GPULatency,GPUBusy,DisplayedTime\n"
    with pytest.raises(pm.MissingColumnError, match="frame_ms"):
        pm.parse_csv(both + "1,16.0,17.0,1,8,16\n")
    assert pm.parse_csv(both + "1,16.0,16.0,1,8,16\n")[0].frame_ms == 16.0


def test_empty_and_header_only():
    with pytest.raises(pm.PresentMonError):
        pm.parse_csv(Path(__file__).parent / "data" / "does_not_exist.csv")
    with pytest.raises(pm.PresentMonError):
        pm.parse_csv("\n\n")
    assert pm.parse_csv(mini(rows=())) == []


def test_non_numeric_gpu_field_raises():
    with pytest.raises(pm.PresentMonError, match="GPUBusy"):
        pm.parse_csv(mini(rows=("0xA,Flip,100,16.6,1.0,NA,16.6",)))


def test_known_columns_union():
    for c in GOLD.split(","):
        assert c in pm.KNOWN_COLUMNS
    for c in ("MsCPUBusy", "MsGPULatency", "MsGPUBusy", "MsBetweenAppStart", "MsFlipDelay", "AllInputToPhotonLatency", "ClickToPhotonLatency", "PresentId", "CPUStartQPC"):
        assert c in pm.KNOWN_COLUMNS
    assert pm.PM_ALIASES["frame_ms"] == ("FrameTime", "MsBetweenAppStart")
    assert pm.PM_ALIASES["cpu_start"] == ("CPUStartQPC",)


def test_dominant_swapchain():
    frames = pm.parse_csv(SAMPLE)
    assert pm.dominant_swapchain(frames) == "0x0000000000000001"
    assert len(pm.frames_of_swapchain(frames, "0x0000000000000002")) == 5
    with pytest.raises(ValueError):
        pm.dominant_swapchain([])


def test_qpc_hz_required_and_positive():
    f = pm.parse_csv(SAMPLE)[1]
    assert pm.to_seconds(f.t_cpu_start, HZ) == pytest.approx(100.016667)
    with pytest.raises(ValueError):
        pm.to_seconds(1.0, 0)


def test_build_cmd_exact_flags():
    cmd = pm.Capture.build_cmd("pm.exe", "game.exe", "o.csv", "sess")
    assert cmd == ["pm.exe", "--v2_metrics", "--qpc_time", "--no_console_stats", "--process_name", "game.exe", "--output_file", "o.csv",
                   "--session_name", "sess", "--stop_existing_session"]
    cmd = pm.Capture.build_cmd("pm.exe", "game.exe", "o.csv", "sess", timed_s=80)
    assert cmd[-3:] == ["--timed", "80", "--terminate_after_timed"] and len(cmd) == 14


class FakeProc:
    def __init__(self, hang=False):
        self.hang, self.killed, self.signalled, self.waits = hang, False, None, 0
        self.returncode = None

    def poll(self):
        return self.returncode

    def send_signal(self, s):
        self.signalled = s

    def wait(self, timeout=None):
        self.waits += 1
        if self.hang and not self.killed:
            import subprocess
            raise subprocess.TimeoutExpired("pm", timeout)
        self.returncode = 0
        return 0

    def kill(self):
        self.killed = True


def test_capture_stop_graceful_then_kill():
    p = FakeProc()
    c = pm.Capture("pm.exe", "g.exe", "o.csv", "s", popen=lambda cmd, **kw: p)
    c.start(); c.stop(timeout=1)
    assert p.signalled is not None and not p.killed
    p = FakeProc(hang=True)
    c = pm.Capture("pm.exe", "g.exe", "o.csv", "s", popen=lambda cmd, **kw: p)
    c.start(); c.stop(timeout=0.01)
    assert p.killed
    c.stop()   # idempotent after stop


def test_capture_stop_before_start_raises():
    with pytest.raises(RuntimeError):
        pm.Capture("pm.exe", "g.exe", "o.csv", "s", popen=lambda *a, **k: None).stop()


def test_version_parses_and_fails_loudly():
    class R:
        def __init__(self, rc, out):
            self.returncode, self.stdout, self.stderr = rc, out, ""
    assert pm.version("pm.exe", run=lambda *a, **k: R(0, "PresentMon 2.6.0\n")) == "PresentMon 2.6.0"
    with pytest.raises(RuntimeError):
        pm.version("pm.exe", run=lambda *a, **k: R(1, ""))


def test_version_uses_help_and_not_the_missing_version_flag():
    """PresentMon 2.6.0 rejects --version (verified on hardware: 'unrecognized option', exit code 1, but the version line is printed first)."""
    seen = []

    class R:
        returncode, stdout, stderr = 1, "error: unrecognized option '--version'.\nPresentMon 2.6.0\n\nCapture Target Options:\n  --process_name name  Only record\n", ""

    def run(cmd, **k):
        seen.append(list(cmd))
        return R()
    assert pm.version("pm.exe", run=run) == "PresentMon 2.6.0"
    assert seen == [["pm.exe", "--help"]] and "--version" not in seen[0]


def test_version_in_stderr_nonzero_exit_and_real_help_text():
    class R:
        returncode, stdout, stderr = 1, "", "PresentMon 2.6.0\n\nCapture Target Options:\n"
    assert pm.version("pm.exe", run=lambda *a, **k: R()) == "PresentMon 2.6.0"


def test_version_without_a_version_line_fails_loudly():
    class R:
        returncode, stdout, stderr = 0, "usage: something else\n", ""
    with pytest.raises(RuntimeError, match="printed no"):
        pm.version("pm.exe", run=lambda *a, **k: R())
