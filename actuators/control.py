"""Applies a sim.plant.Action to the real system: pacing values to the governed driver through a shared SeqBlock, the SM clock through the admin helper client.
Control block layout (governor -> driver): [pacing (0 = unaligned duty, 1 = aligned slack filling), duty, guard_ms].
Clock: an Action clock at or above the unlocked level means RESET (clock lock released), anything else LOCK <mhz>. A command the helper refuses (rate limit) is
retried on the next apply because the commanded clock is only recorded after the helper accepted it. Every apply also sends a heartbeat (watchdog)."""


class ControlActuator:
    def __init__(self, block, clock_client, unlocked_mhz):
        self.block, self.clk, self.unlocked = block, clock_client, float(unlocked_mhz)
        self.cur = None                                        # last clock accepted by the helper (None before the first apply)

    def apply(self, action):
        self.block.write([1.0 if action.pacing == "aligned" else 0.0, float(action.duty), float(action.guard_ms)])
        want = "unlocked" if float(action.clock) >= self.unlocked else float(action.clock)
        if want != self.cur:
            ok = self.clk.reset() if want == "unlocked" else self.clk.lock(int(want))
            if ok:
                self.cur = want
        self.clk.heartbeat()
