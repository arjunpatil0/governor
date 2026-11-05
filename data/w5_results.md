# W5b confirmatory analysis (analysis/w5_analysis.py on results.csv); registered in experiments/w5_governor.yaml

## Budget 35 W (EXPLORATORY)

### HW1 per controller and scene
                  n  frac_feasible  mean_miss  holds
scene controller                                    
S0    c'B-T3b     5            0.0      0.004  False
      c'B-T3c     5            0.0      0.018  False
      d'B         5            0.0      0.042  False
      eB          5            1.0      0.000   True
      g'B         5            1.0      0.000   True
S1    c'B-T3b     5            0.0      0.028  False
      c'B-T3c     5            0.0      0.057  False
      d'B         5            0.0      0.023  False
      eB          5            0.8      0.000  False
      g'B         5            1.0      0.000   True
S1d   c'B-T3b     5            0.4      0.014  False
      c'B-T3c     5            0.0      0.021  False
      d'B         5            0.0      0.025  False
      eB          5            1.0      0.000   True
      g'B         5            1.0      0.000   True
S2    c'B-T3b     5            0.0      0.018  False
      c'B-T3c     5            0.0      0.018  False
      d'B         5            0.0      0.045  False
      eB          5            0.2      0.000  False
      g'B         5            0.2      0.000  False
S5    c'B-T3b     5            0.0      0.124  False
      c'B-T3c     5            0.0      0.064  False
      d'B         5            0.0      0.058  False
      eB          5            1.0      0.000   True
      g'B         5            1.0      0.000   True

## Budget 60 W (PRIMARY)

### HW1 per controller and scene
                   n  frac_feasible  mean_miss  holds
scene controller                                     
S0    a           10            0.0      0.000  False
      c'B-T3b     10            0.8      0.004  False
      c'B-T3c     10            0.0      0.018  False
      d'B         10            1.0      0.000   True
      eB          10            1.0      0.000   True
      g'B         10            1.0      0.000   True
S1    a           10            0.0      0.341  False
      c'B-T3b     10            0.0      0.056  False
      c'B-T3c     10            0.0      0.056  False
      d'B         10            0.0      0.017  False
      eB          10            1.0      0.000   True
      g'B         10            1.0      0.000   True
S1d   a           10            0.0      0.054  False
      c'B-T3b     10            0.0      0.026  False
      c'B-T3c     10            0.0      0.020  False
      d'B         10            1.0      0.003   True
      eB          10            1.0      0.000   True
      g'B         10            1.0      0.000   True
S2    a           10            0.0      0.000  False
      c'B-T3b     10            0.0      0.019  False
      c'B-T3c     10            0.0      0.018  False
      d'B         10            1.0      0.000   True
      eB          10            1.0      0.000   True
      g'B         10            1.0      0.000   True
S5    a           10            0.0      0.347  False
      c'B-T3b     10            0.0      0.116  False
      c'B-T3c     10            0.0      0.065  False
      d'B         10            0.0      0.047  False
      eB          10            1.0      0.000   True
      g'B         10            1.0      0.000   True

### HW2 (score = tok/s if feasible else 0; paired by block)

S5 superiority of d'B vs c'B-T3b (PRIMARY), g'B, eB (exact Wilcoxon, Holm over 3, 90% bootstrap CI of the median difference):
- vs c'B-T3b: median diff 0.00 tok/s, 90% CI [0.00, 0.00], p 1.00000, non-tied blocks 0, INCONCLUSIVE, Holm-reject False, REJECT False
- vs g'B: median diff 0.00 tok/s, 90% CI [0.00, 0.00], p 1.00000, non-tied blocks 0, INCONCLUSIVE, Holm-reject False, REJECT False
- vs eB: median diff 0.00 tok/s, 90% CI [0.00, 0.00], p 1.00000, non-tied blocks 0, INCONCLUSIVE, Holm-reject False, REJECT False

Non-inferiority (ratio d'B / comparator, 90% CI lower bound >= 0.95; PRIMARY c'B comparator = c'B-T3b):
- S0 vs c'B-T3b: median ratio 0.973, CI [0.943, 0.980], blocks used 8, excluded (comparator 0) 2, pass False
- S0 vs g'B: median ratio nan, CI [nan, nan], blocks used 0, excluded (comparator 0) 10, pass True VACUOUS (comparator scored 0 in every block)
- S0 vs eB: median ratio nan, CI [nan, nan], blocks used 0, excluded (comparator 0) 10, pass True VACUOUS (comparator scored 0 in every block)
- S2 vs c'B-T3b: median ratio nan, CI [nan, nan], blocks used 0, excluded (comparator 0) 10, pass True VACUOUS (comparator scored 0 in every block)
- S2 vs g'B: median ratio 1.289, CI [1.282, 1.310], blocks used 10, excluded (comparator 0) 0, pass True
- S2 vs eB: median ratio 1.310, CI [1.304, 1.336], blocks used 10, excluded (comparator 0) 0, pass True

### SECONDARY comparator c'B-T3c (not part of the registered reading; reported for the paper)

- S5 d'B vs c'B-T3c: median diff 0.00 tok/s, 90% CI [0.00, 0.00], p 1.00000, non-tied blocks 0, INCONCLUSIVE, REJECT False
- S0 vs c'B-T3c: median ratio nan, CI [nan, nan], blocks used 0, excluded (comparator 0) 10, pass True VACUOUS (comparator scored 0 in every block)
- S2 vs c'B-T3c: median ratio nan, CI [nan, nan], blocks used 0, excluded (comparator 0) 10, pass True VACUOUS (comparator scored 0 in every block)

HW1 for d'B in every primary scene: S0 True, S1 False, S1d True, S2 True, S5 False

**d'B DOES NOT EARN ITS PLACE** under the registered reading (S5 win against all three, non-inferiority in S0 and S2 against all three, HW1 in every primary scene).

### HW3 (d'B vs g'B and eB; Holm over the 5 scenes)

d'B vs g'B: S0 diff 17.52 [17.22, 17.83] reject True; S1 diff -19.97 [-19.98, -19.94] reject False; S1d diff 1.58 [0.47, 2.68] reject True; S2 diff 9.25 [9.02, 9.98] reject True; S5 diff 0.00 [0.00, 0.00] reject False

d'B vs eB: S0 diff 17.52 [17.22, 17.83] reject True; S1 diff -19.97 [-19.97, -19.95] reject False; S1d diff 0.91 [0.42, 1.88] reject True; S2 diff 9.70 [9.60, 10.54] reject True; S5 diff 0.00 [0.00, 0.00] reject False
