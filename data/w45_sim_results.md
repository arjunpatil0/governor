# W4-5 simulator study: controllers vs the plant (SIMULATION ONLY, held-out evaluation seeds)

Protocol: docs/W45_SIM_PROTOCOL.md (written before any controller ran). Evaluation seeds 200-229 (30); tuning seeds 100-109; controller constants frozen in data/sim_tuned.json. Foreground: 60 Hz periodic, deadline 16.667 ms, base cost 7.0 ms at 1800 MHz, jitter sigma 0.03 (assumption).
Plant parameters come from committed results (sim/params.py); the time-slice share divisor is fitted to the A2 SA4 anchors (data/sim_calibration.json). These numbers are NOT hardware results; the plant is validated only by the hardware smoke and W5.

Unmeasured assumptions in the plant:
- fg and bg effects separable: no joint (clock, duty) measurement exists
- bg speed under contention follows the same time-slice share as the fg (L measured the bg alone)
- token-level pacing: a bg token is one indivisible ~10 ms job (A2 duty used 2 ms slices)
- 'unlocked' fg speed from W1 (2460 MHz) with no thermal throttling unless a scenario caps it
- fg frame jitter (jitter_sigma) is a scenario parameter, not measured
- idle power 5 W from a single pilot observation (journal 0011)
- bg token time is deterministic at the L median rate (no token-time jitter or CPU-side stalls), so the guard only has to absorb fg jitter

## 1. SLO (fg deadline-miss fraction <= 1%)

`holds_slo`: mean miss <= 1% and >= 90% of seeds with miss <= 1% (protocol rule 1).

### S0
```
            mean_miss  pct_runs_ok  holds_slo
controller                                   
a                 0.0        100.0       True
b                 0.0        100.0       True
b'                0.0        100.0       True
c                 0.0        100.0       True
c'                0.0        100.0       True
d                 0.0        100.0       True
d'                0.0        100.0       True
```

### S1
```
            mean_miss  pct_runs_ok  holds_slo
controller                                   
a              0.3383          0.0      False
b              0.0072        100.0       True
b'             0.0000        100.0       True
c              0.0056        100.0       True
c'             0.0000        100.0       True
d              0.0031        100.0       True
d'             0.0000        100.0       True
```

### S1d
```
            mean_miss  pct_runs_ok  holds_slo
controller                                   
a              0.0379          0.0      False
b              0.0042        100.0       True
b'             0.0000        100.0       True
c              0.0006        100.0       True
c'             0.0000        100.0       True
d              0.0003        100.0       True
d'             0.0000        100.0       True
```

### S2
```
            mean_miss  pct_runs_ok  holds_slo
controller                                   
a              0.0000        100.0       True
b              0.0000        100.0       True
b'             0.0000        100.0       True
c              0.0012        100.0       True
c'             0.0000        100.0       True
d              0.0008        100.0       True
d'             0.0000        100.0       True
```

### S3
```
            mean_miss  pct_runs_ok  holds_slo
controller                                   
a              0.5455       0.0000      False
b              0.0120       3.3333      False
b'             0.0000     100.0000       True
c              0.0085      90.0000       True
c'             0.0000     100.0000       True
d              0.0047     100.0000       True
d'             0.0000     100.0000       True
```

### S4
```
            mean_miss  pct_runs_ok  holds_slo
controller                                   
a              0.0000     100.0000       True
b              0.0000     100.0000       True
b'             0.0000     100.0000       True
c              0.0076      96.6667       True
c'             0.0000     100.0000       True
d              0.0000     100.0000       True
d'             0.0000     100.0000       True
```

## 2. Performance (median over all evaluation seeds; compare only where the SLO holds)

### S0
```
            bg_tok_s  power_w  objective  j_per_token  clock_changes  holds_slo
controller                                                                     
a              54.49    87.33      10.82         1.60            0.0       True
b              60.00    79.81      20.10         1.33            0.0       True
b'             60.00    79.63      20.19         1.33            0.0       True
c               6.91    34.82     -10.50         5.04            0.0       True
c'             60.00    79.63      20.19         1.33            0.0       True
d              10.66    38.45      -8.57         3.61            0.0       True
d'             60.00    79.63      20.19         1.33            0.0       True
```

### S1
```
            bg_tok_s  power_w  objective  j_per_token  clock_changes  holds_slo
controller                                                                     
a              54.50    87.33      10.83         1.60            0.0      False
b              15.58    42.67      -5.75         2.74            0.0       True
b'             53.85    74.36      16.68         1.38            0.0       True
c               5.24    30.28      -9.91         5.79           12.0       True
c'             28.25    45.23       5.64         1.60           28.0       True
d              29.51    55.52       1.76         1.88            0.0       True
d'             34.21    48.59       9.92         1.42            5.0       True
```

### S1d
```
            bg_tok_s  power_w  objective  j_per_token  clock_changes  holds_slo
controller                                                                     
a              53.33    87.22       9.72         1.64            0.0      False
b              56.88    81.24      16.27         1.43            0.0       True
b'             59.31    79.60      19.50         1.34            0.0       True
c               5.75    32.61     -10.57         5.68            6.0       True
c'             51.05    70.07      15.96         1.37           14.0       True
d              44.29    69.03       9.78         1.56            0.0       True
d'             43.95    61.48      13.19         1.40            5.0       True
```

### S2
```
            bg_tok_s  power_w  objective  j_per_token  clock_changes  holds_slo
controller                                                                     
a              71.45    89.02      26.94         1.25            0.0       True
b              70.53    85.77      27.64         1.22            0.0       True
b'             74.95    84.12      32.89         1.12            0.0       True
c              37.82    41.81      16.91         1.11            3.0       True
c'             72.09    70.78      36.70         0.98            3.0       True
d              40.46    44.51      18.21         1.10            3.0       True
d'             72.51    71.30      36.85         0.98            3.0       True
```

### S3
```
            bg_tok_s  power_w  objective  j_per_token  clock_changes  holds_slo
controller                                                                     
a              45.98    64.08      13.94         1.39            0.0      False
b               2.85    25.61      -9.96         8.98            0.0      False
b'             27.27    46.67       3.94         1.71            0.0       True
c               4.29    27.08      -9.25         6.31            2.0       True
c'             27.27    46.67       3.94         1.71            2.0       True
d               5.49    28.36      -8.70         5.17            0.0       True
d'             27.27    46.67       3.94         1.71            0.0       True
```

### S4
```
            bg_tok_s  power_w  objective  j_per_token  clock_changes  holds_slo
controller                                                                     
a              64.91    87.96      20.93         1.36            0.0       True
b              64.91    87.96      20.93         1.36            0.0       True
b'             53.85    74.36      16.68         1.38            0.0       True
c               6.11    30.75      -9.24         5.03           12.0       True
c'             28.25    45.23       5.64         1.60           28.0       True
d              38.60    62.55       7.33         1.62            0.0       True
d'             34.21    48.59       9.92         1.42            5.0       True
```

## 3. Paired comparisons (median of A - B over seeds where both meet the SLO; 90% bootstrap CI)

### d minus c
```
                     n  median      lo      hi
scenario metric                               
S0       objective  30   1.958   1.912   2.035
         bg_tok_s   30   3.782   3.691   3.909
         power_w    30   3.654   3.553   3.785
S1       objective  30  11.725  11.640  11.753
         bg_tok_s   30  24.427  24.209  24.482
         power_w    30  25.331  25.130  25.484
S1d      objective  30  20.448  19.913  20.956
         bg_tok_s   30  38.727  37.855  39.745
         power_w    30  36.546  35.852  37.627
S2       objective  30   1.319   1.221   1.386
         bg_tok_s   30   2.673   2.509   2.782
         power_w    30   2.697   2.577   2.802
S3       objective  27   0.580   0.514   0.635
         bg_tok_s   27   1.218   1.127   1.345
         power_w    27   1.292   1.251   1.397
S4       objective  29  16.582  16.469  16.622
         bg_tok_s   29  32.382  32.291  32.673
         power_w    29  31.641  31.588  31.875
```

### d' minus c'
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

### c' minus c
```
                     n  median      lo      hi
scenario metric                               
S0       objective  30  30.691  30.651  30.751
         bg_tok_s   30  53.091  53.009  53.200
         power_w    30  44.799  44.730  44.892
S1       objective  30  15.541  15.487  15.589
         bg_tok_s   30  23.036  23.000  23.100
         power_w    30  14.950  14.900  15.020
S1d      objective  30  26.519  26.474  26.623
         bg_tok_s   30  45.273  45.218  45.509
         power_w    30  37.360  37.169  37.560
S2       objective  30  19.789  19.686  19.927
         bg_tok_s   30  34.273  34.064  34.509
         power_w    30  28.967  28.748  29.152
S3       objective  27  13.189  13.152  13.245
         bg_tok_s   27  22.964  22.909  23.109
         power_w    27  19.557  19.526  19.702
S4       objective  29  14.966  14.780  15.028
         bg_tok_s   29  22.164  21.964  22.309
         power_w    29  14.431  14.340  14.543
```

### d' minus d
```
                     n  median      lo      hi
scenario metric                               
S0       objective  30  28.750  28.700  28.797
         bg_tok_s   30  49.336  49.264  49.427
         power_w    30  41.180  41.108  41.263
S1       objective  30   8.166   8.101   8.195
         bg_tok_s   30   4.691   4.545   4.782
         power_w    30  -6.943  -7.110  -6.882
S1d      objective  30   3.461   2.698   4.221
         bg_tok_s   30  -0.173  -1.800   1.027
         power_w    30  -7.267  -8.724  -6.577
S2       objective  30  18.648  18.608  18.687
         bg_tok_s   30  32.045  31.982  32.109
         power_w    30  26.794  26.746  26.847
S3       objective  30  12.637  12.617  12.662
         bg_tok_s   30  21.782  21.745  21.836
         power_w    30  18.300  18.269  18.336
S4       objective  30   2.592   2.495   2.641
         bg_tok_s   30  -4.382  -4.564  -4.291
         power_w    30 -13.958 -14.126 -13.858
```

### b' minus b
```
                     n  median      lo      hi
scenario metric                               
S0       objective  30   0.089   0.089   0.089
         bg_tok_s   30   0.000   0.000   0.000
         power_w    30  -0.177  -0.178  -0.177
S1       objective  30  22.481  22.397  22.581
         bg_tok_s   30  38.382  38.236  38.473
         power_w    30  31.760  31.693  31.883
S1d      objective  30   3.227   3.156   3.296
         bg_tok_s   30   2.409   2.309   2.509
         power_w    30  -1.641  -1.697  -1.593
S2       objective  30   5.248   5.235   5.258
         bg_tok_s   30   4.418   4.400   4.436
         power_w    30  -1.660  -1.665  -1.648
S3       objective   1  13.793  13.793  13.793
         bg_tok_s    1  24.291  24.291  24.291
         power_w     1  20.995  20.995  20.995
S4       objective  30  -4.245  -4.264  -4.127
         bg_tok_s   30 -11.045 -11.073 -10.818
         power_w    30 -13.597 -13.618 -13.400
```

### c' minus b'
```
                     n  median      lo      hi
scenario metric                               
S0       objective  30   0.000   0.000   0.000
         bg_tok_s   30   0.000   0.000   0.000
         power_w    30   0.000   0.000   0.000
S1       objective  30 -11.111 -11.206 -11.026
         bg_tok_s   30 -25.727 -25.891 -25.600
         power_w    30 -29.232 -29.366 -29.138
S1d      objective  30  -3.535  -3.579  -3.462
         bg_tok_s   30  -8.218  -8.309  -8.082
         power_w    30  -9.585  -9.722  -9.391
S2       objective  30   3.814   3.814   3.815
         bg_tok_s   30  -2.855  -2.855  -2.855
         power_w    30 -13.338 -13.338 -13.338
S3       objective  30  -0.000  -0.000   0.000
         bg_tok_s   30   0.000   0.000   0.000
         power_w    30   0.000   0.000   0.000
S4       objective  30 -11.111 -11.206 -11.029
         bg_tok_s   30 -25.727 -25.891 -25.600
         power_w    30 -29.232 -29.366 -29.138
```

### d' minus b'
```
                     n  median      lo      hi
scenario metric                               
S0       objective  30   0.000   0.000   0.000
         bg_tok_s   30   0.000   0.000   0.000
         power_w    30   0.000   0.000   0.000
S1       objective  30  -6.831  -6.913  -6.740
         bg_tok_s   30 -19.764 -19.927 -19.618
         power_w    30 -25.848 -26.008 -25.739
S1d      objective  30  -6.294  -6.438  -6.159
         bg_tok_s   30 -15.364 -15.491 -15.145
         power_w    30 -18.104 -18.222 -17.882
S2       objective  30   3.972   3.962   3.973
         bg_tok_s   30  -2.436  -2.455  -2.436
         power_w    30 -12.818 -12.833 -12.817
S3       objective  30   0.000   0.000   0.000
         bg_tok_s   30   0.000   0.000   0.000
         power_w    30   0.000   0.000   0.000
S4       objective  30  -6.831  -6.913  -6.743
         bg_tok_s   30 -19.764 -19.918 -19.618
         power_w    30 -25.848 -26.008 -25.740
```

### c minus b
```
                     n  median      lo      hi
scenario metric                               
S0       objective  30 -30.591 -30.649 -30.544
         bg_tok_s   30 -53.073 -53.173 -52.990
         power_w    30 -44.966 -45.041 -44.901
S1       objective  30  -4.134  -4.240  -4.060
         bg_tok_s   30 -10.445 -10.509 -10.218
         power_w    30 -12.445 -12.523 -12.332
S1d      objective  30 -26.838 -26.925 -26.765
         bg_tok_s   30 -51.164 -51.291 -51.073
         power_w    30 -48.648 -48.690 -48.572
S2       objective  30 -10.721 -10.860 -10.620
         bg_tok_s   30 -32.700 -32.927 -32.491
         power_w    30 -43.959 -44.146 -43.767
S3       objective   1   0.644   0.644   0.644
         bg_tok_s    1   1.382   1.382   1.382
         power_w     1   1.475   1.475   1.475
S4       objective  29 -30.207 -30.275 -30.122
         bg_tok_s   29 -58.800 -58.910 -58.600
         power_w    29 -57.204 -57.243 -57.044
```

### d minus b
```
                     n  median      lo      hi
scenario metric                               
S0       objective  30 -28.656 -28.705 -28.596
         bg_tok_s   30 -49.318 -49.418 -49.218
         power_w    30 -41.342 -41.438 -41.275
S1       objective  30   7.538   7.454   7.597
         bg_tok_s   30  13.973  13.891  14.091
         power_w    30  12.893  12.796  12.967
S1d      objective  30  -6.556  -6.871  -5.757
         bg_tok_s   30 -12.682 -13.140 -11.291
         power_w    30 -12.251 -12.694 -11.086
S2       objective  30  -9.429  -9.465  -9.382
         bg_tok_s   30 -30.055 -30.127 -29.982
         power_w    30 -41.254 -41.324 -41.216
S3       objective   1   1.154   1.154   1.154
         bg_tok_s    1   2.509   2.509   2.509
         power_w     1   2.711   2.711   2.711
S4       objective  30 -13.607 -13.694 -13.522
         bg_tok_s   30 -26.309 -26.464 -26.145
         power_w    30 -25.408 -25.550 -25.248
```

## 4. Does the learned part earn its place? (protocol rule 3, objective = tok/s - 0.5 W)

- d vs c: **EARNS ITS PLACE** under the pre-registered rule (a win with CI above 0 in S1 and S4, no loss in S0/S2/S3).
- d' vs c': **EARNS ITS PLACE** under the pre-registered rule (a win with CI above 0 in S1 and S4, no loss in S0/S2/S3).

Against the best static setting (objective difference, 90% CI; wins = CI above 0, losses = CI below 0):

- c vs b: wins in ['S3'], losses in ['S0', 'S1', 'S1d', 'S2', 'S4']
- d vs b: wins in ['S1', 'S3'], losses in ['S0', 'S1d', 'S2', 'S4']
- c' vs b': wins in ['S2'], losses in ['S1', 'S1d', 'S4']
- d' vs b': wins in ['S2'], losses in ['S1', 'S1d', 'S4']
- b' vs b: wins in ['S0', 'S1', 'S1d', 'S2', 'S3'], losses in ['S4']

## 5. Frozen controller constants

```
{
 "c": {
  "clock_margin": 0.35,
  "kp": 0.5,
  "ki": 0.15,
  "target": 0.5
 },
 "c'": {
  "ki": 0.05,
  "target": 0.65,
  "guard0": 0.5,
  "gmin": 0.3
 },
 "d": {
  "safety": 0.5,
  "gamma_alpha": 0.05,
  "switch_gain": 0.5
 },
 "d'": {
  "safety": 0.8,
  "switch_gain": 2.0,
  "clock_every": 20
 }
}
```

Best-static settings are in data/sim_tuned.json (per scenario, tuned on the tuning seeds). Static settings are per-scenario oracles; the dynamic controllers use one parameter set for all scenarios.