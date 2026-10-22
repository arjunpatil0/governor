"""(a) No governor: unlocked clock, background always on."""
from sim.plant import Action


class NoGovernor:
    name = "a"

    def __init__(self, P):
        self.a = Action(clock=P.UNLOCKED_MHZ, pacing="unaligned", duty=1.0)

    def reset(self, ctx=None):
        return self.a

    def act(self, obs):
        return self.a
