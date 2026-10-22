"""A2 SA4 anchor runs for the plant: the same fg/bg design as the measured cells (data/w2_A_secondary_results.md SA4), simulated for 60 s.
Used by tests/test_sim_plant.py and by sim/calibrate.py (fits the one free plant parameter, the time-slice share divisor)."""
from sim.plant import Action, BgSpec, FgSpec, Plant, Scenario, summarise

ANCHOR_IDS = ("sa4_fg4_alone", "duty_fg4_d0.25", "duty_fg4_d0.5", "duty_fg4_d0.75", "sa4_fg4_m2", "sa4_fg9_alone", "duty_fg9_d0.25")
OVERLOAD_IDS = ("duty_fg9_d0.5", "duty_fg9_d0.75", "sa4_fg9_m2")
PERIOD_60HZ = 1000.0 / 60.0


def a2_run(P, cid, seed=1, dur_ms=60000.0):
    row = P.sa4[cid]
    d = row["duty"]
    if row["fg_ms"] == 4.0:      # 4 ms fg: Poisson 40 Hz (experiments/w2_colocation.yaml SA4_foreground_size)
        fg = FgSpec(period_ms=25.0, arrivals="poisson", cost_ms=lambda t: P.sa4["sa4_fg4_alone"]["fg_gpu_p50_ms"], jitter_sigma=0.05, deadline_ms=2000.0, active=lambda t: True)
    else:                        # 9 ms frame: periodic 60 Hz (the B fma frame)
        fg = FgSpec(period_ms=PERIOD_60HZ, arrivals="periodic", cost_ms=lambda t: P.sa4["sa4_fg9_alone"]["fg_gpu_p50_ms"], jitter_sigma=0.01, deadline_ms=2000.0, active=lambda t: True)
    bg = BgSpec(kind="slice", slice_ms=row["m_ms"]) if d > 0 else None
    sc = Scenario(name=cid, duration_ms=dur_ms, fg=fg, bg=bg)
    return summarise(Plant(P, sc, seed=seed).run(Action(clock=1800, pacing="unaligned", duty=d if d > 0 else 1.0)))
