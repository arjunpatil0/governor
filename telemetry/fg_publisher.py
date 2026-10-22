"""Foreground-side publisher: frame records for the daemon / governor and the pace block the governed driver reads for slack filling.
Frame ring record (QPC seconds): [t_sched, t_start, t_end]. Pace block: [fg_busy (0/1), t_next_arrival_s, t_updated_s]; the driver treats a block older than
100 ms as 'fg idle'. The fg calls frame_started() when it starts a frame, frame_done() when it completes (with the next scheduled arrival) and idle() when it stops producing frames."""
import math


class FramePublisher:
    def __init__(self, frame_ring, pace_block):
        self.ring, self.pace = frame_ring, pace_block

    def frame_started(self, t_now, t_next):
        self.pace.write([1.0, t_next, t_now])

    def frame_done(self, t_sched, t_start, t_end, t_next, t_now):
        self.ring.push([t_sched, t_start, t_end])
        self.pace.write([0.0, t_next, t_now])

    def idle(self, t_now):
        self.pace.write([0.0, math.inf, t_now])
