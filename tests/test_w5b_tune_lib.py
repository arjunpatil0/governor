"""W5b tuning blocks T1-T3: the pure plan / decision logic (experiments/w5b/tune_lib.py), exactly as stated in plan addendum O section 4 (docs/W5B_ADDENDUM_O.md, committed before any W5b data):
c0 search 7..11 with the arm-a > 5% precondition, the 70-static sweep, HW0 at 60 W, stage-2 top 8 per budget, g'B per budget, c'B constants grid, d'B margin rule, the fixed c'B pacing mode.
Instruction (Arjun, 2026-10-23): "give me the T1-T3 session commands, set up to run unattended overnight (fresh-restart check, helper start, chained blocks)"."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "experiments" / "w5b")); sys.path.insert(0, str(ROOT))
import tune_lib as tl  # noqa: E402

WORKLOADS = ("llama32_1b", "llama32_3b", "phi35_mini")


def metrics(miss=0.0, tok=30.0, power=40.0, c0m=None):
    return dict(miss=miss, tok_s=tok, power_w=power, c0m=c0m, power_sampled_w=power - 0.8)         # the counter reads 0.8 W above the sampled mean in the synthetic world


def run_plan(fake, max_rounds=60, results=None):
    """Drive the plan with a fake executor; returns (results, final plan answer)."""
    results = {} if results is None else results
    for _ in range(max_rounds):
        ans = tl.next_batch(results)
        if ans["batch"]:
            for spec in ans["batch"]:
                results[spec["id"]] = fake(spec)
            continue
        return results, ans
    raise AssertionError("plan did not finish")


def fake_world(good_c0=8, c0m_of=lambda c0: 0.745 * c0):
    """A synthetic world: arm a misses 10% at every c0; the 70 statics are feasible only at c0 >= good_c0 (aligned, locked clock) with tok = 40 (20 below duty 1); everything else infeasible."""
    def fake(spec):
        k = spec["kind"]
        if k == "bg_alone":
            return metrics(tok={"llama32_1b": 120.0, "llama32_3b": 100.0, "phi35_mini": 80.0}[spec["workload"]], power=70.0)
        if k == "fg_alone":
            return dict(metrics(c0m=c0m_of(spec["c0"])), c0m_unlocked=0.954 * c0m_of(spec["c0"]), sm_locked_median=1800.0, sm_unlocked_median=1890.0)
        if k == "arm_a":
            return metrics(miss=0.10, tok=40.0, power=80.0)
        if k == "static":
            s = spec["setting"]
            ok = spec["c0"] >= good_c0 and s["mode"] == "aligned" and s["clock"] != "unlocked"
            return metrics(miss=0.0 if ok else 0.3, tok=40.0 if s["duty"] == 1.0 else 20.0, power=50.0 if ok else 70.0)
        if k == "cB":
            return metrics(miss=0.004, tok=35.0 + 10 * spec["params"]["ki"], power=55.0)
        if k == "dB":
            return metrics(miss=0.03 if spec["params"]["margin"] < 0.2 else 0.004, tok=45.0 - 20 * spec["params"]["margin"], power=55.0)
        return metrics()
    return fake


def test_the_70_statics_are_7_clocks_times_10_pacing_configurations_with_unique_ids():
    s = tl.settings70()
    assert len(s) == 70 and len({x["sid"] for x in s}) == 70
    assert sum(1 for x in s if x["mode"] == "aligned") == 42 and sum(1 for x in s if x["clock"] == "unlocked") == 10


def test_feasible_needs_slo_budget_and_a_fifth_of_the_background_alone_rate():
    assert tl.feasible(metrics(miss=0.01, tok=20.0, power=60.0), 60.0, 100.0)
    assert not tl.feasible(metrics(miss=0.0101, tok=50.0), 60.0, 100.0)
    assert not tl.feasible(metrics(miss=0.0, tok=50.0, power=60.1), 60.0, 100.0)
    assert not tl.feasible(metrics(miss=0.0, tok=19.9, power=40.0), 60.0, 100.0)          # an aligned setting that admits no token must not pass


def test_first_batches_are_the_discarded_cell_then_the_three_background_alone_references():
    ans = tl.next_batch({})
    assert [c["id"] for c in ans["batch"]] == ["t1_discard"] and ans["batch"][0]["discard"] is True
    res = {"t1_discard": metrics()}
    ans = tl.next_batch(res)
    assert sorted(c["workload"] for c in ans["batch"]) == sorted(WORKLOADS) and all(c["kind"] == "bg_alone" for c in ans["batch"])


def test_c0_search_skips_a_c0_where_arm_a_does_not_miss_more_than_5_percent_and_sweeps_the_first_that_does():
    base = fake_world(good_c0=7)

    def f(spec):
        if spec["kind"] == "arm_a" and spec["c0"] == 7:
            return metrics(miss=0.03)                                                    # not enough overload at 7: gate fails without a sweep
        return base(spec)
    res, ans = run_plan(f)
    assert not any(k.startswith("st_c7_") for k in res) and any(k.startswith("st_c8_") for k in res)
    assert ans["decisions"]["c0"] == 8


def test_chosen_c0_is_the_smallest_with_a_feasible_static_and_failed_sweeps_stay_in_the_data():
    res, ans = run_plan(fake_world(good_c0=9))
    d = ans["decisions"]
    assert d["c0"] == 9 and sum(1 for k in res if k.startswith("st_c7_")) == 70 and sum(1 for k in res if k.startswith("st_c8_")) == 70 and sum(1 for k in res if k.startswith("st_c9_llama32_3b_S1_")) == 70


def test_no_feasible_c0_stops_with_a_report_and_invents_no_other_c0():
    res, ans = run_plan(fake_world(good_c0=99))
    assert ans["stop"] and "no c0" in ans["stop"] and ans["decisions"].get("c0") is None
    assert not any(k.startswith("st_c12_") for k in res)


def test_stage_two_runs_the_top_eight_per_budget_on_three_workloads_and_two_scenes_without_repeating_cells():
    res, ans = run_plan(fake_world(good_c0=8))
    s2 = [k for k in res if k.startswith("st_c8_") and not k.startswith("st_c8_llama32_3b_S1_")]
    assert len(s2) > 0 and len(s2) == len(set(s2))
    top = ans["decisions"]["stage1_top"]["60"]
    sids = {c.split("_S1_", 1)[1] for c in res if c.startswith("st_c8_llama32_3b_S1_")}
    assert len(top) == 8 and set(top) <= sids


def test_g_b_is_the_best_setting_feasible_in_all_six_cells_else_the_one_with_most_feasible_cells():
    res, ans = run_plan(fake_world(good_c0=8))
    g = ans["decisions"]["g_b"]["60"]
    assert g["feasible_in_all"] is True and g["setting"]["duty"] == 1.0 and g["setting"]["mode"] == "aligned"
    res2, ans2 = run_plan(fake_world(good_c0=8), results=dict(res))
    assert ans2["decisions"]["g_b"]["60"]["setting"] == g["setting"]                  # deterministic recomputation from stored cells


def test_c_b_switches_mode_itself_so_the_plan_fixes_only_its_constants_and_records_c0m_at_locked_1800():
    seen = []
    base = fake_world(good_c0=8, c0m_of=lambda c0: 7.0)

    def f(spec):
        if spec["kind"] == "cB":
            seen.append(spec)
        return base(spec)
    res, ans = run_plan(f)
    d = ans["decisions"]
    assert d["c0m"] == 7.0 and abs(d["c0m_unlocked"] - 0.954 * 7.0) < 1e-9 and d["c0m_basis"].startswith("locked 1800")
    cb = d["c_b"]
    assert cb["pacing"].startswith("auto") and cb["params"]["ki"] == 0.15 and cb["rule_met"] is True          # highest mean tok/s among combinations with mean miss <= 1% and power <= 60 W
    assert len(seen) == 36 and all("pacing" not in sp for sp in seen)


def test_d_b_margin_tuning_is_deferred_to_block_t3b_so_the_sitting_has_no_d_b_cells():
    res, ans = run_plan(fake_world(good_c0=8))
    assert ans["decisions"]["d_b"] == "deferred to block T3b (addendum O-1: d'B action-space fix first)" and not any(k.startswith("db_") for k in res)


def test_resume_returns_only_the_missing_cells():
    fake = fake_world(good_c0=8)
    res = {}
    first = tl.next_batch(res)["batch"]
    res[first[0]["id"]] = fake(first[0])
    again = tl.next_batch(res)["batch"]
    assert first[0]["id"] not in [c["id"] for c in again]


def test_batches_are_shuffled_with_a_fixed_seed_so_a_resumed_plan_repeats_its_order():
    res = {"t1_discard": metrics()}
    a = [c["id"] for c in tl.next_batch(res)["batch"]]
    b = [c["id"] for c in tl.next_batch(res)["batch"]]
    assert a == b


def test_diag_specs_are_five_arms_static_governor_with_reads_governor_without_reads_c_b_with_reads_and_c_b_on_the_sampled_power_source():
    d = tl.diag_specs()
    assert [s["id"] for s in d] == ["diag_static", "diag_gov_static", "diag_gov_static_noenergy", "diag_cb", "diag_cb_sampled"]
    assert d[0]["kind"] == "static" and d[1]["kind"] == "gov_static" and d[2].get("gov_no_energy") is True and d[3]["kind"] == "cB" and d[4]["kind"] == "cB"
    assert d[1].get("power_source") == "energy" and d[3].get("power_source") == "energy" and d[4].get("power_source") == "sampled"
    assert d[0]["setting"] == d[1]["setting"] == d[2]["setting"]


# ---------------------------------------------------------------- block T3b (addendum O-3): d'B margin grid + the c'B constants re-tuned under the final controller, at the chosen c0
def run_t3b(fake, c0=7, results=None, rounds=20):
    results = {} if results is None else results
    for _ in range(rounds):
        ans = tl.next_batch_t3b(results, c0)
        if not ans["batch"]:
            return results, ans
        for spec in ans["batch"]:
            results[spec["id"]] = fake(spec)
    raise AssertionError("T3b did not finish")


def test_t3b_starts_with_one_discarded_cell_then_runs_30_d_b_and_36_c_b_cells():
    ans = tl.next_batch_t3b({}, 7)
    assert [c["id"] for c in ans["batch"]] == ["t3b_discard"] and ans["batch"][0]["discard"] is True
    res, ans = run_t3b(fake_world(good_c0=7))
    assert sum(1 for k in res if k.startswith("db_")) == 30 and sum(1 for k in res if k.startswith("cb2_")) == 36 and len(res) == 67
    assert all(v["c0"] == 7 for k, v in ((s["id"], s) for s in tl.next_batch_t3b({"t3b_discard": metrics()}, 7)["batch"]))


def test_t3b_applies_the_d_b_margin_rule_and_the_c_b_rule_and_flags_when_a_rule_is_not_met():
    res, ans = run_t3b(fake_world(good_c0=7))
    d = ans["decisions"]
    assert d["d_b"]["margin"] == 0.2 and d["d_b"]["rule_met"] is True and d["c_b"]["params"]["ki"] == 0.15 and d["c_b"]["rule_met"] is True and d["c0"] == 7

    def bad(spec):
        r = fake_world(good_c0=7)(spec)
        return metrics(miss=0.05, tok=10.0, power=55.0) if spec["kind"] in ("dB", "cB") else r
    res, ans = run_t3b(bad)
    assert ans["decisions"]["d_b"]["margin"] == 0.4 and ans["decisions"]["d_b"]["rule_met"] is False and ans["decisions"]["c_b"]["rule_met"] is False


def test_t3b_is_resumable_and_deterministic():
    fake = fake_world(good_c0=7)
    res = {"t3b_discard": fake(tl.next_batch_t3b({}, 7)["batch"][0])}
    a = [c["id"] for c in tl.next_batch_t3b(res, 7)["batch"]]
    res[a[0]] = metrics()
    b = [c["id"] for c in tl.next_batch_t3b(res, 7)["batch"]]
    assert a[0] not in b and len(b) == len(a) - 1


# ---------------------------------------------------------------- block T3c (addendum O-6): the c'B grid extended to targets 0.35 and 0.2, rule applied to the FULL grid
def run_t3c(fake, base, c0=7, rounds=20):
    results = dict(base)
    for _ in range(rounds):
        ans = tl.next_batch_t3c(results, c0)
        if not ans["batch"]:
            return results, ans
        for spec in ans["batch"]:
            results[spec["id"]] = fake(spec)
    raise AssertionError("T3c did not finish")


def t3b_base():
    res, _ = run_t3b(fake_world(good_c0=7))
    return {k: v for k, v in res.items() if k.startswith(("cb2_", "db_"))}


def test_t3c_runs_a_discarded_cell_then_24_cells_for_the_new_targets_only():
    base = t3b_base()
    ans = tl.next_batch_t3c(base, 7)
    assert [c["id"] for c in ans["batch"]] == ["t3c_discard"] and ans["batch"][0]["discard"] is True
    res, ans = run_t3c(fake_world(good_c0=7), base)
    new = [k for k in res if k.startswith("cb3_")]
    assert len(new) == 24 and {k.split("_t")[1].split("_k")[0] for k in new} == {"0.35", "0.2"} and len(ans["decisions"]["c_b"]["grid"]) == 10
    assert len([k for k in res if k.startswith("dbh_")]) == 6


def test_t3c_applies_the_unchanged_rule_to_the_full_grid_and_flags_an_edge_winner():
    base = t3b_base()

    def lower_is_safer(spec):                                  # miss falls with the target; nothing reaches 1% -> fallback = lowest mean miss = the new edge 0.2
        if spec["kind"] != "cB":
            return metrics()
        return metrics(miss=0.06 * spec["params"]["target"], tok=30.0 - 20 * spec["params"]["target"], power=45.0)
    res, ans = run_t3c(lower_is_safer, {k: (metrics(miss=0.06 * float(k.split("_t")[1].split("_k")[0]), tok=30.0 - 20 * float(k.split("_t")[1].split("_k")[0]), power=45.0) if k.startswith("cb2_") else v) for k, v in base.items()})
    cb = ans["decisions"]["c_b"]
    assert cb["rule_met"] is False and cb["params"]["target"] == 0.2 and cb["at_grid_edge"] is True

    def knee(spec):                                            # 0.35 meets the SLO, 0.2 also but with fewer tokens: the rule picks the highest tok/s among the compliant ones
        if spec["kind"] != "cB":
            return metrics()
        t = spec["params"]["target"]
        return metrics(miss=0.004 if t <= 0.35 else 0.05, tok=30.0 - 20 * (0.5 - t) ** 2 * 10 if t <= 0.35 else 40.0, power=45.0)
    res2, ans2 = run_t3c(knee, {k: (knee(dict(kind="cB", params=dict(target=float(k.split("_t")[1].split("_k")[0])))) if k.startswith("cb2_") else v) for k, v in base.items()})
    assert ans2["decisions"]["c_b"]["rule_met"] is True and ans2["decisions"]["c_b"]["params"]["target"] == 0.35 and ans2["decisions"]["c_b"]["at_grid_edge"] is False


def test_the_sitting_can_merge_the_cells_of_an_earlier_block_as_read_only_base_results(tmp_path):
    import json
    import tune
    base = t3b_base()

    class Stub:
        name = "stub"
        calls = []

        def run(self, spec, cdir):
            self.calls.append(spec["id"])
            return metrics(miss=0.004, tok=30.0, power=45.0)

        def between_cells(self):
            pass
    ex = Stub()
    s = tune.run_sitting(tmp_path, ex, log=lambda *a: None, planner=lambda r: tl.next_batch_t3c(r, 7), base_results=base)
    assert s["finished"] and len(ex.calls) == 31 and not any(c.startswith(("cb2_", "db_")) for c in ex.calls)
    assert json.loads((tmp_path / "decisions.json").read_text(encoding="utf-8"))["c_b"]["grid"]


def test_t3c_is_governed_so_the_power_source_rules_of_t3b_apply(tmp_path):
    import pytest
    import tune
    o5 = tmp_path / "O5.md"; o5.write_text("x")
    assert tune.resolve_power_source("t3c", "sampled", tmp_path, o5_path=o5) == "sampled"
    with pytest.raises(SystemExit):
        tune.resolve_power_source("t3c", "energy", tmp_path, o5_path=o5)



# ---------------------------------------------------------------- power headroom (addendum O-6 amendment, 2026-10-24): steering target = budget - headroom, headroom from the T3b data only
def headroom_world():
    """d'B cells at every margin; the chosen margin (0.3 in fake_world) has counter powers whose p95 above the steady target 58.2 W is known; the counter reads 0.8 W above the sampled mean."""
    res = {}
    for m in tl.DB_MARGINS:
        for w in WORKLOADS:
            for sc in tl.SCENES:
                miss = 0.03 if m < 0.2 else 0.004
                res[f"db_{w}_{sc}_m{m:g}"] = metrics(miss=miss, tok=30.0, power=58.2 + (1.0 if sc == "S0" else -2.0) + (0.0 if m == 0.2 else 0.0))
    return res


def test_headroom_is_the_p95_of_counter_minus_sampled_plus_the_p95_of_counter_above_the_steady_target_of_the_chosen_margin_cells():
    import numpy as np
    h = tl.headroom_from_results(headroom_world())
    assert abs(h["sensor_p95_w"] - 0.8) < 1e-9 and abs(h["steady_target_w"] - 58.2) < 1e-9 and h["margin"] == 0.2
    # chosen margin 0.2 here (smallest with mean miss <= 1%): its 6 cells are +1.0 (S0 x3) and -2.0 (S1 x3) around 58.2 -> p95 of the deviations
    assert abs(h["spread_p95_w"] - float(np.percentile([1.0, 1.0, 1.0, -2.0, -2.0, -2.0], 95))) < 1e-9
    assert abs(h["w"] - (0.8 + 1.0)) < 1e-9 and "p95" in h["formula"]


def test_headroom_never_goes_negative_and_needs_the_data():
    res = {k: dict(v, power_w=40.0, power_sampled_w=41.0) for k, v in headroom_world().items()}                  # counter below the sampled mean and below the target: no headroom needed
    assert tl.headroom_from_results(res)["w"] == 0.0
    assert tl.headroom_from_results({}) is None


def test_t3c_adds_six_d_b_cells_at_the_chosen_margin_with_the_steering_budget_and_reports_whether_the_rule_still_holds():
    base = dict(t3b_base())
    base.update(headroom_world())
    base = {k: v for k, v in base.items() if k.startswith(("db_", "cb2_"))}
    seen = []

    def fake(spec):
        if spec["id"].startswith("dbh_"):
            seen.append(spec)
            return metrics(miss=0.004, tok=28.0, power=57.0)
        return fake_world(good_c0=7)(spec)
    res, ans = run_t3c(fake, base)
    d = ans["decisions"]
    assert len(seen) == 6 and all(s["params"]["margin"] == 0.2 and abs(s["steer_budget_w"] - (60.0 - d["headroom"]["w"]) / 0.97) < 1e-9 for s in seen)
    assert d["d_b_headroom"]["rule_holds"] is True and abs(d["d_b_headroom"]["mean_miss"] - 0.004) < 1e-9

    def worse(spec):
        return metrics(miss=0.02, tok=20.0, power=55.0) if spec["id"].startswith("dbh_") else fake_world(good_c0=7)(spec)
    res2, ans2 = run_t3c(worse, base)
    assert ans2["decisions"]["d_b_headroom"]["rule_holds"] is False and ans2["decisions"]["headroom"]["w"] == d["headroom"]["w"]          # keep the headroom, report, no further tuning
