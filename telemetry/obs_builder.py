"""Turns shared-ring records and sensor deltas into the sim.plant.Obs the controllers consume, so the controllers run unchanged on hardware.
Frame record (QPC seconds): [t_sched, t_start, t_end]; latency = t_end - t_sched (no coordinated omission, as the W2 experiments).
n_arrived is approximated by the number of frames COMPLETED in the tick (the fg publishes at completion); the controllers only use it to detect an idle fg (no frames for 5 ticks)."""
import numpy as np

from sim.plant import Obs


class ObsBuilder:
    def __init__(self, period_ms, deadline_ms):
        self.period_ms, self.deadline_ms = period_ms, deadline_ms
        self._anchor = None                                   # last scheduled fg arrival seen (QPC s): the frame schedule is anchor + k * period

    def build(self, frames, n_tokens, energy_j, dt_s, clock_mhz, t_ms, tok_ms=None, tok_end=None):
        frames = np.asarray(frames, float).reshape(-1, 3)
        if len(frames):
            self._anchor = float(frames[-1, 0])
        over = None
        if tok_ms is not None and tok_end is not None:
            te, tm, per = np.asarray(tok_end, float), np.asarray(tok_ms, float), self.period_ms / 1000.0
            if self._anchor is None:
                over = np.zeros(len(te))
            else:
                nxt = self._anchor + np.ceil((te - tm / 1000.0 - self._anchor) / per - 1e-9) * per        # first scheduled arrival at or after the token start
                over = np.where(te - self._anchor < 0.5, np.maximum(0.0, (te - nxt) * 1000.0), 0.0)         # a stale schedule (fg idle) claims no overrun
        lat = (frames[:, 2] - frames[:, 0]) * 1000.0
        return Obs(t_ms=float(t_ms), lat_ms=lat, n_missed=int((lat > self.deadline_ms).sum()), n_arrived=int(len(lat)), tokens=int(n_tokens),
                   power_w=float(energy_j / dt_s) if dt_s > 0 else 0.0, clock_mhz=float(clock_mhz), period_ms=self.period_ms, deadline_ms=self.deadline_ms,
                   tok_ms=None if tok_ms is None else np.asarray(tok_ms, float), overrun_ms=over)
