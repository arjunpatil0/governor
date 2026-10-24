"""Governor loop: ring data -> Obs -> controller.act -> actuators. The controllers are the same objects the simulator evaluates."""


import dataclasses


class Governor:
    def __init__(self, controller, obs_builder, actuator, frame_ring, token_ring, period_ms, deadline_ms, params=None):
        self.ctl, self.ob, self.act_, self.frames, self.tokens = controller, obs_builder, actuator, frame_ring, token_ring
        self.period_ms, self.deadline_ms, self.params = period_ms, deadline_ms, params
        self.last_obs = None
        self.clamped = []                                           # (t_ms, raw MHz, clamped MHz): every live clock reading mapped into the measured model range
        self._t = self._e = None

    def start(self, t_ms, startup_reset=None):
        """startup_reset: callable run FIRST (e.g. actuators.startup_reset.reset_clocks bound to the helper client); if it raises, nothing else starts."""
        if startup_reset is not None:
            startup_reset()
        a = self.ctl.reset(dict(params=self.params, period_ms=self.period_ms, deadline_ms=self.deadline_ms))
        self.act_.apply(a)
        self._t = t_ms
        return a

    def step(self, t_ms, energy_j, clock_mhz, power_w=None):
        """energy_j is the cumulative NVML energy counter (J); the power over the tick is its delta / dt. power_w (plan addendum O-4): a power measured elsewhere (the mean of the NVML power samples), which REPLACES
        the energy-derived one so that the loop does not have to read the counter every tick (every extra read adds ~4.2 J of phantom energy, journal 0005)."""
        if self.params is not None and hasattr(self.params, "clamp_clock"):
            c = self.params.clamp_clock(clock_mhz)
            if c != float(clock_mhz):
                self.clamped.append((float(t_ms), float(clock_mhz), c))
            clock_mhz = c
        fr, _ = self.frames.read_new()
        tk, _ = self.tokens.read_new()
        dt = (t_ms - self._t) / 1000.0
        de = 0.0 if self._e is None else energy_j - self._e
        self._t, self._e = t_ms, energy_j
        tok_ms = tk[:, 1] if tk.ndim == 2 and tk.shape[1] >= 2 else None
        tok_end = tk[:, 0] if tok_ms is not None else None          # token ring record [t_end_s, token_ms] (older one-field rings: no durations)
        self.last_obs = self.ob.build(fr, len(tk), de, dt, clock_mhz, t_ms, tok_ms=tok_ms, tok_end=tok_end)
        if power_w is not None:
            self.last_obs = dataclasses.replace(self.last_obs, power_w=float(power_w))
        a = self.ctl.act(self.last_obs)
        self.act_.apply(a)
        return a
