"""analysis/w5_analysis.py: the registered W5b tests of experiments/w5_governor.yaml (HW1 constraints, HW2 superiority in S5 + non-inferiority in S0/S2 + HW1 for d'B, HW3 learned vs simple,
HW7 staleness of the clean-token estimate). Specified BEFORE any W5 data by the yaml (committed 2026-10-23) and written test-first on synthetic fixtures.
Cell table columns: block, scene, controller, budget_w, bg_tok_s, miss_frac, power_w. SCORE = bg_tok_s if feasible (miss_frac <= 0.01 and power_w <= budget_w) else 0 (infeasible cells are NOT dropped).
Instruction (Arjun, 2026-10-23): "write analysis/w5_analysis.py test-first"."""
import numpy as np
import pandas as pd

from analysis.w5_analysis import (NI_MARGIN, bootstrap_ci_median, cell_scores, earns_place, hw1_table, hw2_report, hw7_staleness, holm, ratio_blocks,
                                  wilcoxon_greater_exact)

CTRL = ("g'B", "eB", "c'B", "d'B")
SCENES = ("S0", "S1", "S1d", "S2", "S5")


def table(tok, blocks=range(10)):
    """tok: dict (scene, controller) -> number or function(block)->tok/s. Every cell is feasible (miss 0, 50 W) unless the test edits the frame."""
    rows = []
    for b in blocks:
        for s in SCENES:
            for c in CTRL:
                v = tok[(s, c)]
                rows.append(dict(block=b, scene=s, controller=c, budget_w=60.0, bg_tok_s=v(b) if callable(v) else v, miss_frac=0.0, power_w=50.0))
    return pd.DataFrame(rows)


def jitter(v, amp=0.5):
    return lambda b: v + amp * ((b * 7919) % 10 - 4.5) / 4.5


def good_tok():
    """d'B wins S5 clearly, is equal elsewhere (non-inferior); every cell has a small block-dependent jitter."""
    t = {(s, c): jitter(30.0, 0.4) for s in SCENES for c in CTRL}
    t[("S5", "d'B")] = jitter(40.0)
    t[("S5", "c'B")] = jitter(25.0, 0.4)
    return t


def test_score_is_zero_when_the_slo_or_the_budget_is_broken():
    df = pd.DataFrame([dict(block=0, scene="S1", controller="x", budget_w=60.0, bg_tok_s=30.0, miss_frac=0.02, power_w=50.0),
                       dict(block=0, scene="S1", controller="y", budget_w=60.0, bg_tok_s=30.0, miss_frac=0.0, power_w=61.0),
                       dict(block=0, scene="S1", controller="z", budget_w=60.0, bg_tok_s=30.0, miss_frac=0.01, power_w=60.0)])
    assert cell_scores(df).tolist() == [0.0, 0.0, 30.0]


def test_exact_wilcoxon_floor_is_1_over_2_to_the_n_and_ties_drop_out():
    p, n = wilcoxon_greater_exact(np.arange(1, 11, dtype=float) + 1.0, np.zeros(10))
    assert n == 10 and abs(p - 1 / 1024) < 1e-12
    p2, n2 = wilcoxon_greater_exact(np.array([0.0, 0.0, 5, 6, 7, 8, 9, 10.0, 11, 12]), np.zeros(10))
    assert n2 == 8 and abs(p2 - 1 / 256) < 1e-12                       # two (0, 0) ties dropped
    p3, n3 = wilcoxon_greater_exact(np.ones(6), np.zeros(6))
    assert n3 == 6 and abs(p3 - 1 / 64) < 1e-12
    p4, _ = wilcoxon_greater_exact(np.zeros(5), np.ones(5))
    assert p4 > 0.9                                                      # all negative: no evidence for 'greater'


def test_wilcoxon_with_tied_magnitudes_uses_average_ranks_and_the_exact_sign_distribution():
    p, n = wilcoxon_greater_exact(np.array([1.0, 1.0, 1.0, -1.0]), np.zeros(4))
    # ranks 2.5 each; W+ = 7.5 of 10; P(W+ >= 7.5) over 16 sign patterns = patterns with >= 3 positives = (4 + 1) / 16
    assert n == 4 and abs(p - 5 / 16) < 1e-12


def test_holm_step_down():
    assert holm([0.001, 0.03, 0.5], alpha=0.05) == [True, False, False]        # 0.001 < 0.05/3; 0.03 > 0.05/2 = 0.025
    assert holm([0.01, 0.015, 0.02], alpha=0.05) == [True, True, True]


def test_bootstrap_ci_is_reproducible_and_brackets_the_median():
    d = np.arange(10, dtype=float)
    a, b = bootstrap_ci_median(d, seed=1), bootstrap_ci_median(d, seed=1)
    assert a == b and a[0] <= np.median(d) <= a[1]


def test_ratio_blocks_rules_for_zero_scores():
    r, n_excluded = ratio_blocks(np.array([0.0, 10.0, 8.0, 0.0]), np.array([5.0, 0.0, 10.0, 0.0]))
    assert r.tolist() == [0.0, 0.8] and n_excluded == 2        # d'B 0 vs comparator 5 -> ratio 0; comparator 0 -> excluded


def test_hw1_requires_90_percent_feasible_and_mean_miss_at_most_1_percent():
    df = table(good_tok())
    assert bool(hw1_table(df, 60.0).loc[("S1", "d'B"), "holds"])
    bad = df.block.isin([0, 1]) & (df.scene == "S1") & (df.controller == "d'B")           # 2 of 10 cells infeasible = 80% < 90%
    df.loc[bad, "miss_frac"] = 0.05
    assert not bool(hw1_table(df, 60.0).loc[("S1", "d'B"), "holds"])


def test_earns_its_place_when_it_wins_s5_is_non_inferior_and_holds_hw1():
    rep = hw2_report(table(good_tok()), budget=60.0, seed=0)
    assert all(rep["s5"][c]["reject"] for c in ("c'B", "g'B", "eB"))
    assert all(v["pass"] for sc in rep["ni"].values() for v in sc.values())
    assert earns_place(rep)


def test_no_place_if_inferior_in_s2_or_hw1_fails_or_there_is_no_s5_win():
    t = good_tok()
    t[("S2", "d'B")] = jitter(20.0)                                       # 20 / 30 = 0.67 < 0.95
    assert not earns_place(hw2_report(table(t), budget=60.0, seed=0))
    df = table(good_tok())
    df.loc[(df.scene == "S1") & (df.controller == "d'B") & (df.block < 3), "miss_frac"] = 0.05           # 70% feasible in S1: HW1 fails
    assert not earns_place(hw2_report(df, budget=60.0, seed=0))
    t = good_tok()
    t[("S5", "d'B")] = jitter(30.0, 0.4)
    assert not earns_place(hw2_report(table(t), budget=60.0, seed=0))


def test_infeasible_cells_count_as_zero_not_dropped():
    df = table(good_tok())
    bad = (df.scene == "S5") & (df.controller == "d'B") & (df.block < 6)                      # d'B breaks the SLO in 6 of 10 S5 blocks, better in the other four
    df.loc[bad, "miss_frac"] = 0.2
    rep = hw2_report(df, budget=60.0, seed=0)
    assert not rep["s5"]["c'B"]["reject"] and not earns_place(rep)


def test_fewer_than_six_non_tied_blocks_is_inconclusive():
    df = table(good_tok())
    both_zero = (df.scene == "S5") & df.controller.isin(["d'B", "c'B"]) & (df.block < 6)
    df.loc[both_zero, "miss_frac"] = 0.2                                  # 6 blocks tie at (0, 0): 4 non-tied blocks left
    rep = hw2_report(df, budget=60.0, seed=0)
    assert rep["s5"]["c'B"]["n_nontied"] == 4 and rep["s5"]["c'B"]["inconclusive"] and not rep["s5"]["c'B"]["reject"]


def test_ni_margin_value():
    assert NI_MARGIN == 0.95


def test_hw7_staleness_error_and_unrecovered_changes():
    t = np.arange(0, 10, 0.02)                                            # one token every 20 ms; the true clean time goes 10 -> 14 ms at the clock change t = 2 s
    tok = np.where(t < 2.0, 10.0, 14.0)
    est = np.array([np.median(tok[max(0, i - 8):i]) if i > 0 else tok[0] for i in range(len(t))])           # a median of the last 8 clean tokens
    tokens = pd.DataFrame(dict(t_start=t, tok_ms=tok, overlapped=0, est_clean_ms=est))
    r = hw7_staleness(tokens, clock_changes=[2.0])
    assert r.loc[0, "n_clean_window"] >= 8 and r.loc[0, "error"] < 0.01 and not r.loc[0, "unrecovered"]
    sparse = tokens[(tokens.t_start < 2.5) | (tokens.t_start > 3.2)].copy()              # almost no tokens in [3, 3.2]: the window holds fewer than 8 clean tokens
    sparse.loc[sparse.t_start > 3.2, "overlapped"] = 1
    r2 = hw7_staleness(sparse, clock_changes=[2.0])
    assert bool(r2.loc[0, "unrecovered"])
