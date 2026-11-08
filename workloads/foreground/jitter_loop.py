"""v2 sprint 3: the synthetic 60 fps foreground with jitter (docs/V2_SPRINT3_JITTER.md). The v1 loop (workloads/foreground/frame_loop.py) is left untouched; this is a separate loop with the same absolute schedule
(frame k is nominally due at t0 + k / 60 s) and the same publisher and runner interfaces. Three kinds of jitter, all drawn up front from one seed so that every arm at a level and repetition sees the SAME sequence:
  (a) frame cost: lognormal around the scene's current mean cost with a given CV (mean 1 multiplier), plus a 2x spike in a fraction of frames;
  (b) submit time: the frame is submitted uniformly within +-submit_ms of its nominal time, and the hint is updated ONLY when the app actually submits (busy goes up just before the real submit, no lead);
      the deadline published is still the nominal grid (scheduled time + period), which is what the app believes;
  (c) unannounced bursts: with a given probability per frame a short extra kernel (0.5 to 1.5 ms) runs at a random point of the gap before the frame, with no hint at all.
Lateness is measured against the NOMINAL schedule (lat = t_end - nominal arrival; late if lat > period), so submit jitter counts, equally in the SOLO arm.
LEVELS: none (no jitter), moderate (CV 0.15, +-1 ms, 5% bursts), heavy (CV 0.30 + 2% spikes, +-2 ms, 10% bursts)."""
import time

import numpy as np

LEVELS = {
    "none": dict(cv=0.0, spike_p=0.0, submit_ms=0.0, burst_p=0.0),
    "moderate": dict(cv=0.15, spike_p=0.0, submit_ms=1.0, burst_p=0.05),
    "heavy": dict(cv=0.30, spike_p=0.02, submit_ms=2.0, burst_p=0.10),
}
BURST_MS = (0.5, 1.5)


def make_sequence(seed, n, level):
    """Per-frame jitter arrays for n frames from one seed: cost multiplier, submit offset (ms), burst flag, burst duration (ms) and burst position (0..1 of the free part of the gap)."""
    p = LEVELS[level]
    rng = np.random.default_rng(np.random.SeedSequence(int(seed)))
    if p["cv"] > 0:
        sigma = np.sqrt(np.log(1.0 + p["cv"] ** 2))
        mult = rng.lognormal(mean=-0.5 * sigma ** 2, sigma=sigma, size=n)
    else:
        mult = np.ones(n)
    spike = rng.random(n) < p["spike_p"]
    mult = mult * np.where(spike, 2.0, 1.0)
    delta_ms = rng.uniform(-p["submit_ms"], p["submit_ms"], size=n) if p["submit_ms"] > 0 else np.zeros(n)
    burst = rng.random(n) < p["burst_p"]
    burst_ms = rng.uniform(BURST_MS[0], BURST_MS[1], size=n)
    burst_u = rng.random(n)
    return dict(mult=mult, spike=spike, delta_ms=delta_ms, burst=burst, burst_ms=burst_ms, burst_u=burst_u)


class JitterFrameLoop:
    """fg: FgSpec (cost_ms(t_ms) mean cost, active(t_ms)); run_frame(cost_ms, t_sched_s) -> (t_launch_s, t_complete_s) as in FrameLoop; publisher: FramePublisher; seq: make_sequence(...) output."""
    def __init__(self, fg, run_frame, publisher, seq, clock=time.perf_counter, sleep=time.sleep, grace_s=5.0):
        self.fg, self.run_frame, self.pub, self.seq = fg, run_frame, publisher, seq
        self.clock, self.sleep, self.grace_s = clock, sleep, grace_s
        self.t0, self.abandoned = None, 0

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
        s = self.seq
        recs, self.abandoned = [], 0
        t_prev_end = None
        for k in range(n_total):
            t_sched = self.t0 + k * period
            if self.clock() > self.t0 + duration_s + self.grace_s:
                self.abandoned = n_total - k
                break
            ms = (t_sched - self.t0) * 1000.0
            if not self.fg.active(ms):
                self.pub.idle(self.clock())
                self._sleep_until(t_sched + period)
                continue
            cost = self.fg.cost_ms(ms) * float(s["mult"][k])
            t_submit = t_sched + float(s["delta_ms"][k]) / 1000.0
            burst_ran = False
            if s["burst"][k] and t_prev_end is not None:                  # (c) unannounced extra kernel in the gap before this frame: no hint is published
                d = float(s["burst_ms"][k]) / 1000.0
                free = (t_submit - 0.0003) - t_prev_end - d
                if free > 0:
                    t_b = t_prev_end + float(s["burst_u"][k]) * free
                    self._sleep_until(t_b)
                    self.run_frame(d * 1000.0, self.clock())
                    burst_ran = True
            self._sleep_until(t_submit)
            self.pub.frame_started(self.clock(), t_next=t_sched + period)   # (b) busy goes up only at the real submit; the deadline is the nominal grid
            t_start, t_end = self.run_frame(cost, self.clock())
            self.pub.frame_done(t_sched, t_start, t_end, t_next=t_sched + period, t_now=t_end)
            t_prev_end = t_end
            recs.append(dict(k=k, t_sched=t_sched, t_submit=t_submit, t_start=t_start, t_end=t_end, lat_ms=(t_end - t_sched) * 1000.0, cost_ms=cost, burst=burst_ran, spike=bool(s["spike"][k])))
        return recs
