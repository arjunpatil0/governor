"""NVML helpers shared by the audit and the experiment harnesses (pure functions are unit-tested in tests/)."""

# Clock-event-reason bits. 0x1..0x100 are documented in the CUDA 13.1 nvml.h (tests parse the header and compare).
# 0x200 BoardLimit and 0x400 Reliability are NOT in that header: they come from the nvidia-ml-py binding and were
# confirmed on this machine (driver 616.92) with `nvidia-smi -q -d PERFORMANCE` (raw 0x400 under fma load <-> "Reliability: Active").
EVENT_REASONS = {
    "GpuIdle": 0x1,
    "ApplicationsClocksSetting": 0x2,
    "SwPowerCap": 0x4,
    "HwSlowdown": 0x8,
    "SyncBoost": 0x10,
    "SwThermalSlowdown": 0x20,
    "HwThermalSlowdown": 0x40,
    "HwPowerBrakeSlowdown": 0x80,
    "DisplayClockSetting": 0x100,
    "BoardLimit": 0x200,
    "Reliability": 0x400,
}


def decode_event_reasons(mask):
    """Names of the bits set in `mask`, sorted; bits we do not know are reported as Unknown_0x<bit>, never dropped."""
    if mask == 0:
        return ["None"]
    names, rest = [], mask
    for name, bit in EVENT_REASONS.items():
        if mask & bit:
            names.append(name); rest &= ~bit
    bit = 1
    while rest:
        if rest & bit:
            names.append(f"Unknown_{bit:#x}"); rest &= ~bit
        bit <<= 1
    return sorted(names)


def current_event_mask(handle):
    """Raw clock-event-reason bitmask (new NVML name first, deprecated name as fallback)."""
    import pynvml as nv
    fn = getattr(nv, "nvmlDeviceGetCurrentClocksEventReasons", None) or nv.nvmlDeviceGetCurrentClocksThrottleReasons
    return fn(handle)


def summarize_temps(pre_c, window_samples):
    """temp_pre_c is the reading used by the pre-run thermal gate (taken before the pre-roll heats or cools the GPU).
    temp_start_c is the first sample inside the measured window, so temp_max_c >= temp_start_c always holds."""
    if not window_samples:
        raise ValueError("no temperature samples in the measured window")
    return {"temp_pre_c": pre_c, "temp_start_c": window_samples[0], "temp_max_c": max(window_samples)}
