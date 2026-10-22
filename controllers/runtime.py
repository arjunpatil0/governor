"""Governor loop: ring data -> Obs -> controller.act -> actuators. The controllers are the same objects the simulator evaluates."""


class Governor:
    def __init__(self, controller, obs_builder, actuator, frame_ring, token_ring, period_ms, deadline_ms, params=None):
        self.ctl, self.ob, self.act_, self.frames, self.tokens = controller, obs_builder, actuator, frame_ring, token_ring
        self.period_ms, self.deadline_ms, self.params = period_ms, deadline_ms, params
        self.last_obs = None
        self._t = self._e = None

    def start(self, t_ms, startup_reset=None):
        """startup_reset: callable run FIRST (e.g. actuators.startup_reset.reset_clocks bound to the helper client); if it raises, nothing else starts."""
        if startup_reset is not None:
            startup_reset()
        a = self.ctl.reset(dict(params=self.params, period_ms=self.period_ms, deadline_ms=self.deadline_ms))
        self.act_.apply(a)
        self._t = t_ms
        return a

    def step(self, t_ms, energy_j, clock_mhz):
        """energy_j is the cumulative NVML energy counter (J); the power over the tick is its delta / dt."""
        fr, _ = self.frames.read_new()
        tk, _ = self.tokens.read_new()
        dt = (t_ms - self._t) / 1000.0
        de = 0.0 if self._e is None else energy_j - self._e
        self._t, self._e = t_ms, energy_j
        tok_ms = tk[:, 1] if tk.ndim == 2 and tk.shape[1] >= 2 else None          # token ring record [t_end_s, token_ms] (older one-field rings: no durations)
        self.last_obs = self.ob.build(fr, len(tk), de, dt, clock_mhz, t_ms, tok_ms=tok_ms)
        a = self.ctl.act(self.last_obs)
        self.act_.apply(a)
        return a
