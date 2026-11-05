# W5b evaluation results (2026-11-06)
Registered analysis (analysis/w5_analysis.py, pre-registered in experiments/w5_governor.yaml and addenda O-4..O-7) run once on data/w5b/eval/results.csv: 10 blocks (4 5 8 9 10 11 12 13 14 15), 425 cells, constants sha256 f7b99650efe7fea9d392a1aee2e49a18a84a00fe69d56fb4e41bf562cc6fb4a9, integrity PASS (0 problems; flags: discarded blocks 6 and 7, kept, not counted). Full registered output: data/w5_results.md (verbatim). Descriptive tables (POST HOC): data/w5b/eval_descriptive.md (analysis/w5b_descriptive.py). Nothing was re-run, re-selected or re-scored after seeing a result.

## Registered verdicts, as computed
**d'B DOES NOT EARN ITS PLACE** under the registered reading. Which conditions fail:

| condition (registered) | result |
|---|---|
| HW1 for d'B, 60 W, per primary scene | S0 True, **S1 False** (0/10 feasible, median miss 1.72%), S1d True, S2 True, **S5 False** (0/10 feasible, median miss 4.72%) |
| S5 superiority vs c'B-T3b / g'B / eB (Holm over 3) | all three INCONCLUSIVE, REJECT False: every block ties at score 0 (non-tied blocks 0). d'B scores 0 because it misses the 1% limit in S5; g'B and eB score 0 because they make 0 background tokens in the window; c'B-T3b is infeasible in S5 |
| non-inferiority 0.95, S0 vs c'B-T3b (PRIMARY) | median ratio 0.973, 90% CI [0.943, 0.980], 8 blocks used (2 excluded: c'B-T3b infeasible there), **FAIL** (lower bound 0.943 < 0.95) |
| non-inferiority, S0 vs g'B, eB | pass, VACUOUS (comparators score 0 in all 10 blocks) |
| non-inferiority, S2 vs c'B-T3b | pass, VACUOUS (c'B-T3b infeasible in all 10 S2 blocks: median miss 1.88%) |
| non-inferiority, S2 vs g'B / eB | pass: ratio 1.289 [1.282, 1.310] / 1.310 [1.304, 1.336] |

d'B power was within 60 W in every 60 W cell (10/10 in each scene).

## SECONDARY comparator c'B-T3c (not part of the registered reading)
S5 d'B vs c'B-T3c: INCONCLUSIVE (all blocks tie at 0), REJECT False. Non-inferiority S0 and S2: pass, VACUOUS (c'B-T3c is infeasible in every cell of every scene at 60 W; median miss 1.8-6.5% by scene).

## HW3 (d'B vs g'B and eB, Holm over 5 scenes, as computed)
vs g'B: S0 +17.52 tok/s [17.22, 17.83] reject; S1 -19.97 [-19.98, -19.94] no; S1d +1.58 [0.47, 2.68] reject; S2 +9.25 [9.02, 9.98] reject; S5 0.00 no.
vs eB: S0 +17.52 [17.22, 17.83] reject; S1 -19.97 [-19.97, -19.95] no; S1d +0.91 [0.42, 1.88] reject; S2 +9.70 [9.60, 10.54] reject; S5 0.00 no.
(The S0 and S5 differences are against a static baseline that produced 0 tokens in the window: see observation 1.)

## Exploratory 35 W family (HW1 only, as registered; 5 blocks)
HW1 holds only for g'B (S0, S1, S1d, S5) and eB (S0, S1d, S5); it fails for c'B-T3b, c'B-T3c and d'B in every scene. d'B was feasible in 0 of 25 cells at 35 W (S1: median counter power 37.7 W, above the budget; the controller limit explained in journal 0060). Not tested beyond HW1.

## Final pacing mode per cell
Exported per cell in results.csv (column final_pacing_mode); counts per scene and controller in data/w5b/eval_descriptive.md. d'B ended in "unaligned" in all 75 of its cells (50 at 60 W, 25 at 35 W): no mode flip, no bimodality observed (cf. journal 0059). g'B and eB: aligned in all cells. c'B-T3b: aligned in 9 of 10 S0 cells at 60 W (unaligned in 1), unaligned in every other scene; c'B-T3c: unaligned everywhere; arm a: unaligned.

## Observations, POST HOC (descriptive, none registered)
1. **g'B and eB make 0 background tokens in the window in S0 and S5** (all 40 cells at 60 W: 2 controllers x 2 scenes x 10 blocks; 5-16 tokens in the whole run, all outside the window). Static aligned setting 1800_a_g0_d1; the mechanism is not analysed here. Known for the 3B in S0 from tuning (journal 0053: "at c0 = 7 aligned statics give 0 tok/s for the 3B and Phi in S0"). The registered scoring counts these cells as feasible (HW1 True) with score 0, so the S0 and S5 comparisons against g'B and eB are comparisons against a baseline that does no background work.
2. **d'B in S1 and S5 misses the SLO in every block** (S1 median 1.72% miss, 18.4-20.9 tok/s; S5 4.72%, 7.3-8.1 tok/s). The tuning-data d'B figure, 0.86% miss at 30.5 tok/s (PAPER_MAP row 30, measured on the cells that selected the constants), was not reproduced in the evaluation S1 cells; the cause is not investigated here.
3. Where d'B does hold HW1 (median tok/s): S2 41.3 vs 32.0 (g'B) and 31.4 (eB); S1d 17.9 vs 16.6 and 16.7; S0 17.5 vs 0.
4. c'B-T3b (median over the cells of a scene): S0 feasible in 8/10 (18.1 tok/s, 58.4 W); infeasible in every S1, S1d, S2 and S5 cell (median miss 6.3, 2.5, 1.9, 11.1%). c'B-T3c: 0.3-0.8 tok/s except S2 (28.3 tok/s), infeasible everywhere.
5. Arm a (unaligned, no governor): 87-92 W counter power in every scene, feasible in no cell at 60 W.

## Limits
- 10 paired blocks per 60 W cell, 5 per 35 W cell. The exact one-sided Wilcoxon with Holm over 3 needs at least 6 non-tied blocks (registered MIN_NONTIED), so a scene in which every block ties at 0 cannot reject by construction.
- The d'B confirmation of the tuning ran at headroom 2.84 W; the registered 2.692 W was used in the evaluation (journal 0059).
- Feasibility uses the energy counter; the governed loops steer on the sampled power source (addenda O-4, O-5).
- No result in this file was used to change code, constants or the registered reading.
