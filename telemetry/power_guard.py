"""Guard against the NVML sampled-power glitch (docs/AUDIT_590W.md): nvmlDeviceGetPowerUsage sometimes returns 588 to 590 W (about one 0.5 s update at a time) on this laptop, far above the card's
maximum power limit. A reading is rejected if it is negative or above FACTOR (1.5) times that limit, read once from NVML at start (nvmlDeviceGetPowerManagementLimitConstraints, 140 W here, so 210 W).
If NVML cannot give the limit the recorded value of this machine (FALLBACK_MAX_LIMIT_W, `nvidia-smi` power.max_limit) is used and `source` says so; nothing is silently guessed.
filter() is for samplers: a rejected reading is replaced by the last accepted one (None before the first), counted, and the raw value is kept in `rejected_values`, so the glitch stays visible in the record.
ok() is for displays that simply drop a bad reading. The guard is used from one thread."""
FACTOR = 1.5
FALLBACK_MAX_LIMIT_W = 140.0


class PowerGuard:
    def __init__(self, max_limit_w, factor=FACTOR, source="given"):
        self.max_limit_w, self.factor, self.source = float(max_limit_w), float(factor), source
        self.limit_w = self.factor * self.max_limit_w
        self.last_good, self.rejected, self.rejected_values = None, 0, []

    @classmethod
    def from_nvml(cls, nv, h):
        """The limit from NVML; if the call is not supported, the fallback constant (source 'fallback')."""
        try:
            return cls(nv.nvmlDeviceGetPowerManagementLimitConstraints(h)[1] / 1000.0, source="nvml")
        except Exception:                                                    # noqa: BLE001
            return cls(FALLBACK_MAX_LIMIT_W, source="fallback")

    @classmethod
    def default(cls):
        """from_nvml on device 0; the fallback constant if NVML is not available at all."""
        try:
            import pynvml as nv
            nv.nvmlInit()
            return cls.from_nvml(nv, nv.nvmlDeviceGetHandleByIndex(0))
        except Exception:                                                    # noqa: BLE001
            return cls(FALLBACK_MAX_LIMIT_W, source="fallback")

    def ok(self, w):
        return w is not None and 0.0 <= w <= self.limit_w

    def filter(self, w):
        """-> (value to store, accepted). A rejected reading is counted and returns the last accepted value (None if there is none yet)."""
        if self.ok(w):
            self.last_good = w
            return w, True
        self.rejected += 1
        self.rejected_values.append(w)
        return self.last_good, False

    def describe(self):
        return dict(max_limit_w=self.max_limit_w, factor=self.factor, limit_w=self.limit_w, source=self.source, rejected=self.rejected)
