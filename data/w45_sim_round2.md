# W4-5 simulator, ROUND 2 (POST-HOC / SENSITIVITY; SIMULATION ONLY; rounds 0-1 unchanged)

Adds scene S5 (S1 foreground + UNSEEN background: fp16-proxy curve from data/w2_C_results.md, knee 1050; absolute rate scaled to the L unlocked rate, only the shape is from C) and d'B v2. d'B v2 constants chosen on tuning seeds 100-109 over S0-S4 at both budgets (0 of 32 parameter sets hold the SLO and budget in every cell); round-2 evaluation seeds 300-329 (new). g'B, c'B, eB keep round-1 constants tuned on the L plant; b'B for S5 is an oracle tuned on S5 tuning seeds. The plant is unchanged except for the S5 profile and the token-duration observation.

Chosen d'B v2 constants:
```
{
 "safety": 0.8,
 "switch_gain": 0.5,
 "clock_every": 10,
 "guard_k": 3.0,
 "sigma_w": 0.0,
 "guard_floor": 0.0
}
```

## Budget 60 W

### S0
```
            mean_miss  pct_within_budget  pct_feasible  power_w_med  tok_s_med  tok_s_med_feasible  holds
controller                                                                                               
a                 0.0                0.0           0.0        87.33      54.49                 NaN  False
g'B               0.0              100.0         100.0        53.84      30.00               30.00   True
eB                0.0              100.0         100.0        53.84      30.00               30.00   True
c'B               0.0              100.0         100.0        58.12      34.98               34.98   True
d'B               0.0              100.0         100.0        53.83      30.00               30.00   True
d'B2              0.0              100.0         100.0        53.83      30.00               30.00   True
b'B               0.0              100.0         100.0        53.83      30.00               30.00   True
```
### S1
```
            mean_miss  pct_within_budget  pct_feasible  power_w_med  tok_s_med  tok_s_med_feasible  holds
controller                                                                                               
a                0.34                0.0           0.0        87.33      54.49                 NaN  False
g'B              0.00              100.0         100.0        54.92      31.26               31.26   True
eB               0.00              100.0         100.0        54.92      31.26               31.26   True
c'B              0.00              100.0         100.0        42.61      25.07               25.07   True
d'B              0.00              100.0         100.0        42.71      26.03               26.03   True
d'B2             0.00              100.0         100.0        51.73      36.35               36.35   True
b'B              0.00              100.0         100.0        54.92      31.26               31.26   True
```
### S1d
```
            mean_miss  pct_within_budget  pct_feasible  power_w_med  tok_s_med  tok_s_med_feasible  holds
controller                                                                                               
a                0.04                0.0           0.0        87.22      53.33                 NaN  False
g'B              0.00              100.0         100.0        54.26      29.82               29.82   True
eB               0.00              100.0         100.0        54.26      29.82               29.82   True
c'B              0.00              100.0         100.0        56.56      36.95               36.95   True
d'B              0.00              100.0         100.0        48.51      27.21               27.21   True
d'B2             0.00              100.0         100.0        53.64      37.30               37.30   True
b'B              0.00              100.0         100.0        54.26      29.82               29.82   True
```
### S2
```
            mean_miss  pct_within_budget  pct_feasible  power_w_med  tok_s_med  tok_s_med_feasible  holds
controller                                                                                               
a                 0.0                0.0           0.0        89.02      71.44                 NaN  False
g'B               0.0              100.0         100.0        51.90      37.49               37.49   True
eB                0.0              100.0         100.0        54.88      53.42               53.42   True
c'B               0.0              100.0         100.0        55.52      52.49               52.49   True
d'B               0.0              100.0         100.0        54.30      52.75               52.75   True
d'B2              0.0              100.0         100.0        54.54      53.00               53.00   True
b'B               0.0              100.0         100.0        51.90      37.49               37.49   True
```
### S3
```
            mean_miss  pct_within_budget  pct_feasible  power_w_med  tok_s_med  tok_s_med_feasible  holds
controller                                                                                               
a                0.55                0.0           0.0        64.08      45.98                 NaN  False
g'B              0.00              100.0         100.0        34.94      13.64               13.64   True
eB               0.00              100.0         100.0        34.94      13.64               13.64   True
c'B              0.00              100.0         100.0        36.84      15.84               15.84   True
d'B              0.00              100.0         100.0        34.94      13.64               13.64   True
d'B2             0.00              100.0         100.0        34.94      13.64               13.64   True
b'B              0.00              100.0         100.0        46.67      27.27               27.27   True
```
### S4
```
            mean_miss  pct_within_budget  pct_feasible  power_w_med  tok_s_med  tok_s_med_feasible  holds
controller                                                                                               
a                 0.0                0.0           0.0        87.95      64.91                 NaN  False
g'B               0.0              100.0         100.0        54.92      31.26               31.26   True
eB                0.0              100.0         100.0        54.92      31.26               31.26   True
c'B               0.0              100.0         100.0        42.61      25.07               25.07   True
d'B               0.0              100.0         100.0        42.71      26.03               26.03   True
d'B2              0.0              100.0         100.0        51.73      36.35               36.35   True
b'B               0.0              100.0         100.0        54.92      31.26               31.26   True
```
### S5
```
            mean_miss  pct_within_budget  pct_feasible  power_w_med  tok_s_med  tok_s_med_feasible  holds
controller                                                                                               
a                0.34                0.0           0.0        84.30      54.49                 NaN  False
g'B              0.00              100.0         100.0        53.40      31.26               31.26   True
eB               0.00              100.0         100.0        53.40      31.26               31.26   True
c'B              0.00              100.0         100.0        42.47      25.94               25.94   True
d'B              0.00              100.0         100.0        42.23      26.13               26.13   True
d'B2             0.00              100.0         100.0        50.60      36.16               36.16   True
b'B              0.00              100.0         100.0        59.42      38.68               38.68   True
```
### Paired comparisons on tok/s (median of A - B over seeds where BOTH are feasible; 90% bootstrap CI)

#### d'B2 minus c'B (tok/s)
```
           n  median      lo      hi
scenario                            
S0        30  -4.982  -5.000  -4.982
S1        30  11.282  11.218  11.327
S1d       30  -0.109  -1.382   1.645
S2        30   0.527   0.509   0.527
S3        30  -2.200  -2.200  -2.200
S4        30  11.282  11.200  11.327
S5        30  10.218  10.145  10.300
```
#### d'B2 minus g'B (tok/s)
```
           n  median      lo      hi
scenario                            
S0        30   0.000   0.000   0.000
S1        30   5.100   4.982   5.145
S1d       30   7.455   7.382   7.545
S2        30  15.509  15.509  15.509
S3        30   0.000   0.000   0.000
S4        30   5.100   4.982   5.136
S5        30   4.882   4.818   4.945
```
#### d'B2 minus eB (tok/s)
```
           n  median     lo     hi
scenario                          
S0        30   0.000  0.000  0.000
S1        30   5.100  4.982  5.145
S1d       30   7.455  7.400  7.545
S2        30  -0.400 -0.418 -0.400
S3        30   0.000  0.000  0.000
S4        30   5.100  4.991  5.136
S5        30   4.882  4.818  4.945
```
#### d'B2 minus b'B (tok/s)
```
           n  median      lo      hi
scenario                            
S0        30   0.000   0.000   0.000
S1        30   5.100   4.991   5.145
S1d       30   7.455   7.409   7.545
S2        30  15.509  15.509  15.509
S3        30 -13.636 -13.636 -13.636
S4        30   5.100   4.982   5.136
S5        30  -2.564  -2.636  -2.482
```
#### d'B2 minus d'B (tok/s)
```
           n  median      lo      hi
scenario                            
S0        30   0.000   0.000   0.000
S1        30  10.318  10.236  10.364
S1d       30   9.991   9.800  10.155
S2        30   0.273   0.255   0.291
S3        30   0.000   0.000   0.000
S4        30  10.318  10.236  10.355
S5        30  10.018   9.982  10.055
```
#### c'B minus g'B (tok/s)
```
           n  median      lo      hi
scenario                            
S0        30   4.982   4.982   5.000
S1        30  -6.236  -6.273  -6.145
S1d       30   7.127   5.673   8.973
S2        30  15.000  14.982  15.000
S3        30   2.200   2.200   2.200
S4        30  -6.236  -6.273  -6.145
S5        30  -5.364  -5.418  -5.291
```
## Budget 35 W

### S0
```
            mean_miss  pct_within_budget  pct_feasible  power_w_med  tok_s_med  tok_s_med_feasible  holds
controller                                                                                               
a                 0.0                0.0           0.0        87.33      54.49                 NaN  False
g'B               0.0              100.0         100.0        21.60       0.00                0.00   True
eB                0.0              100.0         100.0        21.60       0.00                0.00   True
c'B               0.0              100.0         100.0        33.96       6.89                6.89   True
d'B               0.0              100.0         100.0        18.36       0.00                0.00   True
d'B2              0.0              100.0         100.0        32.33       5.00                5.00   True
b'B               0.0              100.0         100.0        22.55       1.55                1.55   True
```
### S1
```
            mean_miss  pct_within_budget  pct_feasible  power_w_med  tok_s_med  tok_s_med_feasible  holds
controller                                                                                               
a                0.34                0.0           0.0        87.33      54.49                 NaN  False
g'B              0.00              100.0         100.0        34.91      21.82               21.82   True
eB               0.00              100.0         100.0        34.91      21.82               21.82   True
c'B              0.00              100.0         100.0        33.59      12.67               12.67   True
d'B              0.00              100.0         100.0        26.09       8.02                8.02   True
d'B2             0.00              100.0         100.0        28.86      11.44               11.44   True
b'B              0.00              100.0         100.0        34.91      21.82               21.82   True
```
### S1d
```
            mean_miss  pct_within_budget  pct_feasible  power_w_med  tok_s_med  tok_s_med_feasible  holds
controller                                                                                               
a                0.04                0.0           0.0        87.22      53.33                 NaN  False
g'B              0.00              100.0         100.0        30.17      13.36               13.36   True
eB               0.00              100.0         100.0        30.17      13.36               13.36   True
c'B              0.00                0.0           0.0        36.43      12.58                 NaN  False
d'B              0.00              100.0         100.0        26.01       5.61                5.61   True
d'B2             0.00              100.0         100.0        30.29       9.23                9.23   True
b'B              0.00              100.0         100.0        33.09      18.16               18.16   True
```
### S2
```
            mean_miss  pct_within_budget  pct_feasible  power_w_med  tok_s_med  tok_s_med_feasible  holds
controller                                                                                               
a                 0.0                0.0           0.0        89.02      71.44                 NaN  False
g'B               0.0              100.0         100.0        33.21      28.91               28.91   True
eB                0.0              100.0         100.0        34.31      35.09               35.09   True
c'B               0.0              100.0         100.0        32.92      21.65               21.65   True
d'B               0.0              100.0         100.0        31.53      33.67               33.67   True
d'B2              0.0                0.0           0.0        40.59      36.78                 NaN  False
b'B               0.0              100.0         100.0        32.70      35.38               35.38   True
```
### S3
```
            mean_miss  pct_within_budget  pct_feasible  power_w_med  tok_s_med  tok_s_med_feasible  holds
controller                                                                                               
a                0.55                0.0           0.0        64.08      45.98                 NaN  False
g'B              0.00              100.0         100.0        20.29       0.00                0.00   True
eB               0.00              100.0         100.0        20.29       0.00                0.00   True
c'B              0.00              100.0         100.0        25.91       3.15                3.15   True
d'B              0.00              100.0         100.0        18.36       0.00                0.00   True
d'B2             0.00              100.0         100.0        25.17       2.27                2.27   True
b'B              0.00              100.0         100.0        34.94      13.64               13.64   True
```
### S4
```
            mean_miss  pct_within_budget  pct_feasible  power_w_med  tok_s_med  tok_s_med_feasible  holds
controller                                                                                               
a                 0.0                0.0           0.0        87.95      64.91                 NaN  False
g'B               0.0              100.0         100.0        34.91      21.82               21.82   True
eB                0.0              100.0         100.0        34.91      21.82               21.82   True
c'B               0.0              100.0         100.0        33.59      12.67               12.67   True
d'B               0.0              100.0         100.0        26.09       8.02                8.02   True
d'B2              0.0              100.0         100.0        28.86      11.44               11.44   True
b'B               0.0              100.0         100.0        34.91      21.82               21.82   True
```
### S5
```
            mean_miss  pct_within_budget  pct_feasible  power_w_med  tok_s_med  tok_s_med_feasible  holds
controller                                                                                               
a                0.34                0.0           0.0        84.30      54.49                 NaN  False
g'B              0.00              100.0         100.0        34.74      21.82               21.82   True
eB               0.00              100.0         100.0        34.74      21.82               21.82   True
c'B              0.00              100.0         100.0        33.54      13.08               13.08   True
d'B              0.00              100.0         100.0        26.48       8.76                8.76   True
d'B2             0.00              100.0         100.0        29.39      11.71               11.71   True
b'B              0.00              100.0         100.0        34.74      21.82               21.82   True
```
### Paired comparisons on tok/s (median of A - B over seeds where BOTH are feasible; 90% bootstrap CI)

#### d'B2 minus c'B (tok/s)
```
           n  median     lo     hi
scenario                          
S0        30  -1.891 -1.891 -1.891
S1        30  -1.245 -1.273 -1.191
S1d        0     NaN    NaN    NaN
S2         0     NaN    NaN    NaN
S3        30  -0.873 -0.873 -0.855
S4        30  -1.245 -1.273 -1.191
S5        30  -1.391 -1.436 -1.327
```
#### d'B2 minus g'B (tok/s)
```
           n  median      lo      hi
scenario                            
S0        30   5.000   5.000   5.000
S1        30 -10.382 -10.409 -10.345
S1d       30  -4.118  -4.245  -4.036
S2         0     NaN     NaN     NaN
S3        30   2.273   2.273   2.273
S4        30 -10.382 -10.409 -10.345
S5        30 -10.109 -10.127 -10.091
```
#### d'B2 minus eB (tok/s)
```
           n  median      lo      hi
scenario                            
S0        30   5.000   5.000   5.000
S1        30 -10.382 -10.409 -10.345
S1d       30  -4.118  -4.236  -4.027
S2         0     NaN     NaN     NaN
S3        30   2.273   2.273   2.273
S4        30 -10.382 -10.409 -10.345
S5        30 -10.109 -10.127 -10.091
```
#### d'B2 minus b'B (tok/s)
```
           n  median      lo      hi
scenario                            
S0        30   3.445   3.400   3.491
S1        30 -10.382 -10.409 -10.345
S1d       30  -8.900  -8.973  -8.864
S2         0     NaN     NaN     NaN
S3        30 -11.364 -11.364 -11.364
S4        30 -10.382 -10.409 -10.345
S5        30 -10.109 -10.127 -10.091
```
#### d'B2 minus d'B (tok/s)
```
           n  median     lo     hi
scenario                          
S0        30   5.000  5.000  5.000
S1        30   3.427  3.400  3.464
S1d       30   3.527  3.464  3.655
S2         0     NaN    NaN    NaN
S3        30   2.273  2.273  2.273
S4        30   3.427  3.400  3.464
S5        30   2.945  2.927  2.964
```
#### c'B minus g'B (tok/s)
```
           n  median     lo     hi
scenario                          
S0        30   6.891  6.891  6.891
S1        30  -9.145 -9.182 -9.109
S1d        0     NaN    NaN    NaN
S2        30  -7.255 -7.255 -7.255
S3        30   3.145  3.127  3.145
S4        30  -9.145 -9.173 -9.109
S5        30  -8.736 -8.764 -8.691
```
## Pre-stated reading at 60 W (review finding 2): does d'B (v2) earn its place?

- comparator c'B: **DOES NOT EARN ITS PLACE**; S0: win=False loss=True; S1: win=True loss=False; S2: win=True loss=False; S5: win=True loss=False
- comparator best simple (g'B, eB): **DOES NOT EARN ITS PLACE**; S0: win=False loss=False; S1: win=True loss=False; S2: win=False loss=True; S5: win=True loss=False

Rule: win (CI above 0) in S1 OR S5 and no loss (CI below 0) in S0 or S2. S5 is the held-out-workload scene; the S1 win alone does not decide the question for the strict comparator.

## S5 oracle static settings (tuned on S5 tuning seeds; knows the workload)
```
{
 "60": {
  "action": {
   "clock": 2460.0,
   "pacing": "aligned",
   "duty": 0.6,
   "guard_ms": 0.5
  },
  "tok_s": 38.770909090909086,
  "power_max_seen": 59.651158814145525,
  "feasible": true
 },
 "35": {
  "action": {
   "clock": 1800,
   "pacing": "aligned",
   "duty": 0.6,
   "guard_ms": 0.5
  },
  "tok_s": 21.82,
  "power_max_seen": 34.74786904774668,
  "feasible": true
 }
}
```