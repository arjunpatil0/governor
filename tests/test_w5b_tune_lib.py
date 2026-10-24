"""W5b tuning blocks T1-T3: the pure plan / decision logic (experiments/w5b/tune_lib.py), exactly as stated in plan addendum O section 4 (docs/W5B_ADDENDUM_O.md, committed before any W5b data):
c0 search 7..11 with the arm-a > 5% precondition, the 70-static sweep, HW0 at 60 W, stage-2 top 8 per budget, g'B per budget, c'B constants grid, d'B margin rule, the fixed c'B pacing mode.
Instruction (Arjun, 2026-10-23): "give me the T1-T3 session commands, set up to run unattended overnight (fresh-restart check, helper start, chained blocks)"."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "experiments" / "w5b"))
import tune_lib as tl  # noqa: E402

WORKLOADS = ("llama32_1b", "llama32_3b", "phi35_mini")


def metrics(miss=0.0, tok=30.0, power=40.0, c0m=None):
    return dict(miss=miss, tok_s=tok, power_w=power, c0m=c0m)


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


def test_diag_specs_are_a_static_reference_the_same_action_through_the_governor_with_and_without_energy_reads_and_c_b():
    d = tl.diag_specs()
    assert [s["id"] for s in d] == ["diag_static", "diag_gov_static", "diag_gov_static_noenergy", "diag_cb"]
    assert d[0]["kind"] == "static" and d[1]["kind"] == "gov_static" and d[2]["kind"] == "gov_static" and d[2].get("gov_no_energy") is True and d[3]["kind"] == "cB"
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
