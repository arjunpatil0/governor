# W4-5 simulator, ROUND 3 (LAST simulator round; POST-HOC; SIMULATION ONLY; rounds 0-2 unchanged)

d'B v3 constants chosen on tuning seeds 100-109 over S0-S4 at both budgets (10 of 32 parameter sets hold SLO and budget in every cell); evaluation on NEW seeds 400-429. g'B, eB, c'B, b'B and the S5 oracle keep their earlier constants; d'B2 = the round-2 controller with its round-2 constants. The plant is unchanged except for the overrun observation.

Chosen d'B v3 constants:
```
{
 "safety": 0.8,
 "switch_gain": 0.5,
 "clock_every": 10,
 "guard_k": 3.0,
 "sigma_w": 0.0,
 "guard_floor": 0.0,
 "power_gain": 0.03
}
```

## Budget 60 W

### S0
```
            mean_miss  pct_feasible  power_w_med  tok_s_med  holds
controller                                                        
a                 0.0           0.0        87.33      54.49  False
g'B               0.0         100.0        53.84      30.00   True
eB                0.0         100.0        53.84      30.00   True
c'B               0.0         100.0        58.12      34.98   True
d'B2              0.0         100.0        53.83      30.00   True
d'B3              0.0         100.0        57.20      33.93   True
b'B               0.0         100.0        53.83      30.00   True
```
### S1
```
            mean_miss  pct_feasible  power_w_med  tok_s_med  holds
controller                                                        
a                0.34           0.0        87.33      54.51  False
g'B              0.00         100.0        54.92      31.25   True
eB               0.00         100.0        54.92      31.25   True
c'B              0.00         100.0        42.53      25.00   True
d'B2             0.00         100.0        51.73      36.35   True
d'B3             0.00         100.0        52.55      38.28   True
b'B              0.00         100.0        54.92      31.25   True
```
### S1d
```
            mean_miss  pct_feasible  power_w_med  tok_s_med  holds
controller                                                        
a                0.04           0.0        87.22      53.33  False
g'B              0.00         100.0        54.26      29.84   True
eB               0.00         100.0        54.26      29.84   True
c'B              0.00         100.0        56.37      37.09   True
d'B2             0.00         100.0        53.69      37.29   True
d'B3             0.00         100.0        54.96      38.94   True
b'B              0.00         100.0        54.26      29.84   True
```
### S2
```
            mean_miss  pct_feasible  power_w_med  tok_s_med  holds
controller                                                        
a                 0.0           0.0        89.02      71.45  False
g'B               0.0         100.0        51.90      37.49   True
eB                0.0         100.0        54.87      53.42   True
c'B               0.0         100.0        55.52      52.49   True
d'B2              0.0         100.0        54.53      53.00   True
d'B3              0.0         100.0        46.84      38.78   True
b'B               0.0         100.0        51.90      37.49   True
```
### S3
```
            mean_miss  pct_feasible  power_w_med  tok_s_med  holds
controller                                                        
a                0.55           0.0        64.08      45.99  False
g'B              0.00         100.0        34.94      13.64   True
eB               0.00         100.0        34.94      13.64   True
c'B              0.00         100.0        36.84      15.85   True
d'B2             0.00         100.0        34.94      13.64   True
d'B3             0.00         100.0        35.92      14.78   True
b'B              0.00         100.0        46.67      27.27   True
```
### S4
```
            mean_miss  pct_feasible  power_w_med  tok_s_med  holds
controller                                                        
a                 0.0           0.0        87.96      64.93  False
g'B               0.0         100.0        54.92      31.25   True
eB                0.0         100.0        54.92      31.25   True
c'B               0.0         100.0        42.53      25.00   True
d'B2              0.0         100.0        51.73      36.35   True
d'B3              0.0         100.0        52.55      38.28   True
b'B               0.0         100.0        54.92      31.25   True
```
### S5
```
            mean_miss  pct_feasible  power_w_med  tok_s_med  holds
controller                                                        
a                0.34           0.0        84.30      54.51  False
g'B              0.00         100.0        53.40      31.25   True
eB               0.00         100.0        53.40      31.25   True
c'B              0.00         100.0        42.45      25.92   True
d'B2             0.00         100.0        50.57      36.14   True
d'B3             0.00         100.0        50.66      36.49   True
b'B              0.00         100.0        59.44      38.72   True
```
### Paired tok/s difference, d'B3 minus comparator (median, 90% CI; seeds where both feasible)

#### d'B3 minus c'B
```
           n  median      lo      hi
scenario                            
S0        30  -1.073  -1.073  -1.055
S1        30  13.236  13.036  13.327
S1d       30   1.864   0.182   3.464
S2        30 -13.709 -13.764 -13.673
S3        30  -1.073  -1.073  -1.055
S4        30  13.236  13.036  13.327
S5        30  10.636  10.055  10.809
```
#### d'B3 minus g'B
```
           n  median     lo     hi
scenario                          
S0        30   3.927  3.909  3.927
S1        30   7.027  6.954  7.055
S1d       30   9.109  9.055  9.200
S2        30   1.291  1.255  1.355
S3        30   1.145  1.145  1.145
S4        30   7.027  6.955  7.055
S5        30   5.145  4.909  5.600
```
#### d'B3 minus eB
```
           n  median      lo      hi
scenario                            
S0        30   3.927   3.909   3.927
S1        30   7.027   6.945   7.055
S1d       30   9.109   9.055   9.200
S2        30 -14.636 -14.673 -14.564
S3        30   1.145   1.145   1.145
S4        30   7.027   6.945   7.055
S5        30   5.145   4.936   5.600
```
#### d'B3 minus d'B2
```
           n  median      lo      hi
scenario                            
S0        30   3.927   3.909   3.927
S1        30   1.945   1.873   1.973
S1d       30   1.618   1.591   1.655
S2        30 -14.227 -14.255 -14.164
S3        30   1.145   1.145   1.145
S4        30   1.936   1.882   1.964
S5        30   0.336  -0.018   0.836
```
#### d'B3 minus b'B
```
           n  median      lo      hi
scenario                            
S0        30   3.927   3.909   3.927
S1        30   7.027   6.955   7.055
S1d       30   9.109   9.055   9.200
S2        30   1.291   1.255   1.355
S3        30 -12.491 -12.491 -12.491
S4        30   7.027   6.945   7.055
S5        30  -2.255  -2.618  -1.964
```
## Budget 35 W

### S0
```
            mean_miss  pct_feasible  power_w_med  tok_s_med  holds
controller                                                        
a                 0.0           0.0        87.33      54.49  False
g'B               0.0         100.0        21.60       0.00   True
eB                0.0         100.0        21.60       0.00   True
c'B               0.0         100.0        33.96       6.89   True
d'B2              0.0         100.0        32.33       5.00   True
d'B3              0.0         100.0        33.95       6.89   True
b'B               0.0         100.0        22.61       1.65   True
```
### S1
```
            mean_miss  pct_feasible  power_w_med  tok_s_med  holds
controller                                                        
a                0.34           0.0        87.33      54.51  False
g'B              0.00         100.0        34.91      21.82   True
eB               0.00         100.0        34.91      21.82   True
c'B              0.00         100.0        33.61      12.69   True
d'B2             0.00         100.0        28.85      11.40   True
d'B3             0.00         100.0        27.00      11.45   True
b'B              0.00         100.0        34.91      21.82   True
```
### S1d
```
            mean_miss  pct_feasible  power_w_med  tok_s_med  holds
controller                                                        
a                0.04           0.0        87.22      53.33  False
g'B              0.00         100.0        30.20      13.43   True
eB               0.00         100.0        30.20      13.43   True
c'B              0.00           0.0        36.44      12.61  False
d'B2             0.00         100.0        30.56       9.34   True
d'B3             0.00         100.0        26.42       8.92   True
b'B              0.00         100.0        33.08      18.15   True
```
### S2
```
            mean_miss  pct_feasible  power_w_med  tok_s_med  holds
controller                                                        
a                 0.0          0.00        89.02      71.45  False
g'B               0.0        100.00        33.20      28.91   True
eB                0.0        100.00        34.31      35.09   True
c'B               0.0        100.00        32.92      21.67   True
d'B2              0.0          0.00        40.71      36.94  False
d'B3              0.0         96.67        32.38      26.57   True
b'B               0.0        100.00        32.69      35.38   True
```
### S3
```
            mean_miss  pct_feasible  power_w_med  tok_s_med  holds
controller                                                        
a                0.55           0.0        64.08      45.99  False
g'B              0.00         100.0        20.29       0.00   True
eB               0.00         100.0        20.29       0.00   True
c'B              0.00         100.0        25.91       3.15   True
d'B2             0.00         100.0        25.17       2.27   True
d'B3             0.00         100.0        25.90       3.13   True
b'B              0.00         100.0        34.94      13.64   True
```
### S4
```
            mean_miss  pct_feasible  power_w_med  tok_s_med  holds
controller                                                        
a                 0.0           0.0        87.96      64.93  False
g'B               0.0         100.0        34.91      21.82   True
eB                0.0         100.0        34.91      21.82   True
c'B               0.0         100.0        33.61      12.69   True
d'B2              0.0         100.0        28.85      11.40   True
d'B3              0.0         100.0        27.00      11.45   True
b'B               0.0         100.0        34.91      21.82   True
```
### S5
```
            mean_miss  pct_feasible  power_w_med  tok_s_med  holds
controller                                                        
a                0.34           0.0        84.30      54.51  False
g'B              0.00         100.0        34.73      21.82   True
eB               0.00         100.0        34.73      21.82   True
c'B              0.00         100.0        33.55      13.12   True
d'B2             0.00         100.0        29.37      11.70   True
d'B3             0.00         100.0        28.25      12.19   True
b'B              0.00         100.0        34.73      21.82   True
```
### Paired tok/s difference, d'B3 minus comparator (median, 90% CI; seeds where both feasible)

#### d'B3 minus c'B
```
           n  median     lo     hi
scenario                          
S0        30  -0.018 -0.018 -0.009
S1        30  -1.282 -1.400 -1.236
S1d        0     NaN    NaN    NaN
S2        29   4.382  3.236  6.691
S3        30  -0.018 -0.018 -0.018
S4        30  -1.282 -1.391 -1.236
S5        30  -0.918 -1.000 -0.673
```
#### d'B3 minus g'B
```
           n  median      lo      hi
scenario                            
S0        30   6.891   6.891   6.891
S1        30 -10.364 -10.509 -10.300
S1d       30  -4.491  -4.874  -4.127
S2        29  -2.891  -4.018  -0.545
S3        30   3.127   3.127   3.127
S4        30 -10.364 -10.509 -10.291
S5        30  -9.627  -9.709  -9.309
```
#### d'B3 minus eB
```
           n  median      lo      hi
scenario                            
S0        30   6.891   6.891   6.891
S1        30 -10.364 -10.509 -10.300
S1d       30  -4.491  -4.891  -4.091
S2        29  -9.073 -10.200  -6.727
S3        30   3.127   3.127   3.127
S4        30 -10.364 -10.509 -10.300
S5        30  -9.627  -9.718  -9.382
```
#### d'B3 minus d'B2
```
           n  median     lo     hi
scenario                          
S0        30   1.891  1.891  1.891
S1        30   0.009 -0.191  0.118
S1d       30  -0.400 -0.636  0.155
S2         0     NaN    NaN    NaN
S3        30   0.855  0.855  0.855
S4        30   0.009 -0.236  0.118
S5        30   0.500  0.418  0.755
```
#### d'B3 minus b'B
```
           n  median      lo      hi
scenario                            
S0        30   5.355   5.218   5.418
S1        30 -10.364 -10.509 -10.300
S1d       30  -9.155  -9.501  -8.845
S2        29  -9.364 -10.491  -7.018
S3        30 -10.509 -10.509 -10.509
S4        30 -10.364 -10.509 -10.300
S5        30  -9.627  -9.718  -9.391
```
## Pre-registered reading at 60 W (reviewer 2026-10-22)

- S0: best comparator c'B; ratio d'B3/c'B median 0.969, 90% CI [0.969, 0.970] (non-inferior if lower bound >= 0.95)
- S2: best comparator eB; ratio d'B3/eB median 0.726, 90% CI [0.725, 0.727] (non-inferior if lower bound >= 0.95)
- S5 vs c'B: median diff 10.64 tok/s, 90% CI [10.11, 10.81]
- S5 vs g'B: median diff 5.15 tok/s, 90% CI [4.91, 5.56]
- S5 vs eB: median diff 5.15 tok/s, 90% CI [4.93, 5.60]

**d'B3 DOES NOT EARN ITS PLACE** under the reading: S5 win against all three comparators AND non-inferior (>= 0.95) in S0 and S2. Simulation only; the plant's token timing is known to be wrong (smoke), so this is not evidence about hardware.