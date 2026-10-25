"""Addendum O-7 (decided after T3c, before any evaluation block): the c'B fallback picks the highest-throughput combination within a replicate-noise tolerance d of the lowest mean miss, and the
power headroom is computed from the T3b cells ONLY (the T3c run leaked its own cells into the number: 2.84 W in the dbh cells, 2.64 W in the first freeze, 2.69 W registered)."""
import json
import math
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "experiments" / "w5b"))
sys.path.insert(0, str(ROOT))
import freeze  # noqa: E402
import o7  # noqa: E402
import tune_lib as tl  # noqa: E402

WORKLOADS = ("llama32_1b", "llama32_3b", "phi35_mini")


def m(miss=0.0, tok=20.0, power=50.0, sampled=None, **kw):
    return dict(miss=miss, tok_s=tok, power_w=power, power_sampled_w=power if sampled is None else sampled, power_source="sampled", **kw)


def t3b_world():
    res = {"t3b_discard": m(power=50.0, sampled=49.0)}
    for mg in tl.DB_MARGINS:
        for w in WORKLOADS:
            for sc in tl.SCENES:
                res[f"db_{w}_{sc}_m{mg:g}"] = m(miss=0.03 if mg < 0.2 else 0.004, power=58.2 + (1.0 if sc == "S0" else -2.0), sampled=57.4 + (1.0 if sc == "S0" else -2.0))
    return res


# ---------------------------------------------------------------- headroom from T3b cells only
def test_the_headroom_uses_only_the_t3b_cells_so_t3c_cells_in_the_merged_results_do_not_change_it():
    res = t3b_world()
    h0 = tl.headroom_from_results(res)
    leaked = dict(res)
    leaked["t3c_discard"] = m(power=60.0, sampled=55.0)                                  # the discarded T3c cell read 1.89 W above its sampled mean in the real run
    for w in WORKLOADS:
        for sc in tl.SCENES:
            leaked[f"dbh_{w}_{sc}_m0.2"] = m(power=70.0, sampled=50.0)
            leaked[f"cb3_{w}_{sc}_t0.2_k0.15"] = m(power=70.0, sampled=50.0)
    h1 = tl.headroom_from_results(leaked)
    assert h1["w"] == h0["w"] and h1["n_cells_sensor"] == h0["n_cells_sensor"] == len(res)


# ---------------------------------------------------------------- the tolerance d
def test_d_is_the_p95_of_the_absolute_replicate_miss_differences_scaled_to_a_six_cell_mean():
    pairs = [dict(a=0.0, b=0.0), dict(a=0.0, b=0.0), dict(a=0.02, b=0.0192), dict(a=0.0633, b=0.0658)]
    r = tl.replicate_tolerance(pairs)
    import numpy as np
    p95 = float(np.percentile([0.0, 0.0, abs(0.02 - 0.0192), abs(0.0633 - 0.0658)], 95))
    assert abs(r["p95_abs_diff"] - p95) < 1e-12 and abs(r["d"] - p95 / math.sqrt(6)) < 1e-12 and r["n_pairs"] == 4 and "sqrt(6)" in r["formula"]
    assert tl.replicate_tolerance([])["d"] is None


# ---------------------------------------------------------------- the O-7 fallback
GRID = [dict(params=dict(target=0.2, ki=0.15), miss=0.0308, power_w=24.0, tok_s=0.6), dict(params=dict(target=0.35, ki=0.15), miss=0.0322, power_w=33.0, tok_s=13.6),
        dict(params=dict(target=0.5, ki=0.15), miss=0.0330, power_w=40.0, tok_s=17.3), dict(params=dict(target=0.65, ki=0.15), miss=0.0448, power_w=43.7, tok_s=27.0),
        dict(params=dict(target=0.8, ki=0.05), miss=0.0580, power_w=43.8, tok_s=27.3)]


def test_the_o7_fallback_is_the_fastest_combination_within_d_of_the_lowest_miss():
    assert tl.pick_cb_o7(GRID, 0.0)["params"]["target"] == 0.2                           # d = 0: the registered pick (lowest miss)
    assert tl.pick_cb_o7(GRID, 0.0010)["params"]["target"] == 0.2                        # 0.14 points is outside a 0.10 point tolerance
    assert tl.pick_cb_o7(GRID, 0.0015)["params"]["target"] == 0.35
    assert tl.pick_cb_o7(GRID, 0.0023)["params"]["target"] == 0.5
    assert tl.pick_cb_o7(GRID, 0.0140)["params"]["target"] == 0.65
    assert tl.pick_cb_o7(GRID, 0.0)["miss"] == 0.0308 and tl.pick_cb_o7(GRID, 0.0023)["tok_s"] == 17.3


def test_the_o7_fallback_still_requires_the_power_budget():
    over = [dict(g) for g in GRID]; over[2]["power_w"] = 61.0
    assert tl.pick_cb_o7(over, 0.0023)["params"]["target"] == 0.35                       # 0.5 would be faster but is over 60 W
    assert tl.pick_cb_o7(GRID, 0.0023, budget_w=35.0)["params"]["target"] == 0.35        # at 35 W only combinations up to 35 W qualify


# ---------------------------------------------------------------- replicate pairs from the cell directories
def write_cell(root, name, spec, metrics):
    d = Path(root) / "cells" / name
    d.mkdir(parents=True)
    (d / "cell.json").write_text(json.dumps(dict(id=name, spec=dict(spec, id=name), metrics=metrics, executor="hw")), encoding="utf-8")


def test_pairs_are_cells_with_the_same_spec_and_the_sampled_source_in_different_directories_discards_and_energy_cells_excluded(tmp_path):
    diag, b, c = tmp_path / "diag", tmp_path / "t3b", tmp_path / "t3c"
    cb = dict(kind="cB", workload="llama32_3b", scene="S1", c0=7, params=dict(target=0.5, ki=0.15), budget_w=60.0)
    write_cell(diag, "diag_cb_sampled", cb, m(miss=0.0633))
    write_cell(diag, "diag_cb", cb, dict(m(miss=0.0186), power_source="energy"))                         # energy source: not comparable
    write_cell(b, "cb2_llama32_3b_S1_t0.5_k0.15", cb, m(miss=0.0658))
    db = dict(kind="dB", workload="llama32_3b", scene="S1", c0=7, params=dict(margin=0.3), budget_w=60.0)
    write_cell(b, "db_llama32_3b_S1_m0.3", db, m(miss=0.0200))
    write_cell(c, "dbh_llama32_3b_S1_m0.3", dict(db, steer_budget_w=58.9, headroom_w=2.84), m(miss=0.0192))
    write_cell(b, "t3b_discard", dict(kind="arm_a", workload="llama32_3b", scene="S0", c0=7, discard=True), m(miss=0.5))
    write_cell(c, "t3c_discard", dict(kind="arm_a", workload="llama32_3b", scene="S0", c0=7, discard=True), m(miss=0.0))
    pairs = o7.collect_pairs([diag, b, c])
    kinds = {p["type"] for p in pairs}
    assert len(pairs) == 2 and kinds == {"replicate", "near_replicate_steering_target"}
    rep = next(p for p in pairs if p["type"] == "replicate")
    assert {rep["id_a"], rep["id_b"]} == {"diag_cb_sampled", "cb2_llama32_3b_S1_t0.5_k0.15"} and abs(abs(rep["a"] - rep["b"]) - 0.0025) < 1e-12
    near = next(p for p in pairs if p["type"] != "replicate")
    assert {near["id_a"], near["id_b"]} == {"db_llama32_3b_S1_m0.3", "dbh_llama32_3b_S1_m0.3"}


def test_the_tolerance_file_records_the_pairs_the_number_and_the_formula(tmp_path):
    b, c = tmp_path / "t3b", tmp_path / "t3c"
    for i, (x, y) in enumerate([(0.0, 0.0), (0.02, 0.0192), (0.0633, 0.0658)]):
        spec = dict(kind="cB", workload="llama32_3b", scene="S1", c0=7, params=dict(target=0.5, ki=0.05 + i), budget_w=60.0)
        write_cell(b, f"x{i}", spec, m(miss=x)); write_cell(c, f"y{i}", spec, m(miss=y))
    out = tmp_path / "o7.json"
    r = o7.write_tolerance([b, c], out)
    saved = json.loads(out.read_text(encoding="utf-8"))
    assert saved["n_pairs"] == 3 and saved["d"] == r["d"] and len(saved["pairs"]) == 3 and "sqrt(6)" in saved["formula"]


# ---------------------------------------------------------------- freeze: O-7 primary, registered pick kept, headroom from the T3b cells
def freeze_inputs(tmp_path, rule_met=False):
    tmp_path.mkdir(parents=True, exist_ok=True)
    t =tmp_path / "tuning.json"; t.write_text(json.dumps(dict(c0=7, g_b={"60": dict(setting=dict(sid="1800_a_g0_d1"), feasible_cells=3), "35": None})))
    b = tmp_path / "t3b" / "decisions.json"; b.parent.mkdir()
    b.write_text(json.dumps(dict(d_b=dict(margin=0.2, rule_met=True))))
    for k, v in t3b_world().items():
        write_cell(b.parent, k, dict(kind="dB" if k.startswith("db_") else "arm_a", workload="llama32_3b", scene="S0", c0=7), v)
    c = tmp_path / "t3c" / "decisions.json"; c.parent.mkdir()
    c.write_text(json.dumps(dict(c_b=dict(params=dict(target=0.2, ki=0.15, guard0=0.5, gmin=0.3), rule_met=rule_met, at_grid_edge=True, mean_miss=0.0308, mean_tok_s=0.6, mean_power_w=24.0,
                                         grid=[dict(g) for g in GRID]),
                                 headroom=dict(w=2.84, sensor_p95_w=1.2, spread_p95_w=1.64), d_b_headroom=dict(rule_holds=True, mean_miss=0.0086))))
    write_cell(c.parent, "dbh_llama32_3b_S1_m0.2", dict(kind="dB", workload="llama32_3b", scene="S1", c0=7, params=dict(margin=0.2), steer_budget_w=58.9, headroom_w=2.84), m(miss=0.004))      # what the cells really ran with
    o = tmp_path / "o7.json"; o.write_text(json.dumps(dict(d=0.0023, n_pairs=7, formula="p95/sqrt(6)")))
    return t, b, c, o


def test_freeze_applies_the_o7_fallback_keeps_the_registered_pick_in_the_record_and_recomputes_the_headroom_from_t3b(tmp_path):
    t, b, c, o = freeze_inputs(tmp_path)
    const = freeze.build_constants(t, b, c, tmp_path / "constants.json", o7=o)
    assert const["c_b"]["target"] == 0.5 and const["c_b"]["ki"] == 0.15 and const["c_b_selection"] == "O-7"
    assert const["c_b_registered"]["target"] == 0.2 and const["c_b_registered"]["status"] == "registered pick, sensitivity only, NOT run in the evaluation"
    assert const["o7"]["d"] == 0.0023 and const["rules"]["c_b_rule_met"] is False
    h = tl.headroom_from_results(t3b_world())
    assert abs(const["headroom"]["w"] - h["w"]) < 1e-12 and const["headroom"]["source"].startswith("T3b cells") and abs(const["headroom"]["w"] - 2.84) > 0.1
    assert const["rules"]["d_b_headroom_ran_with_w"] == 2.84                                # the confirmation cells' own spec, not the decisions file's merged-set number


def test_freeze_with_a_met_rule_keeps_the_registered_pick_and_without_the_o7_file_it_refuses(tmp_path):
    t, b, c, o = freeze_inputs(tmp_path, rule_met=True)
    const = freeze.build_constants(t, b, c, tmp_path / "constants.json", o7=o)
    assert const["c_b"]["target"] == 0.2 and const["c_b_selection"] == "registered (rule met)"
    freeze.build_constants(t, b, c, tmp_path / "x.json")                                  # a met rule needs no tolerance file
    t2, b2, c2, _ = freeze_inputs(tmp_path / "unmet", rule_met=False)
    with pytest.raises(SystemExit):
        freeze.build_constants(t2, b2, c2, tmp_path / "y.json")                           # an unmet rule without the O-7 tolerance file is refused


def test_the_session_meta_names_addendum_o7():
    assert "O-5, O-6, O-7" in (ROOT / "experiments" / "w5b" / "evaluate.py").read_text(encoding="utf-8")
