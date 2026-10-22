# W4-5 simulator follow-ups (POST-HOC / SENSITIVITY; the frozen results in data/w45_sim_results.md are unchanged)

Held-out evaluation seeds 200-229, each configuration evaluated once. Controllers c, c', d, d' and the per-scenario statics b, b' keep their FROZEN constants (tuned without jitter); the scenario-agnostic statics g, g' and e were chosen on the tuning seeds 100-109 (data/sim_tuned_followup.json), under the jittered plant for the jitter evaluation. bj' = per-scenario aligned static re-tuned under jitter. Token jitter: inter-token intervals from the L per-token logs / cell median, pooled, mean 1. SIMULATION ONLY.

## Chosen settings (tuning seeds)

```
{
 "global_nojit": {
  "g": {
   "action": {
    "clock": 2460.0,
    "pacing": "unaligned",
    "duty": 0.05,
    "guard_ms": 0.5
   },
   "tok_s": 3.483333333333333,
   "power_w": 29.1968215421761,
   "miss_max_seen": 0.013636363636363636,
   "feasible": false
  },
  "g'": {
   "action": {
    "clock": 2460.0,
    "pacing": "aligned",
    "duty": 1.0,
    "guard_ms": 0.0
   },
   "tok_s": 54.92636363636365,
   "power_w": 73.16811832788328,
   "miss_max_seen": 0.0,
   "feasible": true
  }
 },
 "global_jit": {
  "g": {
   "action": {
    "clock": 2460.0,
    "pacing": "unaligned",
    "duty": 0.05,
    "guard_ms": 0.5
   },
   "tok_s": 3.4615151515151514,
   "power_w": 29.18240579149921,
   "miss_max_seen": 0.011212121212121211,
   "feasible": false
  },
  "g'": {
   "action": {
    "clock": 2460.0,
    "pacing": "aligned",
    "duty": 1.0,
    "guard_ms": 0.0
   },
   "tok_s": 54.592121212121214,
   "power_w": 72.89319422939457,
   "miss_max_seen": 0.0,
   "feasible": true
  }
 }
}
```

Per-scenario aligned static re-tuned under jitter (bj'):

```
{
 "S0": {
  "b'": {
   "clock": 2460.0,
   "pacing": "aligned",
   "duty": 1.0,
   "guard_ms": 0.0
  },
  "_meta": {
   "tok_s": 59.980000000000004,
   "power_w": 79.61958587824707,
   "miss_max_seen": 0.0,
   "feasible": true
  }
 },
 "S1": {
  "b'": {
   "clock": 2460.0,
   "pacing": "aligned",
   "duty": 1.0,
   "guard_ms": 0.0
  },
  "_meta": {
   "tok_s": 53.09818181818181,
   "power_w": 73.72994094838562,
   "miss_max_seen": 0.0,
   "feasible": true
  }
 },
 "S1d": {
  "b'": {
   "clock": 2460.0,
   "pacing": "aligned",
   "duty": 1.0,
   "guard_ms": 0.0
  },
  "_meta": {
   "tok_s": 59.04545454545455,
   "power_w": 79.40004289746233,
   "miss_max_seen": 0.0,
   "feasible": true
  }
 },
 "S2": {
  "b'": {
   "clock": 2460.0,
   "pacing": "aligned",
   "duty": 1.0,
   "guard_ms": 0.0
  },
  "_meta": {
   "tok_s": 74.93090909090908,
   "power_w": 84.1093609262112,
   "miss_max_seen": 0.0,
   "feasible": true
  }
 },
 "S3": {
  "b'": {
   "clock": 2460.0,
   "pacing": "aligned",
   "duty": 1.0,
   "guard_ms": 0.0
  },
  "_meta": {
   "tok_s": 27.25818181818182,
   "power_w": 46.66481969607992,
   "miss_max_seen": 0.0,
   "feasible": true
  }
 },
 "S4": {
  "b'": {
   "clock": 2460.0,
   "pacing": "aligned",
   "duty": 1.0,
   "guard_ms": 0.0
  },
  "_meta": {
   "tok_s": 53.239999999999995,
   "power_w": 73.83541502998128,
   "miss_max_seen": 0.0,
   "feasible": true
  }
 }
}
```

## plant as frozen (no token jitter)

### SLO: mean miss fraction (top) and holds_slo (bottom)
```
controller       a       b   b'       c   c'       d   d'       g   g'    e
scenario                                                                   
S0          0.0000  0.0000  0.0  0.0000  0.0  0.0000  0.0  0.0000  0.0  0.0
S1          0.3383  0.0072  0.0  0.0056  0.0  0.0031  0.0  0.0019  0.0  0.0
S1d         0.0379  0.0042  0.0  0.0006  0.0  0.0003  0.0  0.0003  0.0  0.0
S2          0.0000  0.0000  0.0  0.0012  0.0  0.0008  0.0  0.0000  0.0  0.0
S3          0.5455  0.0120  0.0  0.0085  0.0  0.0047  0.0  0.0120  0.0  0.0
S4          0.0000  0.0000  0.0  0.0076  0.0  0.0000  0.0  0.0000  0.0  0.0
```
```
         a      b    b'     c    c'     d    d'      g    g'     e
S0    True   True  True  True  True  True  True   True  True  True
S1   False   True  True  True  True  True  True   True  True  True
S1d  False   True  True  True  True  True  True   True  True  True
S2    True   True  True  True  True  True  True   True  True  True
S3   False  False  True  True  True  True  True  False  True  True
S4    True   True  True  True  True  True  True   True  True  True
```

### Pareto headline (median tok/s, median power W; controllers that hold the SLO; `*` = on the Pareto front; objective = tok/s - 0.5 W is ONE marked point)

#### S0  (lambda = 0.5 best: b'*)
```
            tok_s  power_w  objective_lam0p5  j_per_token
controller                                               
b           60.00    79.81             20.10         1.33
b'*         60.00    79.63             20.19         1.33
c'*         60.00    79.63             20.19         1.33
d'*         60.00    79.63             20.19         1.33
g'*         60.00    79.63             20.19         1.33
e*          60.00    79.63             20.19         1.33
a           54.49    87.33             10.82         1.60
d*          10.66    38.45             -8.56         3.61
c*           6.91    34.82            -10.50         5.04
g*           3.45    31.42            -12.26         9.10
```

#### S1  (lambda = 0.5 best: b'*)
```
            tok_s  power_w  objective_lam0p5  j_per_token
controller                                               
b'*         53.85    74.36             16.68         1.38
g'*         53.85    74.36             16.68         1.38
e*          53.85    74.36             16.68         1.38
d'*         34.21    48.59              9.92         1.42
d           29.51    55.52              1.75         1.88
c'*         28.25    45.23              5.63         1.60
b*          15.58    42.67             -5.75         2.74
c*           5.24    30.28             -9.91         5.79
g            3.45    31.43            -12.27         9.12
```

#### S1d  (lambda = 0.5 best: b'*)
```
            tok_s  power_w  objective_lam0p5  j_per_token
controller                                               
b'*         59.31    79.60             19.51         1.34
g'*         59.31    79.60             19.51         1.34
e*          59.31    79.60             19.51         1.34
b           56.88    81.24             16.26         1.43
c'*         51.05    70.07             16.02         1.37
d*          44.29    69.03              9.78         1.56
d'*         43.95    61.48             13.21         1.40
c*           5.75    32.61            -10.56         5.68
g*           3.42    31.98            -12.57         9.35
```

#### S2  (lambda = 0.5 best: e*)
```
            tok_s  power_w  objective_lam0p5  j_per_token
controller                                               
b'*         74.95    84.12             32.89         1.12
g'*         74.95    84.12             32.89         1.12
e*          73.18    71.88             37.24         0.98
d'*         72.51    71.30             36.86         0.98
c'*         72.09    70.78             36.70         0.98
a           71.45    89.02             26.94         1.25
b           70.53    85.77             27.64         1.22
d*          40.46    44.51             18.21         1.10
c*          37.82    41.81             16.91         1.11
g*           4.02    23.39             -7.68         5.82
```

#### S3  (lambda = 0.5 best: b'*)
```
            tok_s  power_w  objective_lam0p5  j_per_token
controller                                               
b'*         27.27    46.67              3.94         1.71
c'          27.27    46.67              3.94         1.71
d'*         27.27    46.67              3.94         1.71
g'*         27.27    46.67              3.94         1.71
e*          27.27    46.67              3.94         1.71
d*           5.49    28.36             -8.69         5.17
c*           4.29    27.08             -9.25         6.31
```

#### S4  (lambda = 0.5 best: a*)
```
            tok_s  power_w  objective_lam0p5  j_per_token
controller                                               
a*          64.91    87.96             20.93         1.36
b*          64.91    87.96             20.93         1.36
b'*         53.85    74.36             16.68         1.38
g'*         53.85    74.36             16.68         1.38
e*          53.85    74.36             16.68         1.38
d*          38.60    62.55              7.33         1.62
d'*         34.21    48.59              9.92         1.42
c'*         28.25    45.23              5.63         1.60
c*           6.11    30.75             -9.27         5.03
g            3.69    31.36            -11.99         8.50
```

### Paired comparisons on the objective, tok/s and power (median of A - B over seeds where both meet the SLO; 90% bootstrap CI)

#### d' minus c'   (PRIMARY learned-vs-feedback comparison)
```
                     n  median     lo     hi
scenario metric                             
S0       objective  30   0.000  0.000  0.000
         bg_tok_s   30   0.000  0.000  0.000
         power_w    30   0.000  0.000  0.000
S1       objective  30   4.282  4.206  4.329
         bg_tok_s   30   5.973  5.818  6.018
         power_w    30   3.376  3.252  3.429
S1d      objective  30  -2.886 -3.033 -2.710
         bg_tok_s   30  -7.309 -7.465 -6.964
         power_w    30  -8.550 -8.839 -8.148
S2       objective  30   0.158  0.148  0.159
         bg_tok_s   30   0.418  0.400  0.418
         power_w    30   0.520  0.505  0.522
S3       objective  30   0.000  0.000  0.000
         bg_tok_s   30   0.000  0.000  0.000
         power_w    30  -0.000 -0.000  0.000
S4       objective  30   4.282  4.206  4.329
         bg_tok_s   30   5.973  5.827  6.018
         power_w    30   3.376  3.252  3.438
```

#### c' minus g'
```
                     n  median      lo      hi
scenario metric                               
S0       objective  30   0.000   0.000   0.000
         bg_tok_s   30   0.000   0.000   0.000
         power_w    30   0.000   0.000   0.000
S1       objective  30 -11.111 -11.206 -11.021
         bg_tok_s   30 -25.727 -25.891 -25.600
         power_w    30 -29.232 -29.366 -29.138
S1d      objective  30  -3.535  -3.578  -3.457
         bg_tok_s   30  -8.218  -8.309  -8.082
         power_w    30  -9.585  -9.722  -9.400
S2       objective  30   3.814   3.814   3.815
         bg_tok_s   30  -2.855  -2.855  -2.855
         power_w    30 -13.338 -13.338 -13.338
S3       objective  30  -0.000  -0.000   0.000
         bg_tok_s   30   0.000   0.000   0.000
         power_w    30   0.000   0.000   0.000
S4       objective  30 -11.111 -11.204 -11.026
         bg_tok_s   30 -25.727 -25.891 -25.600
         power_w    30 -29.232 -29.379 -29.140
```

#### d' minus g'
```
                     n  median      lo      hi
scenario metric                               
S0       objective  30   0.000   0.000   0.000
         bg_tok_s   30   0.000   0.000   0.000
         power_w    30   0.000   0.000   0.000
S1       objective  30  -6.831  -6.913  -6.740
         bg_tok_s   30 -19.764 -19.919 -19.618
         power_w    30 -25.848 -26.008 -25.739
S1d      objective  30  -6.294  -6.438  -6.168
         bg_tok_s   30 -15.364 -15.491 -15.145
         power_w    30 -18.104 -18.237 -17.910
S2       objective  30   3.972   3.962   3.973
         bg_tok_s   30  -2.436  -2.455  -2.436
         power_w    30 -12.818 -12.833 -12.810
S3       objective  30   0.000   0.000   0.000
         bg_tok_s   30   0.000   0.000   0.000
         power_w    30   0.000   0.000   0.000
S4       objective  30  -6.831  -6.913  -6.740
         bg_tok_s   30 -19.764 -19.918 -19.618
         power_w    30 -25.848 -26.008 -25.740
```

#### e minus g'
```
                     n  median      lo      hi
scenario metric                               
S0       objective  30   0.000   0.000   0.000
         bg_tok_s   30   0.000   0.000   0.000
         power_w    30   0.000   0.000   0.000
S1       objective  30   0.000   0.000   0.000
         bg_tok_s   30   0.000   0.000   0.000
         power_w    30   0.000   0.000   0.000
S1d      objective  30   0.000   0.000   0.000
         bg_tok_s   30   0.000   0.000   0.000
         power_w    30   0.000   0.000   0.000
S2       objective  30   4.356   4.356   4.356
         bg_tok_s   30  -1.764  -1.764  -1.764
         power_w    30 -12.239 -12.239 -12.239
S3       objective  30   0.000   0.000   0.000
         bg_tok_s   30   0.000   0.000   0.000
         power_w    30   0.000   0.000   0.000
S4       objective  30   0.000   0.000   0.000
         bg_tok_s   30   0.000   0.000   0.000
         power_w    30   0.000   0.000   0.000
```

#### e minus b'
```
                     n  median      lo      hi
scenario metric                               
S0       objective  30   0.000   0.000   0.000
         bg_tok_s   30   0.000   0.000   0.000
         power_w    30   0.000   0.000   0.000
S1       objective  30   0.000   0.000   0.000
         bg_tok_s   30   0.000   0.000   0.000
         power_w    30   0.000   0.000   0.000
S1d      objective  30   0.000   0.000   0.000
         bg_tok_s   30   0.000   0.000   0.000
         power_w    30   0.000   0.000   0.000
S2       objective  30   4.356   4.356   4.356
         bg_tok_s   30  -1.764  -1.764  -1.764
         power_w    30 -12.239 -12.239 -12.239
S3       objective  30   0.000   0.000   0.000
         bg_tok_s   30   0.000   0.000   0.000
         power_w    30   0.000   0.000   0.000
S4       objective  30   0.000   0.000   0.000
         bg_tok_s   30   0.000   0.000   0.000
         power_w    30   0.000   0.000   0.000
```

#### g' minus b'
```
                     n  median   lo   hi
scenario metric                         
S0       objective  30     0.0  0.0  0.0
         bg_tok_s   30     0.0  0.0  0.0
         power_w    30     0.0  0.0  0.0
S1       objective  30     0.0  0.0  0.0
         bg_tok_s   30     0.0  0.0  0.0
         power_w    30     0.0  0.0  0.0
S1d      objective  30     0.0  0.0  0.0
         bg_tok_s   30     0.0  0.0  0.0
         power_w    30     0.0  0.0  0.0
S2       objective  30     0.0  0.0  0.0
         bg_tok_s   30     0.0  0.0  0.0
         power_w    30     0.0  0.0  0.0
S3       objective  30     0.0  0.0  0.0
         bg_tok_s   30     0.0  0.0  0.0
         power_w    30     0.0  0.0  0.0
S4       objective  30     0.0  0.0  0.0
         bg_tok_s   30     0.0  0.0  0.0
         power_w    30     0.0  0.0  0.0
```

#### c' minus e
```
                     n  median      lo      hi
scenario metric                               
S0       objective  30   0.000   0.000   0.000
         bg_tok_s   30   0.000   0.000   0.000
         power_w    30   0.000   0.000   0.000
S1       objective  30 -11.111 -11.204 -11.029
         bg_tok_s   30 -25.727 -25.891 -25.600
         power_w    30 -29.232 -29.366 -29.134
S1d      objective  30  -3.535  -3.579  -3.457
         bg_tok_s   30  -8.218  -8.309  -8.073
         power_w    30  -9.585  -9.797  -9.396
S2       objective  30  -0.541  -0.542  -0.541
         bg_tok_s   30  -1.091  -1.091  -1.091
         power_w    30  -1.099  -1.099  -1.099
S3       objective  30  -0.000  -0.000   0.000
         bg_tok_s   30   0.000   0.000   0.000
         power_w    30   0.000   0.000   0.000
S4       objective  30 -11.111 -11.206 -11.029
         bg_tok_s   30 -25.727 -25.891 -25.600
         power_w    30 -29.232 -29.366 -29.138
```

#### d' minus e
```
                     n  median      lo      hi
scenario metric                               
S0       objective  30   0.000   0.000   0.000
         bg_tok_s   30   0.000   0.000   0.000
         power_w    30   0.000   0.000   0.000
S1       objective  30  -6.831  -6.913  -6.740
         bg_tok_s   30 -19.764 -19.918 -19.618
         power_w    30 -25.848 -26.008 -25.741
S1d      objective  30  -6.294  -6.438  -6.168
         bg_tok_s   30 -15.364 -15.491 -15.145
         power_w    30 -18.104 -18.237 -17.900
S2       objective  30  -0.383  -0.394  -0.383
         bg_tok_s   30  -0.673  -0.691  -0.673
         power_w    30  -0.579  -0.594  -0.579
S3       objective  30   0.000   0.000   0.000
         bg_tok_s   30   0.000   0.000   0.000
         power_w    30   0.000   0.000   0.000
S4       objective  30  -6.831  -6.915  -6.740
         bg_tok_s   30 -19.764 -19.927 -19.618
         power_w    30 -25.848 -26.008 -25.740
```

## plant with empirical token-time jitter

### SLO: mean miss fraction (top) and holds_slo (bottom)
```
controller       a       b   b'       c   c'       d   d'       g   g'    e  bj'
scenario                                                                        
S0          0.0000  0.0000  0.0  0.0000  0.0  0.0000  0.0  0.0000  0.0  0.0  0.0
S1          0.3383  0.0075  0.0  0.0056  0.0  0.0030  0.0  0.0018  0.0  0.0  0.0
S1d         0.0379  0.0042  0.0  0.0009  0.0  0.0003  0.0  0.0002  0.0  0.0  0.0
S2          0.0000  0.0000  0.0  0.0011  0.0  0.0009  0.0  0.0000  0.0  0.0  0.0
S3          0.5455  0.0099  0.0  0.0089  0.0  0.0053  0.0  0.0099  0.0  0.0  0.0
S4          0.0000  0.0000  0.0  0.0076  0.0  0.0000  0.0  0.0000  0.0  0.0  0.0
```
```
         a      b    b'      c    c'     d    d'      g    g'     e   bj'
S0    True   True  True   True  True  True  True   True  True  True  True
S1   False   True  True   True  True  True  True   True  True  True  True
S1d  False   True  True   True  True  True  True   True  True  True  True
S2    True   True  True   True  True  True  True   True  True  True  True
S3   False  False  True  False  True  True  True  False  True  True  True
S4    True   True  True   True  True  True  True   True  True  True  True
```

### Pareto headline (median tok/s, median power W; controllers that hold the SLO; `*` = on the Pareto front; objective = tok/s - 0.5 W is ONE marked point)

#### S0  (lambda = 0.5 best: c'*)
```
            tok_s  power_w  objective_lam0p5  j_per_token
controller                                               
b'          59.98    79.63             20.17         1.33
c'*         59.98    79.61             20.18         1.33
g'          59.98    79.63             20.17         1.33
e           59.98    79.63             20.17         1.33
bj'         59.98    79.63             20.17         1.33
d'*         59.96    79.60             20.16         1.33
b*          56.76    77.88             17.82         1.37
a           54.49    87.33             10.82         1.60
d*          10.65    38.44             -8.57         3.61
c*           6.95    34.87            -10.48         5.01
g*           3.40    31.40            -12.30         9.23
```

#### S1  (lambda = 0.5 best: b'*)
```
            tok_s  power_w  objective_lam0p5  j_per_token
controller                                               
b'*         52.99    73.62             16.18         1.39
g'*         52.99    73.62             16.18         1.39
e*          52.99    73.62             16.18         1.39
bj'*        52.99    73.62             16.18         1.39
d'*         34.18    48.57              9.90         1.42
d           29.64    55.64              1.82         1.88
c'*         28.24    45.24              5.62         1.60
b*          14.74    42.16             -6.34         2.86
c*           5.33    30.36             -9.85         5.70
g            3.40    31.40            -12.30         9.23
```

#### S1d  (lambda = 0.5 best: b'*)
```
            tok_s  power_w  objective_lam0p5  j_per_token
controller                                               
b'*         58.98    79.33             19.32         1.34
g'*         58.98    79.33             19.32         1.34
e*          58.98    79.33             19.32         1.34
bj'*        58.98    79.33             19.32         1.34
b           56.58    81.06             16.05         1.43
c'*         50.88    69.92             15.92         1.38
d'*         43.03    60.84             12.61         1.41
d           40.26    65.55              7.49         1.63
c*           5.65    32.53            -10.62         5.76
g*           3.35    31.94            -12.62         9.52
```

#### S2  (lambda = 0.5 best: e*)
```
            tok_s  power_w  objective_lam0p5  j_per_token
controller                                               
b'*         74.95    84.12             32.89         1.12
g'*         74.95    84.12             32.89         1.12
bj'*        74.95    84.12             32.89         1.12
e*          73.16    71.87             37.23         0.98
d'*         72.47    71.28             36.83         0.98
c'*         72.07    70.77             36.69         0.98
a           71.45    89.02             26.94         1.25
b           70.49    85.76             27.61         1.22
d*          40.44    44.49             18.19         1.10
c*          37.89    41.87             16.96         1.11
g*           4.02    23.38             -7.67         5.82
```

#### S3  (lambda = 0.5 best: c'*)
```
            tok_s  power_w  objective_lam0p5  j_per_token
controller                                               
b'          27.27    46.66              3.94         1.71
c'*         27.27    46.66              3.94         1.71
g'          27.27    46.66              3.94         1.71
e           27.27    46.66              3.94         1.71
bj'         27.27    46.66              3.94         1.71
d'*         27.25    46.65              3.93         1.71
d*           5.55    28.41             -8.66         5.12
```

#### S4  (lambda = 0.5 best: a*)
```
            tok_s  power_w  objective_lam0p5  j_per_token
controller                                               
a*          64.91    87.96             20.93         1.36
b*          64.91    87.96             20.93         1.36
b'*         53.15    73.74             16.28         1.39
g'*         53.15    73.74             16.28         1.39
e*          53.15    73.74             16.28         1.39
bj'*        53.15    73.74             16.28         1.39
d*          38.17    62.14              7.10         1.63
d'*         34.18    48.57              9.90         1.42
c'*         28.22    45.22              5.61         1.60
c*           6.07    30.77             -9.31         5.07
g            3.69    31.36            -11.99         8.49
```

### Paired comparisons on the objective, tok/s and power (median of A - B over seeds where both meet the SLO; 90% bootstrap CI)

#### d' minus c'   (PRIMARY learned-vs-feedback comparison)
```
                     n  median     lo     hi
scenario metric                             
S0       objective  30  -0.006 -0.010  0.000
         bg_tok_s   30  -0.009 -0.018  0.000
         power_w    30  -0.008 -0.016  0.000
S1       objective  30   4.297  4.181  4.351
         bg_tok_s   30   5.991  5.809  6.055
         power_w    30   3.364  3.243  3.406
S1d      objective  30  -3.352 -3.665 -3.154
         bg_tok_s   30  -7.827 -8.436 -7.564
         power_w    30  -8.789 -9.365 -8.499
S2       objective  30   0.157  0.147  0.158
         bg_tok_s   30   0.418  0.400  0.418
         power_w    30   0.518  0.506  0.521
S3       objective  30   0.000  0.000  0.000
         bg_tok_s   30   0.000  0.000  0.000
         power_w    30  -0.000 -0.000  0.000
S4       objective  30   4.297  4.199  4.333
         bg_tok_s   30   5.991  5.818  6.055
         power_w    30   3.359  3.251  3.409
```

#### c' minus g'
```
                     n  median      lo      hi
scenario metric                               
S0       objective  30   0.000  -0.010   0.000
         bg_tok_s   30   0.000  -0.018   0.000
         power_w    30   0.000  -0.015   0.000
S1       objective  30 -10.523 -10.673 -10.469
         bg_tok_s   30 -24.718 -24.992 -24.545
         power_w    30 -28.399 -28.593 -28.176
S1d      objective  30  -3.429  -3.522  -3.342
         bg_tok_s   30  -8.018  -8.255  -7.891
         power_w    30  -9.446  -9.588  -9.228
S2       objective  30   3.803   3.799   3.811
         bg_tok_s   30  -2.873  -2.873  -2.855
         power_w    30 -13.342 -13.347 -13.340
S3       objective  30  -0.000  -0.000  -0.000
         bg_tok_s   30   0.000   0.000   0.000
         power_w    30   0.000   0.000   0.000
S4       objective  30 -10.629 -10.733 -10.569
         bg_tok_s   30 -24.864 -25.109 -24.745
         power_w    30 -28.504 -28.649 -28.366
```

#### d' minus g'
```
                     n  median      lo      hi
scenario metric                               
S0       objective  30  -0.010  -0.021  -0.010
         bg_tok_s   30  -0.018  -0.036  -0.018
         power_w    30  -0.016  -0.031  -0.016
S1       objective  30  -6.309  -6.402  -6.222
         bg_tok_s   30 -18.873 -19.036 -18.673
         power_w    30 -25.107 -25.250 -24.935
S1d      objective  30  -6.738  -6.934  -6.463
         bg_tok_s   30 -15.964 -16.565 -15.418
         power_w    30 -18.438 -19.320 -17.937
S2       objective  30   3.957   3.952   3.962
         bg_tok_s   30  -2.455  -2.473  -2.455
         power_w    30 -12.832 -12.834 -12.820
S3       objective  30  -0.000  -0.010   0.000
         bg_tok_s   30   0.000  -0.018   0.000
         power_w    30  -0.000  -0.016   0.000
S4       objective  30  -6.410  -6.460  -6.255
         bg_tok_s   30 -19.027 -19.091 -18.773
         power_w    30 -25.227 -25.309 -25.018
```

#### e minus g'
```
                     n  median      lo      hi
scenario metric                               
S0       objective  30   0.000   0.000   0.000
         bg_tok_s   30   0.000   0.000   0.000
         power_w    30   0.000   0.000   0.000
S1       objective  30   0.000   0.000   0.000
         bg_tok_s   30   0.000   0.000   0.000
         power_w    30   0.000   0.000   0.000
S1d      objective  30   0.000   0.000   0.000
         bg_tok_s   30   0.000   0.000   0.000
         power_w    30   0.000   0.000   0.000
S2       objective  30   4.354   4.349   4.355
         bg_tok_s   30  -1.764  -1.773  -1.764
         power_w    30 -12.240 -12.244 -12.238
S3       objective  30   0.000   0.000   0.000
         bg_tok_s   30   0.000   0.000   0.000
         power_w    30   0.000   0.000   0.000
S4       objective  30   0.000   0.000   0.000
         bg_tok_s   30   0.000   0.000   0.000
         power_w    30   0.000   0.000   0.000
```

#### e minus b'
```
                     n  median      lo      hi
scenario metric                               
S0       objective  30   0.000   0.000   0.000
         bg_tok_s   30   0.000   0.000   0.000
         power_w    30   0.000   0.000   0.000
S1       objective  30   0.000   0.000   0.000
         bg_tok_s   30   0.000   0.000   0.000
         power_w    30   0.000   0.000   0.000
S1d      objective  30   0.000   0.000   0.000
         bg_tok_s   30   0.000   0.000   0.000
         power_w    30   0.000   0.000   0.000
S2       objective  30   4.354   4.349   4.355
         bg_tok_s   30  -1.764  -1.782  -1.764
         power_w    30 -12.240 -12.244 -12.238
S3       objective  30   0.000   0.000   0.000
         bg_tok_s   30   0.000   0.000   0.000
         power_w    30   0.000   0.000   0.000
S4       objective  30   0.000   0.000   0.000
         bg_tok_s   30   0.000   0.000   0.000
         power_w    30   0.000   0.000   0.000
```

#### g' minus b'
```
                     n  median   lo   hi
scenario metric                         
S0       objective  30     0.0  0.0  0.0
         bg_tok_s   30     0.0  0.0  0.0
         power_w    30     0.0  0.0  0.0
S1       objective  30     0.0  0.0  0.0
         bg_tok_s   30     0.0  0.0  0.0
         power_w    30     0.0  0.0  0.0
S1d      objective  30     0.0  0.0  0.0
         bg_tok_s   30     0.0  0.0  0.0
         power_w    30     0.0  0.0  0.0
S2       objective  30     0.0  0.0  0.0
         bg_tok_s   30     0.0  0.0  0.0
         power_w    30     0.0  0.0  0.0
S3       objective  30     0.0  0.0  0.0
         bg_tok_s   30     0.0  0.0  0.0
         power_w    30     0.0  0.0  0.0
S4       objective  30     0.0  0.0  0.0
         bg_tok_s   30     0.0  0.0  0.0
         power_w    30     0.0  0.0  0.0
```

#### c' minus e
```
                     n  median      lo      hi
scenario metric                               
S0       objective  30   0.000  -0.010   0.000
         bg_tok_s   30   0.000  -0.018   0.000
         power_w    30   0.000  -0.015   0.000
S1       objective  30 -10.523 -10.705 -10.469
         bg_tok_s   30 -24.718 -24.964 -24.545
         power_w    30 -28.399 -28.593 -28.161
S1d      objective  30  -3.429  -3.541  -3.342
         bg_tok_s   30  -8.018  -8.255  -7.882
         power_w    30  -9.446  -9.647  -9.238
S2       objective  30  -0.542  -0.543  -0.541
         bg_tok_s   30  -1.091  -1.091  -1.091
         power_w    30  -1.100  -1.103  -1.099
S3       objective  30  -0.000  -0.000  -0.000
         bg_tok_s   30   0.000   0.000   0.000
         power_w    30   0.000   0.000   0.000
S4       objective  30 -10.629 -10.750 -10.569
         bg_tok_s   30 -24.864 -25.064 -24.745
         power_w    30 -28.504 -28.649 -28.355
```

#### d' minus e
```
                     n  median      lo      hi
scenario metric                               
S0       objective  30  -0.010  -0.021  -0.010
         bg_tok_s   30  -0.018  -0.036  -0.018
         power_w    30  -0.016  -0.031  -0.016
S1       objective  30  -6.309  -6.402  -6.222
         bg_tok_s   30 -18.873 -19.027 -18.673
         power_w    30 -25.107 -25.245 -24.935
S1d      objective  30  -6.738  -6.934  -6.444
         bg_tok_s   30 -15.964 -16.545 -15.418
         power_w    30 -18.438 -19.265 -17.937
S2       objective  30  -0.393  -0.402  -0.385
         bg_tok_s   30  -0.691  -0.691  -0.673
         power_w    30  -0.584  -0.599  -0.578
S3       objective  30  -0.000  -0.010   0.000
         bg_tok_s   30   0.000  -0.018   0.000
         power_w    30  -0.000  -0.016   0.000
S4       objective  30  -6.410  -6.465  -6.254
         bg_tok_s   30 -19.027 -19.091 -18.773
         power_w    30 -25.227 -25.309 -25.037
```

#### bj' minus b'
```
                     n  median   lo   hi
scenario metric                         
S0       objective  30     0.0  0.0  0.0
         bg_tok_s   30     0.0  0.0  0.0
         power_w    30     0.0  0.0  0.0
S1       objective  30     0.0  0.0  0.0
         bg_tok_s   30     0.0  0.0  0.0
         power_w    30     0.0  0.0  0.0
S1d      objective  30     0.0  0.0  0.0
         bg_tok_s   30     0.0  0.0  0.0
         power_w    30     0.0  0.0  0.0
S2       objective  30     0.0  0.0  0.0
         bg_tok_s   30     0.0  0.0  0.0
         power_w    30     0.0  0.0  0.0
S3       objective  30     0.0  0.0  0.0
         bg_tok_s   30     0.0  0.0  0.0
         power_w    30     0.0  0.0  0.0
S4       objective  30     0.0  0.0  0.0
         bg_tok_s   30     0.0  0.0  0.0
         power_w    30     0.0  0.0  0.0
```
