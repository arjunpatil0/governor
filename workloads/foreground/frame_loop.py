"""Synthetic frame-paced foreground for the governor (W4-5): one frame every fg.period_ms on an ABSOLUTE schedule (no re-timing, no skipped frames: a late frame is simply
late, so lateness shows up as latency, i.e. no coordinated omission), cost and activity taken from the same scenario definitions the simulator uses (sim/scenarios.py).
The pace block goes busy `lead_ms` before each frame and not-busy (with the next scheduled arrival) when the frame completes, so the governed driver can fill the slack.
Frame records: [t_sched, t_start, t_end] on the QPC timeline (time.perf_counter == the DLL QPC clock within microseconds, journal 0011).
`run_frame(cost_ms, t_sched_s) -> (t_launch_s, t_complete_s)` is injected: tests use a busy-wait fake, the hardware smoke uses FmaFrameRunner (GPU)."""
import time


class FrameLoop:
    def __init__(self, fg, run_frame, publisher, lead_ms=1.0, grace_s=2.0, clock=time.perf_counter, sleep=time.sleep):
        self.fg, self.run_frame, self.pub = fg, run_frame, publisher
        self.lead_s, self.grace_s, self.clock, self.sleep = lead_ms / 1000.0, grace_s, clock, sleep
        self.t0 = None
        self.abandoned = 0

    def _sleep_until(self, t):
        while True:
            rem = t - self.clock()
            if rem <= 0:
                return
            if rem > 0.003:
                self.sleep(rem - 0.002)

    def run(self, duration_s, t0=None):
        self.t0 = self.clock() + 0.05 if t0 is None else t0
        period = self.fg.period_ms / 1000.0
        n_total = int(round(duration_s / period))
        recs, self.abandoned = [], 0
        for k in range(n_total):
            t_sched = self.t0 + k * period
            ms = (t_sched - self.t0) * 1000.0
            if self.clock() > self.t0 + duration_s + self.grace_s:       # far past the end: whatever is still scheduled is abandoned, not skipped silently
                self.abandoned = sum(1 for j in range(k, n_total) if self.fg.active((j * period) * 1000.0))
                break
            if not self.fg.active(ms):
                self.pub.idle(self.clock())
                self._sleep_until(t_sched + period)
                continue
            self._sleep_until(t_sched - self.lead_s)
            self.pub.frame_started(self.clock(), t_next=t_sched + period)
            cost = self.fg.cost_ms(ms)
            t_start, t_end = self.run_frame(cost, t_sched)
            self.pub.frame_done(t_sched, t_start, t_end, t_next=t_sched + period, t_now=t_end)
            recs.append(dict(t_sched=t_sched, t_start=t_start, t_end=t_end, lat_ms=(t_end - t_sched) * 1000.0, cost_ms=cost))
        return recs


class FmaFrameRunner:
    """GPU frame runner: one FMA kernel launch through the W2 DLL (workloads/common/w2lib.py), released at the scheduled QPC time and synchronised. Hardware smoke only.
    Calibrate ONCE with the SM clock locked at 1800 MHz (cost_ms means ms alone at 1800 MHz, as in the simulator), e.g. cal = FmaFrameRunner.calibrate(w)."""
    def __init__(self, w2, cal):
        from workloads.common.w2lib import units_for
        self.w, self.cal, self._units_for, self._cache = w2, cal, units_for, {}

    @staticmethod
    def calibrate(w2):
        from workloads.common.w2lib import calibrate
        return calibrate(w2, 1, [2000, 8000, 32000, 64000])

    def __call__(self, cost_ms, t_sched):
        import numpy as np
        u = self._cache.get(cost_ms)
        if u is None:
            u = self._cache[cost_ms] = int(self._units_for(self.cal, cost_ms))
        tl, tc, _ = self.w.fg_run(1, np.array([t_sched]), u)
        return float(tl[0]), float(tc[0])
