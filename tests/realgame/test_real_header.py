"""The REAL PresentMon 2.6.0 capture header (sprint R1 smoke, SOLO_2, 2026-11-11) and its first 40 rows: every column of this machine's build is known to the parser and the logical fields resolve."""
import csv
from pathlib import Path

from tools.realgame import presentmon as pm

SAMPLE = Path(__file__).parent / "data" / "pm_sample_real.csv"
REAL_HEADER = ("Application,ProcessID,SwapChainAddress,PresentRuntime,SyncInterval,PresentFlags,AllowsTearing,PresentMode,CPUStartQPC,FrameTime,CPUBusy,CPUWait,GPULatency,GPUTime,GPUBusy,"
               "GPUWait,DisplayLatency,DisplayedTime,AnimationError,AnimationTime,MsFlipDelay,AllInputToPhotonLatency,ClickToPhotonLatency").split(",")


def test_real_header_is_the_committed_header_and_all_columns_are_known():
    with open(SAMPLE, encoding="utf-8", newline="") as f:
        header = next(csv.reader(f))
    assert header == REAL_HEADER and len(header) == 23
    assert set(header) <= pm.KNOWN_COLUMNS


def test_real_header_has_the_gold_style_names_not_the_ms_prefixed_ones():
    """This build emits FrameTime / GPUBusy / GPULatency (the gold-file names), not MsBetweenAppStart / MsGPUBusy; FrameType and VideoBusy are absent."""
    assert {"FrameTime", "GPUBusy", "GPULatency", "CPUStartQPC", "DisplayedTime"} <= set(REAL_HEADER)
    assert not any(c.startswith("Ms") and c != "MsFlipDelay" for c in REAL_HEADER)
    assert "FrameType" not in REAL_HEADER and "VideoBusy" not in REAL_HEADER


def test_real_sample_parses_into_the_expected_frames():
    frames = pm.parse_csv(SAMPLE)
    assert len(frames) == 40
    assert {f.swapchain for f in frames} == {"0x2678160D240"}
    assert {f.present_mode for f in frames} == {"Composed: Copy with GPU GDI"}
    assert all(f.displayed for f in frames)
    ms = sorted(f.frame_ms for f in frames)
    assert 16.0 < ms[len(ms) // 2] < 17.5
    busy = sorted(f.gpu_busy_ms for f in frames)
    assert 6.0 < busy[len(busy) // 2] < 7.0
    assert frames[0].t_cpu_start == 54864059033.0
