import pytest

from tools.realgame import decision as d

REPS = 5
IDLE = 0


def solo(p99=100.0, hitch=0.0, reps=REPS):
    return [({"p99": p99, "hitch": hitch}, {"p99": p99, "hitch": hitch}) for _ in range(reps)]


import tempfile
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="rg_dec_"))
GOOD_TOKENS = _TMP / "tokens.csv"
GOOD_TOKENS.write_text("t_tok_end_s,dur_ms,kind\n" + "".join(f"{i * 0.01:.2f},10.0,token\n" for i in range(1, 1000)))      # a token every 10 ms over [0, 10)


def arm(worsen_pct=0.0, hitch_pp=0.0, toks=50.0, reps=REPS, per_rep=None, base=100.0):
    """cells whose paired values against solo(base) are exactly worsen_pct and hitch_pp (per_rep overrides: list of (w, h))."""
    vals = per_rep or [(worsen_pct, hitch_pp)] * reps
    return [{"p99": base * (1 + w / 100.0), "hitch": h, "toks": toks, "tokens_csv": GOOD_TOKENS, "t_open": 0.0, "t_close": 10.0} for w, h in vals]


def run(arms, solo_cells=None, alone=100.0, pred=True, readbacks=(IDLE,) * 10):
    return d.evaluate(solo=solo_cells or solo(), arms=arms, llm_alone_toks=alone, predictability_pass=pred, prio_readbacks=list(readbacks), idle_class=IDLE)


def decide(arms, **kw):
    return run(arms, **kw)["branch"]


GOOD = dict(worsen_pct=0.0, hitch_pp=0.0)
HARM = dict(worsen_pct=20.0, hitch_pp=3.0, toks=50.0)
BAD = dict(worsen_pct=8.0, hitch_pp=0.6, toks=50.0)       # neither within nor harmful, but not within


def arms(ungated, prio, igpu, duty=None):
    return {"UNGATED": ungated, "PRIO_IDLE": prio, "IGPU": igpu, "DUTY50": duty or arm(**BAD)}


# ---- within_limits thresholds
@pytest.mark.parametrize("w,expected", [(4.99, True), (5.01, False)])
def test_worsening_threshold(w, expected):
    assert d.within_limits(d.paired(solo(), arm(w, 0.0))) is expected


@pytest.mark.parametrize("h,expected", [(0.49, True), (0.51, False)])
def test_hitch_threshold(h, expected):
    assert d.within_limits(d.paired(solo(), arm(0.0, h))) is expected


def test_rep_at_exactly_10_percent_fails_clause_c():
    per = [(10.0, 0.0), (0.0, 0.0), (0.0, 0.0), (0.0, 0.0), (0.0, 0.0)]     # mean 2%, hitch 0: only clause c can fail
    assert d.within_limits(d.paired(solo(), arm(per_rep=per))) is False
    per = [(9.99, 0.0)] + [(0.0, 0.0)] * 4
    assert d.within_limits(d.paired(solo(), arm(per_rep=per))) is True


def test_rep_at_exactly_1pp_fails_clause_c():
    per = [(0.0, 1.0)] + [(0.0, 0.0)] * 4                                   # mean 0.2 pp
    assert d.within_limits(d.paired(solo(), arm(per_rep=per))) is False
    per = [(0.0, 0.99)] + [(0.0, 0.0)] * 4
    assert d.within_limits(d.paired(solo(), arm(per_rep=per))) is True


@pytest.mark.parametrize("w,h,expected", [(15.0, 2.0, True), (14.99, 2.0, False), (15.0, 1.99, False), (30, 5, True)])
def test_harmful_thresholds(w, h, expected):
    assert d.harmful(d.paired(solo(), arm(w, h))) is expected


def test_pairing_uses_mean_of_the_reps_two_solos():
    s = [({"p99": 90.0, "hitch": 0.0}, {"p99": 110.0, "hitch": 0.4})] * REPS
    p = d.paired(s, [{"p99": 110.0, "hitch": 1.2, "toks": 1.0}] * REPS)
    assert p[0]["worsening_pct"] == pytest.approx(10.0) and p[0]["hitch_pp"] == pytest.approx(1.0)


def test_paired_length_mismatch_raises():
    with pytest.raises(ValueError):
        d.paired(solo(), arm(reps=3))


# ---- noise precondition
def solo_noise(rel_pct, hitch_diff=0.0, hitch=0.0):
    a = 100.0 * (1 - rel_pct / 200.0)   # |a-b| / mean = rel_pct / 100
    b = 100.0 * (1 + rel_pct / 200.0)
    return [({"p99": a, "hitch": hitch}, {"p99": b, "hitch": hitch + hitch_diff})] * REPS


@pytest.mark.parametrize("rel,ok", [(2.49, True), (2.51, False)])
def test_noise_p99_floor(rel, ok):
    assert d.noise_precondition(solo_noise(rel))["ok"] is ok


@pytest.mark.parametrize("hd,ok", [(0.24, True), (0.26, False)])
def test_noise_hitch_diff_floor(hd, ok):
    assert d.noise_precondition(solo_noise(0.0, hitch_diff=hd))["ok"] is ok


def test_noise_solo_hitch_below_1pct_in_every_rep():
    s = solo_noise(0.0)
    s[2] = ({"p99": 100.0, "hitch": 1.0}, {"p99": 100.0, "hitch": 1.0})
    assert d.noise_precondition(s)["ok"] is False
    s[2] = ({"p99": 100.0, "hitch": 0.99}, {"p99": 100.0, "hitch": 0.99})
    assert d.noise_precondition(s)["ok"] is True


def test_drift_is_signed_and_separate():
    s = [({"p99": 100.0, "hitch": 0.5}, {"p99": 103.0, "hitch": 0.2})] * REPS
    n = d.noise_precondition(s)
    assert n["drift_p99_pct_mean"] == pytest.approx(3.0 / 101.5 * 100) and n["drift_hitch_pp_mean"] == pytest.approx(-0.3)


def test_noise_failure_blocks_within_claim_but_not_harmful():
    r = run(arms(arm(**HARM), arm(**GOOD), arm(**BAD)), solo_cells=solo_noise(4.0))
    assert r["noise"]["ok"] is False
    assert r["arms"]["UNGATED"]["harmful"] is True
    assert r["arms"]["PRIO_IDLE"]["within_limits"] is True and r["arms"]["PRIO_IDLE"]["within_claim"] is False
    assert r["branch"] == "OPEN"        # the PRIO_IDLE claim is blocked and a nominally-within arm blocks BUILD_THE_GATE


# ---- branches
def test_no_problem():
    r = run(arms(arm(**GOOD), arm(**BAD), arm(**BAD)))
    assert r["branch"] == "NO_PROBLEM" and r["reasons"]


def test_no_problem_needs_precondition():
    assert decide(arms(arm(**GOOD), arm(**BAD), arm(**BAD)), solo_cells=solo_noise(4.0)) == "OPEN"


def test_simple_fix_prio_ratio_threshold():
    ung = arm(**HARM)                                    # tok/s 50
    ok = arm(**GOOD, toks=35.0)                          # ratio 0.70 exactly -> qualifies
    low = arm(**GOOD, toks=34.9)
    assert decide(arms(ung, ok, arm(**BAD))) == "SIMPLE_FIX"
    assert decide(arms(ung, low, arm(**BAD))) == "FIX_TOO_SLOW"


def test_simple_fix_igpu_absolute_threshold():
    ung = arm(**HARM)
    assert decide(arms(ung, arm(**BAD), arm(**GOOD, toks=15.0))) == "SIMPLE_FIX"
    assert decide(arms(ung, arm(**BAD), arm(**GOOD, toks=14.99))) == "FIX_TOO_SLOW"


def test_simple_fix_both_qualify_names_higher_toks():
    r = run(arms(arm(**HARM), arm(**GOOD, toks=40.0), arm(**GOOD, toks=20.0)))
    assert r["branch"] == "SIMPLE_FIX" and r["fix"] == "PRIO_IDLE" and r["fixes"] == ["PRIO_IDLE", "IGPU"]
    r = run(arms(arm(**HARM), arm(**GOOD, toks=36.0), arm(**GOOD, toks=60.0)))
    assert r["fix"] == "IGPU"


def test_fix_too_slow_requires_ungated_harmful():
    ung = arm(worsen_pct=8.0, hitch_pp=1.0, toks=50.0)   # neither within nor harmful
    assert decide(arms(ung, arm(**GOOD, toks=10.0), arm(**BAD))) == "OPEN"


def test_build_the_gate_requires_every_condition():
    base = arms(arm(**HARM), arm(**BAD), arm(**BAD))
    assert decide(base) == "BUILD_THE_GATE"
    assert decide(base, pred=False) == "OPEN"
    assert decide(arms(arm(worsen_pct=8, hitch_pp=1.0), arm(**BAD), arm(**BAD))) == "OPEN"          # UNGATED not harmful
    assert decide(dict(base, IGPU=None)) == "BUILD_THE_GATE"                                        # IGPU dropped: evaluated on PRIO_IDLE alone (amendment 11)
    assert decide(base, readbacks=(IDLE, 2)) == "OPEN"                                              # PRIO_IDLE void
    assert decide(arms(arm(**HARM), arm(**GOOD, toks=40.0), arm(**BAD))) != "BUILD_THE_GATE"        # PRIO_IDLE within
    assert decide(arms(arm(**HARM), arm(**BAD), arm(**GOOD, toks=40.0))) != "BUILD_THE_GATE"        # IGPU within


def test_igpu_dropped_prio_within_and_fast_is_simple_fix():
    r = run({"UNGATED": arm(**HARM), "PRIO_IDLE": arm(**GOOD, toks=40.0), "IGPU": None})
    assert r["branch"] == "SIMPLE_FIX" and r["fix"] == "PRIO_IDLE" and r["igpu_tested"] is False


def test_igpu_dropped_prio_within_but_slow_is_fix_too_slow():
    assert decide({"UNGATED": arm(**HARM), "PRIO_IDLE": arm(**GOOD, toks=10.0), "IGPU": None}) == "FIX_TOO_SLOW"


def test_igpu_dropped_prio_not_within_harmful_ungated_predictable_is_build_the_gate():
    r = run({"UNGATED": arm(**HARM), "PRIO_IDLE": arm(**BAD), "IGPU": None})
    assert r["branch"] == "BUILD_THE_GATE" and r["igpu_tested"] is False
    assert any("IGPU option not tested" in x for x in r["reasons"])
    assert decide({"UNGATED": arm(**HARM), "PRIO_IDLE": arm(**BAD)}) == "BUILD_THE_GATE"              # arm key absent altogether
    assert decide({"UNGATED": arm(**HARM), "PRIO_IDLE": arm(**BAD), "IGPU": None}, pred=False) == "OPEN"
    assert decide({"UNGATED": arm(worsen_pct=8, hitch_pp=1.0), "PRIO_IDLE": arm(**BAD), "IGPU": None}) == "OPEN"


def test_igpu_dropped_prio_void_is_open():
    r = run({"UNGATED": arm(**HARM), "PRIO_IDLE": arm(**BAD), "IGPU": None}, readbacks=(IDLE, 2))
    assert r["branch"] == "OPEN" and r["igpu_tested"] is False
    assert decide({"UNGATED": arm(**HARM), "PRIO_IDLE": arm(**BAD), "IGPU": None}, readbacks=()) == "OPEN"


def test_igpu_measured_behaves_as_before():
    r = run(arms(arm(**HARM), arm(**BAD), arm(**BAD)))
    assert r["branch"] == "BUILD_THE_GATE" and r["igpu_tested"] is True and not any("not tested" in x for x in r["reasons"])
    assert decide(arms(arm(**HARM), arm(**BAD), arm(**GOOD, toks=40.0))) != "BUILD_THE_GATE"        # IGPU within blocks the gate


# ---- per-rep noise check (amendment 14)
def solo_pair(p1=100.0, p2=100.0, h1=0.0, h2=0.0):
    return {"p99": p1, "hitch": h1}, {"p99": p2, "hitch": h2}


@pytest.mark.parametrize("rel,ok", [(2.49, True), (2.51, False), (2.5, False)])
def test_rep_noise_p99_boundary(rel, ok):
    a, b = 100.0 * (1 - rel / 200.0), 100.0 * (1 + rel / 200.0)
    good, reasons = d.rep_noise_check(*solo_pair(a, b))
    assert good is ok and bool(reasons) is (not ok)


@pytest.mark.parametrize("hd,ok", [(0.24, True), (0.26, False), (0.25, False)])
def test_rep_noise_hitch_diff_boundary(hd, ok):
    good, reasons = d.rep_noise_check(*solo_pair(h1=0.5, h2=0.5 + hd))
    assert good is ok and bool(reasons) is (not ok)


@pytest.mark.parametrize("h,ok", [(0.99, True), (1.0, False)])
def test_rep_noise_solo_hitch_boundary(h, ok):
    assert d.rep_noise_check(*solo_pair(h1=h, h2=h))[0] is ok            # equal hitch shares: only the 1% clause can fail
    assert d.rep_noise_check(*solo_pair(h1=h, h2=h - 0.1))[0] is ok      # either SOLO
    assert d.rep_noise_check(*solo_pair(h1=h - 0.1, h2=h))[0] is ok


def test_rep_noise_accepts_frame_dict_keys_and_lists_all_reasons():
    ok, reasons = d.rep_noise_check({"p99": 100.0, "hitch_share": 1.5}, {"p99": 110.0, "hitch_share": 0.0})
    assert ok is False and len(reasons) == 3


def test_prio_idle_void_is_not_within_and_cannot_support_gate():
    a = arms(arm(**HARM), arm(**GOOD, toks=45.0), arm(**BAD))
    r = run(a, readbacks=(IDLE, IDLE, 2))
    assert r["prio_idle_valid"] is False and r["arms"]["PRIO_IDLE"]["within_claim"] is False
    assert r["branch"] == "OPEN"
    assert decide(a, readbacks=(IDLE,) * 10) == "SIMPLE_FIX"
    assert decide(a, readbacks=()) == "OPEN"          # no readback recorded = not verified = void


def test_ungated_validity_25_percent_of_llm_alone():
    base = arm(**GOOD)
    assert run(arms(arm(**GOOD, toks=24.0), base, base))["branch"] == "VOID"
    assert "voided" in " ".join(run(arms(arm(**GOOD, toks=24.0), base, base))["reasons"])
    assert run(arms(arm(**GOOD, toks=26.0), base, base))["branch"] == "NO_PROBLEM"
    assert run(arms(arm(**GOOD, toks=25.0), base, base))["branch"] == "VOID"            # strictly above 25%
    mixed = arm(**GOOD, toks=60.0)
    mixed[3]["toks"] = 20.0                                                              # one cell without tokens throughout
    assert run(arms(mixed, base, base))["branch"] == "VOID"


def test_duty50_is_reference_only():
    ung = arm(**HARM)
    # a perfect DUTY50 changes nothing
    assert decide(arms(ung, arm(**BAD), arm(**BAD), duty=arm(**GOOD, toks=99.0))) == "BUILD_THE_GATE"
    assert decide({"UNGATED": ung, "PRIO_IDLE": arm(**BAD), "IGPU": arm(**BAD)}) == "BUILD_THE_GATE"   # absent DUTY50 is fine
    r = run(arms(ung, arm(**BAD), arm(**BAD), duty=arm(**GOOD)))
    assert "DUTY50" in r["arms"] and r["arms"]["DUTY50"]["reference_only"] is True


def test_branch_order_no_problem_before_simple_fix():
    r = run(arms(arm(**GOOD), arm(**GOOD, toks=50.0), arm(**GOOD, toks=50.0)))
    assert r["branch"] == "NO_PROBLEM"


def test_simple_fix_before_build_gate_and_open_default():
    assert decide(arms(arm(worsen_pct=10, hitch_pp=1.0), arm(**BAD), arm(**BAD))) == "OPEN"


def test_stats_reported_for_information():
    r = run(arms(arm(per_rep=[(10, 1), (20, 2), (30, 3), (40, 4), (50, 5)]), arm(**BAD), arm(**BAD)))
    s = r["arms"]["UNGATED"]["worsening_pct_stats"]
    assert s["mean"] == pytest.approx(30.0) and s["median"] == pytest.approx(30.0) and s["worst"] == pytest.approx(50.0)
    assert s["boot_n"] == 10000 and 10 <= s["boot_lo"] <= s["boot_hi"] <= 50
    assert d.summarize([1, 2, 3, 4, 5]) == d.summarize([1, 2, 3, 4, 5])        # seeded: reproducible


def test_decide_returns_branch_and_reasons():
    branch, reasons = d.decide(solo=solo(), arms=arms(arm(**HARM), arm(**BAD), arm(**BAD)), llm_alone_toks=100.0, predictability_pass=True,
                               prio_readbacks=[IDLE] * 10, idle_class=IDLE)
    assert branch == "BUILD_THE_GATE" and isinstance(reasons, list) and reasons


def test_missing_ungated_raises():
    with pytest.raises(ValueError):
        run({"PRIO_IDLE": arm(**BAD), "IGPU": None})
