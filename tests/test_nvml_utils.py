"""Finding 3 (throttle-reason decoding) and finding 2 (temperature summary) from reviews/2026-10-20_w1_review.md."""
import os
import re
from pathlib import Path

import pytest

from nvml_utils import EVENT_REASONS, decode_event_reasons, summarize_temps


def _find_nvml_h():
    """CUDA_PATH first, then any installed CUDA toolkit under Program Files."""
    roots = [os.environ.get("CUDA_PATH", "")]
    roots += [str(p) for p in Path(r"C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA").glob("v*")]
    for r in roots:
        if r and (Path(r) / "include" / "nvml.h").exists():
            return Path(r) / "include" / "nvml.h"
    return Path("nvml.h-not-found")


NVML_H = _find_nvml_h()


# ---- finding 3: decoding, locked to ground truth observed 2026-10-20 (raw masks + nvidia-smi -q -d PERFORMANCE)
def test_idle_mask_is_gpu_idle():
    assert decode_event_reasons(0x1) == ["GpuIdle"]          # observed raw mask at idle


def test_fma_load_mask_is_reliability_only():
    # observed: raw 0x400 under constant fma load; nvidia-smi: Reliability Active, SW Power Cap Not Active
    assert decode_event_reasons(0x400) == ["Reliability"]


def test_board_limit_bit():
    assert decode_event_reasons(0x200) == ["BoardLimit"]     # nvidia-smi lists "Board Limit" as a separate reason


def test_power_cap_plus_reliability_matches_matmul_audit():
    assert decode_event_reasons(0x400 | 0x4) == ["Reliability", "SwPowerCap"]


def test_zero_is_none():
    assert decode_event_reasons(0) == ["None"]


def test_unknown_bit_is_reported_not_dropped_or_misnamed():
    assert decode_event_reasons(0x800) == ["Unknown_0x800"]
    assert decode_event_reasons(0x800 | 0x4) == ["SwPowerCap", "Unknown_0x800"]


@pytest.mark.skipif(not NVML_H.exists(), reason="CUDA nvml.h not installed")
def test_table_agrees_with_cuda_header_for_documented_reasons():
    text = NVML_H.read_text(errors="ignore")
    pairs = re.findall(r"#define\s+nvmlClocks(?:Event|Throttle)Reason(\w+)\s+(0x[0-9A-Fa-f]+)LL", text)
    documented = {name: int(val, 16) for name, val in pairs if name not in ("None", "All")}
    assert documented, "no reasons parsed from nvml.h"
    for name, val in documented.items():
        assert val in EVENT_REASONS.values(), f"header bit {name}={val:#x} missing from our table"
    # and the table's names for those bits match the header's names (aliases allowed via UserDefinedClocks)
    for name, val in documented.items():
        if name != "UserDefinedClocks":
            assert EVENT_REASONS.get(name) == val, f"documented reason {name}={val:#x} is not in EVENT_REASONS"


# ---- finding 2: temp_start must be the first window sample so that temp_max >= temp_start always
def test_start_is_first_window_sample_not_pre_reading():
    t = summarize_temps(pre_c=61, window_samples=[53, 53, 54])
    assert t["temp_start_c"] == 53
    assert t["temp_max_c"] == 54
    assert t["temp_pre_c"] == 61          # the thermal gate reading is kept, under its own name


def test_max_never_below_start():
    for samples in ([50], [50, 49, 48], [60, 70, 65]):
        t = summarize_temps(pre_c=99, window_samples=samples)
        assert t["temp_max_c"] >= t["temp_start_c"]


def test_empty_window_fails_loudly():
    with pytest.raises(ValueError):
        summarize_temps(pre_c=50, window_samples=[])
