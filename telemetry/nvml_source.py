"""NVML sensor source for telemetry/daemon.py. `nv` is the pynvml module (or a fake in tests), `h` a device handle. A missing binding raises at the first poll
(loudly); there is no fallback value. Energy is the cumulative counter in J (the governor differences it; sampled power at 20 Hz is mostly stale, see the capability audit)."""
from telemetry.nvml_utils import decode_event_reasons  # noqa: F401  (re-exported for report code)


class NvmlSource:
    def __init__(self, nv, h):
        self.nv, self.h = nv, h

    def __call__(self):
        nv, h = self.nv, self.h
        reasons_fn = getattr(nv, "nvmlDeviceGetCurrentClocksEventReasons", None) or nv.nvmlDeviceGetCurrentClocksThrottleReasons
        return dict(power_w=nv.nvmlDeviceGetPowerUsage(h) / 1000.0, sm_mhz=nv.nvmlDeviceGetClockInfo(h, nv.NVML_CLOCK_SM), mem_mhz=nv.nvmlDeviceGetClockInfo(h, nv.NVML_CLOCK_MEM),
                    temp_c=nv.nvmlDeviceGetTemperature(h, nv.NVML_TEMPERATURE_GPU), energy_j=nv.nvmlDeviceGetTotalEnergyConsumption(h) / 1000.0, reasons=int(reasons_fn(h)))
