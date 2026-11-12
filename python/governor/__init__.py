"""governor: the reusable part of the project as an importable package. Nothing here is new behaviour: the three names wrap python/slackhint (the frame-hint record, byte-compatible with
include/slackhint.h) and compose its rules exactly as the experiment's driver and examples/demo_slack_hint.py do. Spec: docs/FRAME_HINT_SPEC.md. Windows only (named file mappings).
   FrameHintWriter  the app side: frame_started(now, next_deadline), frame_done(now, next_deadline), idle(now)   (= slackhint.Producer)
   FrameHintReader  the worker side: get(now) -> (busy, next_deadline)                                           (= slackhint.Consumer)
   DeadlineGate     the worker's start rule: may_start(now) is True only while the app is idle and a work unit is expected to end `guard_s` before the next deadline,
                    and the duty gap since the previous unit has passed; unit_done(t_start, t_end) feeds the duration estimate and the duty gap.
All times are seconds on one clock shared by both sides (time.perf_counter() on Windows, the QPC timeline)."""
import slackhint as _sh
from slackhint import INF, STALE_S, now_s  # noqa: F401  (re-exported)

__version__ = "2.0.1"
__all__ = ["FrameHintWriter", "FrameHintReader", "DeadlineGate", "now_s", "INF", "STALE_S"]


class FrameHintWriter(_sh.Producer):
    """One writer per block. create=True initialises the record (the first creator); create=False attaches to an existing one."""


class FrameHintReader(_sh.Consumer):
    """Attaches to an existing record (raises ValueError if the geometry does not match: no silent fallback)."""


class DeadlineGate:
    """Start rule of a background worker. reader: a FrameHintReader. guard_s: slack kept free before the next deadline (the experiments started at 0.5 ms). duty: 1 = no gap after a unit, 0 = never,
    in between = the unit's duration times (1/duty - 1) of gap (the power throttle of the experiments). stale_s: a record older than this means the app is idle (0.1 s)."""

    def __init__(self, reader, guard_s=0.0005, duty=1.0, stale_s=STALE_S, estimator=None):
        self.reader, self.guard_s, self.duty, self.stale_s = reader, float(guard_s), float(duty), float(stale_s)
        self.estimator = estimator if estimator is not None else _sh.Estimator()
        self.wake_s = 0.0
        self._next_at_start = INF

    def estimate_s(self):
        """Duration estimate of one work unit: median of the last 8 units that did not overlap a frame, else the EWMA of all units; 0.0 before the first unit."""
        return self.estimator.value()

    def may_start(self, now):
        """True if a unit may start at `now` (seconds). Remembers the deadline it was gated against for unit_done."""
        busy, next_deadline = self.reader.get(now, self.stale_s)
        ok = now >= self.wake_s and _sh.may_start(now, busy, self.estimate_s(), self.guard_s, next_deadline)
        if ok:
            self._next_at_start = next_deadline
        return ok

    def unit_done(self, t_start, t_end):
        """Record a finished unit [t_start, t_end]: updates the estimate (a unit that overlapped a frame does not count towards the clean median) and the duty gap. Returns True if it overlapped a frame."""
        overlapped = _sh.unit_overlapped(t_end, self._next_at_start, t_start, self.reader.have, self.reader.last[2])
        self.estimator.push(t_end - t_start, overlapped)
        self.wake_s = _sh.duty_wake(t_start, t_end, self.duty)
        return overlapped
