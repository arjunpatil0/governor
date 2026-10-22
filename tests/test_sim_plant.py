"""Simulator plant (sim/plant.py): a two-context time-sliced GPU (fluid model, share 1/S while both run), clock actuation latency and rate limit,
unaligned duty pacing and frame-synchronous (aligned) pacing. Anchored to committed results: W1/B (fg vs clock), A2 SA4 (fg vs duty), L (bg alone).
Called by pytest only; reads result files through sim.params; instruction: "start: simulator -> controllers vs simulator (test-first)"."""
from pathlib import Path

import numpy as np
import pytest

from sim.anchors import a2_run
from sim.params import load_params
from sim.plant import Action, BgSpec, FgSpec, Plant, Scenario, summarise

ROOT = Path(__file__).resolve().parents[1]
PERIOD = 1000.0 / 60.0


@pytest.fixture(scope="module")
def P():
    return load_params(ROOT)


def fg_periodic(cost=4.0, sigma=0.0, active=None, deadline=PERIOD):
    return FgSpec(period_ms=PERIOD, arrivals="periodic", cost_ms=(cost if callable(cost) else (lambda t: cost)), jitter_sigma=sigma, deadline_ms=deadline,
                  active=active or (lambda t: True))


def scen(fg, bg=None, dur=20000.0, **kw):
    return Scenario(name="t", duration_ms=dur, fg=fg, bg=bg, **kw)


LLAMA = BgSpec(kind="llama")


def run(P, sc, act, seed=1):
    return Plant(P, sc, seed=seed).run(act)


# ---------------------------------------------------------------- determinism and the fg-alone plant
def test_same_seed_same_result_different_seed_differs(P):
    sc = scen(fg_periodic(sigma=0.1), LLAMA, dur=3000.0)
    a = Action(clock=1800, pacing="unaligned", duty=0.5)
    r1, r2, r3 = run(P, sc, a, 1), run(P, sc, a, 1), run(P, sc, a, 2)
    assert np.array_equal(r1.lat_ms, r2.lat_ms, equal_nan=True) and not np.array_equal(r1.lat_ms, r3.lat_ms, equal_nan=True)


@pytest.mark.parametrize("clock", [900, 1200, 1800])
def test_fg_alone_latency_is_cost_times_clock_ratio(P, clock):
    s = summarise(run(P, scen(fg_periodic(4.0)), Action(clock=clock)))
    assert s["lat_p50_ms"] == pytest.approx(4.0 * P.fg_ratio(clock), rel=1e-3) and s["miss_frac"] == 0.0 and s["bg_tok_s"] == 0.0


def test_overloaded_fg_counts_unfinished_frames_as_misses(P):
    s = summarise(run(P, scen(fg_periodic(25.0), dur=5000.0), Action(clock=1800)))
    assert s["miss_frac"] > 0.9


def test_fg_cost_steps_scale_latency(P):
    cost = lambda t: 4.0 * (1.3 if 5000 <= t < 10000 else 1.0)          # noqa: E731
    r = run(P, scen(fg_periodic(cost), dur=15000.0), Action(clock=1800))
    arr = r.arr_ms
    assert np.nanmedian(r.lat_ms[(arr >= 5200) & (arr < 9800)]) == pytest.approx(5.2, rel=1e-3)
    assert np.nanmedian(r.lat_ms[arr < 4800]) == pytest.approx(4.0, rel=1e-3)


# ---------------------------------------------------------------- time-slicing and A2 anchors
def test_always_on_bg_slows_a_long_fg_toward_the_share_divisor(P):
    s = summarise(run(P, scen(fg_periodic(5.0), LLAMA), Action(clock=1800, pacing="unaligned", duty=1.0)))
    assert 2.0 < s["lat_mean_ms"] / 5.0 <= P.share_divisor + 0.05


def test_fg_latency_monotone_in_duty(P):
    means = []
    for d in (0.0001, 0.25, 0.5, 1.0):
        vals = [summarise(run(P, scen(fg_periodic(4.0, 0.05), LLAMA, dur=8000.0), Action(clock=1800, pacing="unaligned", duty=d), seed=s))["lat_mean_ms"] for s in (1, 2)]
        means.append(np.mean(vals))
    assert all(a <= b + 0.05 for a, b in zip(means, means[1:]))


def _a2(P, cid, seed=1):
    return a2_run(P, cid, seed=seed)


@pytest.mark.parametrize("cid", ["sa4_fg4_alone", "duty_fg4_d0.25", "duty_fg4_d0.5", "duty_fg4_d0.75", "sa4_fg4_m2", "sa4_fg9_alone", "duty_fg9_d0.25"])
def test_plant_reproduces_A2_SA4_mean_latency_within_20_percent(P, cid):
    s = _a2(P, cid)
    assert s["lat_mean_ms"] == pytest.approx(P.sa4[cid]["lat_mean_ms"], rel=0.20), f"{cid}: sim {s['lat_mean_ms']:.2f} vs measured {P.sa4[cid]['lat_mean_ms']:.2f}"


@pytest.mark.parametrize("cid", ["duty_fg9_d0.5", "duty_fg9_d0.75", "sa4_fg9_m2"])
def test_plant_reproduces_A2_overload_of_the_9ms_frame(P, cid):
    s = _a2(P, cid)
    assert s["lat_mean_ms"] > 10 * P.sa4["sa4_fg9_alone"]["lat_mean_ms"] or s["frac_completed"] < 0.99


# ---------------------------------------------------------------- aligned (frame-synchronous) pacing
def test_aligned_pacing_fills_slack_without_touching_the_fg(P):
    s = summarise(run(P, scen(fg_periodic(4.0), LLAMA), Action(clock=P.UNLOCKED_MHZ, pacing="aligned", guard_ms=0.5)))
    assert s["lat_p99_ms"] == pytest.approx(4.0 * P.fg_ratio(P.UNLOCKED_MHZ), rel=1e-3)
    assert s["miss_frac"] == 0.0 and s["bg_tok_s"] == pytest.approx(60.0, rel=0.05)


def test_aligned_pacing_releases_nothing_when_a_token_does_not_fit(P):
    s = summarise(run(P, scen(fg_periodic(8.0), LLAMA), Action(clock=1800, pacing="aligned", guard_ms=0.5)))
    assert s["bg_tok_s"] == 0.0 and s["lat_p99_ms"] == pytest.approx(8.0, rel=1e-3)


def test_aligned_pacing_needs_a_periodic_fg(P):
    fg = FgSpec(period_ms=25.0, arrivals="poisson", cost_ms=lambda t: 4.0, jitter_sigma=0.0, deadline_ms=PERIOD, active=lambda t: True)
    with pytest.raises(ValueError):
        run(P, scen(fg, LLAMA, dur=1000.0), Action(clock=1800, pacing="aligned", guard_ms=0.5))


def test_bg_runs_free_while_the_fg_is_idle(P):
    r = run(P, scen(fg_periodic(4.0, active=lambda t: t < 5000.0), LLAMA, dur=15000.0), Action(clock=1500, pacing="aligned", guard_ms=0.5))
    idle_tokens = ((r.tok_t_ms >= 7000) & (r.tok_t_ms < 14000)).sum() / 7.0
    assert idle_tokens == pytest.approx(P.tok_s(1500), rel=0.03)


def test_overrun_into_the_next_frame_inflates_that_frame(P):
    """A negative guard releases a token that does not fit and it overruns the next arrival; a positive guard prevents that."""
    sc = scen(fg_periodic(8.0), LLAMA, dur=20000.0)
    small = summarise(run(P, sc, Action(clock=1800, pacing="aligned", guard_ms=-3.0)))
    big = summarise(run(P, sc, Action(clock=1800, pacing="aligned", guard_ms=1.0)))
    assert small["lat_p99_ms"] > big["lat_p99_ms"] + 1.0


# ---------------------------------------------------------------- bg alone, power, clock actuation
def test_bg_alone_matches_L_throughput_and_power(P):
    s = summarise(run(P, scen(fg_periodic(4.0, active=lambda t: False), LLAMA, dur=10000.0), Action(clock=P.UNLOCKED_MHZ, pacing="unaligned", duty=1.0)))
    assert s["bg_tok_s"] == pytest.approx(P.tok_s(P.UNLOCKED_MHZ), rel=0.02) and s["power_w"] == pytest.approx(P.bg_power_w(P.UNLOCKED_MHZ), rel=0.02)


def test_no_work_draws_idle_power(P):
    s = summarise(run(P, scen(fg_periodic(4.0, active=lambda t: False), None, dur=2000.0), Action(clock=1800)))
    assert s["power_w"] == pytest.approx(P.p_idle_w, rel=1e-6)


class Switch:
    def __init__(self, seq):
        self.seq = seq

    def reset(self, ctx=None):
        return Action(clock=1800)

    def act(self, obs):
        return Action(clock=self.seq[(int(obs.t_ms // 100)) % len(self.seq)])


def test_clock_change_takes_effect_after_the_actuation_latency(P):
    r = run(P, scen(fg_periodic(4.0), dur=3000.0), Switch([900]))
    t900 = min(t for t, f in r.clock_log if f == 900)
    assert 100 + 440 <= t900 <= 100 + 460 + 1


def test_clock_changes_are_rate_limited(P):
    r = run(P, scen(fg_periodic(4.0), dur=10000.0), Switch([900, 1200, 1500]))
    assert r.n_clock_changes <= 10000.0 / 1000.0 + 1 and r.n_rate_limited > 0


def test_clock_cap_clamps_the_effective_clock(P):
    r = run(P, scen(fg_periodic(4.0), dur=6000.0, clock_cap=[(2000.0, 1200.0)]), Action(clock=1800))
    assert all(f <= 1200 for t, f in r.clock_log if t >= 2000.0) and any(f == 1800 for t, f in r.clock_log)


def test_energy_is_integral_of_segment_power(P):
    r = run(P, scen(fg_periodic(4.0), dur=4000.0), Action(clock=1800))
    s = summarise(r)
    assert s["power_w"] == pytest.approx(r.energy_j / 4.0, rel=1e-9)


# ---------------------------------------------------------------- empirical token-time jitter (sensitivity follow-up)
def test_token_jitter_keeps_the_L_throughput_but_makes_a_zero_guard_overrun(P):
    alone = summarise(run(P, scen(fg_periodic(4.0, active=lambda t: False), BgSpec(kind="llama", jitter=True), dur=20000.0), Action(clock=P.UNLOCKED_MHZ, pacing="unaligned", duty=1.0)))
    assert alone["bg_tok_s"] == pytest.approx(P.tok_s(P.UNLOCKED_MHZ), rel=0.03)
    sc = scen(fg_periodic(6.0), BgSpec(kind="llama", jitter=True), dur=30000.0)
    g0 = summarise(run(P, sc, Action(clock=P.UNLOCKED_MHZ, pacing="aligned", guard_ms=0.0)))
    g3 = summarise(run(P, sc, Action(clock=P.UNLOCKED_MHZ, pacing="aligned", guard_ms=3.0)))
    assert g0["miss_frac"] > g3["miss_frac"] and g0["lat_p99_ms"] > g3["lat_p99_ms"]
