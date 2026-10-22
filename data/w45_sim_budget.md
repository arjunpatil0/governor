# W4-5 simulator: POWER-BUDGET rerun of the frozen study (POST-HOC / SENSITIVITY; SIMULATION ONLY; frozen results unchanged)

Primary objective (decision 2026-10-22): maximise bg tok/s subject to fg SLO (miss <= 1%) AND mean GPU power <= budget; feasible run = both. Budgets 60 W and 35 W over the 55 s window. Evaluation seeds 200-229; statics tuned on tuning seeds 100-109; c', d' keep their frozen constants and only receive the budget.

Plant assumptions (unchanged): fg and bg effects separable: no joint (clock, duty) measurement exists; bg speed under contention follows the same time-slice share as the fg (L measured the bg alone); token-level pacing: a bg token is one indivisible ~10 ms job (A2 duty used 2 ms slices); 'unlocked' fg speed from W1 (2460 MHz) with no thermal throttling unless a scenario caps it; fg frame jitter (jitter_sigma) is a scenario parameter, not measured; idle power 5 W from a single pilot observation (journal 0011); bg token time is deterministic at the L median rate (no token-time jitter or CPU-side stalls), so the guard only has to absorb fg jitter

Caveat: the budget constrains MEAN power of the plant's time-weighted model (fg W1 fma power, bg L power, idle 5 W); real board power also has CPU-side/fan/idle terms not modelled.

## Budget 60 W

### S0
```
            mean_miss  pct_within_budget  pct_feasible  power_w_med  tok_s_med  tok_s_med_feasible  holds
controller                                                                                               
a                 0.0                0.0           0.0        87.33      54.49                 NaN  False
e                 0.0                0.0           0.0        79.63      60.00                 NaN  False
c'                0.0                0.0           0.0        79.63      60.00                 NaN  False
d'                0.0                0.0           0.0        79.63      60.00                 NaN  False
b'B               0.0              100.0         100.0        53.83      30.00               30.00   True
g'B               0.0              100.0         100.0        53.84      30.00               30.00   True
eB                0.0              100.0         100.0        53.84      30.00               30.00   True
c'B               0.0              100.0         100.0        58.12      34.98               34.98   True
d'B               0.0              100.0         100.0        53.83      30.00               30.00   True
```
### S1
```
            mean_miss  pct_within_budget  pct_feasible  power_w_med  tok_s_med  tok_s_med_feasible  holds
controller                                                                                               
a                0.34                0.0           0.0        87.33      54.50                 NaN  False
e                0.00                0.0           0.0        74.36      53.85                 NaN  False
c'               0.00              100.0         100.0        45.23      28.25               28.25   True
d'               0.00              100.0         100.0        48.59      34.21               34.21   True
b'B              0.00              100.0         100.0        54.98      31.34               31.34   True
g'B              0.00              100.0         100.0        54.98      31.34               31.34   True
eB               0.00              100.0         100.0        54.98      31.34               31.34   True
c'B              0.00              100.0         100.0        42.56      25.04               25.04   True
d'B              0.00              100.0         100.0        42.72      26.02               26.02   True
```
### S1d
```
            mean_miss  pct_within_budget  pct_feasible  power_w_med  tok_s_med  tok_s_med_feasible  holds
controller                                                                                               
a                0.04               0.00          0.00        87.22      53.33                 NaN  False
e                0.00               0.00          0.00        79.60      59.31                 NaN  False
c'               0.00               0.00          0.00        70.07      51.05                 NaN  False
d'               0.00               6.67          6.67        61.48      43.95               42.15  False
b'B              0.00             100.00        100.00        54.26      29.84               29.84   True
g'B              0.00             100.00        100.00        54.26      29.84               29.84   True
eB               0.00             100.00        100.00        54.26      29.84               29.84   True
c'B              0.00             100.00        100.00        56.66      35.42               35.42   True
d'B              0.00             100.00        100.00        48.70      27.45               27.45   True
```
### S2
```
            mean_miss  pct_within_budget  pct_feasible  power_w_med  tok_s_med  tok_s_med_feasible  holds
controller                                                                                               
a                 0.0                0.0           0.0        89.02      71.45                 NaN  False
e                 0.0                0.0           0.0        71.88      73.18                 NaN  False
c'                0.0                0.0           0.0        70.78      72.09                 NaN  False
d'                0.0                0.0           0.0        71.30      72.51                 NaN  False
b'B               0.0              100.0         100.0        51.90      37.49               37.49   True
g'B               0.0              100.0         100.0        51.90      37.49               37.49   True
eB                0.0              100.0         100.0        54.88      53.42               53.42   True
c'B               0.0              100.0         100.0        55.52      52.49               52.49   True
d'B               0.0              100.0         100.0        54.31      52.75               52.75   True
```
### S3
```
            mean_miss  pct_within_budget  pct_feasible  power_w_med  tok_s_med  tok_s_med_feasible  holds
controller                                                                                               
a                0.55                0.0           0.0        64.08      45.98                 NaN  False
e                0.00              100.0         100.0        46.67      27.27               27.27   True
c'               0.00              100.0         100.0        46.67      27.27               27.27   True
d'               0.00              100.0         100.0        46.67      27.27               27.27   True
b'B              0.00              100.0         100.0        46.67      27.27               27.27   True
g'B              0.00              100.0         100.0        34.94      13.64               13.64   True
eB               0.00              100.0         100.0        34.94      13.64               13.64   True
c'B              0.00              100.0         100.0        36.85      15.85               15.85   True
d'B              0.00              100.0         100.0        34.94      13.64               13.64   True
```
### S4
```
            mean_miss  pct_within_budget  pct_feasible  power_w_med  tok_s_med  tok_s_med_feasible  holds
controller                                                                                               
a                 0.0                0.0           0.0        87.96      64.91                 NaN  False
e                 0.0                0.0           0.0        74.36      53.85                 NaN  False
c'                0.0              100.0         100.0        45.23      28.25               28.25   True
d'                0.0              100.0         100.0        48.59      34.21               34.21   True
b'B               0.0              100.0         100.0        54.98      31.34               31.34   True
g'B               0.0              100.0         100.0        54.98      31.34               31.34   True
eB                0.0              100.0         100.0        54.98      31.34               31.34   True
c'B               0.0              100.0         100.0        42.56      25.04               25.04   True
d'B               0.0              100.0         100.0        42.72      26.02               26.02   True
```
### Paired comparisons on tok/s (median of A - B over seeds where BOTH runs are feasible; 90% bootstrap CI)

#### d'B minus c'B (tok/s)
```
           n  median     lo     hi
scenario                          
S0        30  -4.982 -5.000 -4.982
S1        30   0.964  0.891  1.064
S1d       30  -8.109 -8.382 -7.836
S2        30   0.255  0.236  0.255
S3        30  -2.218 -2.227 -2.200
S4        30   0.964  0.891  1.073
```
#### d'B minus g'B (tok/s)
```
           n  median      lo      hi
scenario                            
S0        30   0.000   0.000   0.000
S1        30  -5.273  -5.345  -5.227
S1d       30  -2.391  -2.582  -2.236
S2        30  15.255  15.236  15.255
S3        30   0.000   0.000   0.000
S4        30  -5.273  -5.345  -5.227
```
#### c'B minus g'B (tok/s)
```
           n  median      lo      hi
scenario                            
S0        30   4.982   4.982   5.000
S1        30  -6.327  -6.373  -6.109
S1d       30   5.573   5.491   5.618
S2        30  15.000  15.000  15.000
S3        30   2.218   2.200   2.227
S4        30  -6.327  -6.373  -6.109
```
#### d'B minus eB (tok/s)
```
           n  median     lo     hi
scenario                          
S0        30   0.000  0.000  0.000
S1        30  -5.273 -5.345 -5.227
S1d       30  -2.391 -2.582 -2.236
S2        30  -0.673 -0.691 -0.673
S3        30   0.000  0.000  0.000
S4        30  -5.273 -5.345 -5.227
```
#### eB minus g'B (tok/s)
```
           n  median      lo      hi
scenario                            
S0        30   0.000   0.000   0.000
S1        30   0.000   0.000   0.000
S1d       30   0.000   0.000   0.000
S2        30  15.927  15.927  15.927
S3        30   0.000   0.000   0.000
S4        30   0.000   0.000   0.000
```
#### g'B minus b'B (tok/s)
```
           n  median      lo      hi
scenario                            
S0        30   0.000   0.000   0.000
S1        30   0.000   0.000   0.000
S1d       30   0.000   0.000   0.000
S2        30   0.000   0.000   0.000
S3        30 -13.636 -13.636 -13.636
S4        30   0.000   0.000   0.000
```
## Budget 35 W

### S0
```
            mean_miss  pct_within_budget  pct_feasible  power_w_med  tok_s_med  tok_s_med_feasible  holds
controller                                                                                               
a                 0.0                0.0           0.0        87.33      54.49                 NaN  False
e                 0.0                0.0           0.0        79.63      60.00                 NaN  False
c'                0.0                0.0           0.0        79.63      60.00                 NaN  False
d'                0.0                0.0           0.0        79.63      60.00                 NaN  False
b'B               0.0              100.0         100.0        22.55       1.56                1.56   True
g'B               0.0              100.0         100.0        21.60       0.00                0.00   True
eB                0.0              100.0         100.0        21.60       0.00                0.00   True
c'B               0.0              100.0         100.0        33.96       6.89                6.89   True
d'B               0.0              100.0         100.0        18.36       0.00                0.00   True
```
### S1
```
            mean_miss  pct_within_budget  pct_feasible  power_w_med  tok_s_med  tok_s_med_feasible  holds
controller                                                                                               
a                0.34                0.0           0.0        87.33      54.50                 NaN  False
e                0.00                0.0           0.0        74.36      53.85                 NaN  False
c'               0.00                0.0           0.0        45.23      28.25                 NaN  False
d'               0.00                0.0           0.0        48.59      34.21                 NaN  False
b'B              0.00              100.0         100.0        34.91      21.82               21.82   True
g'B              0.00              100.0         100.0        34.91      21.82               21.82   True
eB               0.00              100.0         100.0        34.91      21.82               21.82   True
c'B              0.00              100.0         100.0        33.60      12.70               12.70   True
d'B              0.00              100.0         100.0        26.09       8.00                8.00   True
```
### S1d
```
            mean_miss  pct_within_budget  pct_feasible  power_w_med  tok_s_med  tok_s_med_feasible  holds
controller                                                                                               
a                0.04                0.0           0.0        87.22      53.33                 NaN  False
e                0.00                0.0           0.0        79.60      59.31                 NaN  False
c'               0.00                0.0           0.0        70.07      51.05                 NaN  False
d'               0.00                0.0           0.0        61.48      43.95                 NaN  False
b'B              0.00              100.0         100.0        33.02      18.05               18.05   True
g'B              0.00              100.0         100.0        30.15      13.34               13.34   True
eB               0.00              100.0         100.0        30.15      13.34               13.34   True
c'B              0.00                0.0           0.0        36.13      10.71                 NaN  False
d'B              0.00              100.0         100.0        26.03       5.66                5.66   True
```
### S2
```
            mean_miss  pct_within_budget  pct_feasible  power_w_med  tok_s_med  tok_s_med_feasible  holds
controller                                                                                               
a                 0.0                0.0           0.0        89.02      71.45                 NaN  False
e                 0.0                0.0           0.0        71.88      73.18                 NaN  False
c'                0.0                0.0           0.0        70.78      72.09                 NaN  False
d'                0.0                0.0           0.0        71.30      72.51                 NaN  False
b'B               0.0              100.0         100.0        32.70      35.38               35.38   True
g'B               0.0              100.0         100.0        33.20      28.91               28.91   True
eB                0.0              100.0         100.0        34.31      35.09               35.09   True
c'B               0.0              100.0         100.0        32.92      21.65               21.65   True
d'B               0.0              100.0         100.0        31.53      33.67               33.67   True
```
### S3
```
            mean_miss  pct_within_budget  pct_feasible  power_w_med  tok_s_med  tok_s_med_feasible  holds
controller                                                                                               
a                0.55                0.0           0.0        64.08      45.98                 NaN  False
e                0.00                0.0           0.0        46.67      27.27                 NaN  False
c'               0.00                0.0           0.0        46.67      27.27                 NaN  False
d'               0.00                0.0           0.0        46.67      27.27                 NaN  False
b'B              0.00              100.0         100.0        34.94      13.64               13.64   True
g'B              0.00              100.0         100.0        20.28       0.00                0.00   True
eB               0.00              100.0         100.0        20.28       0.00                0.00   True
c'B              0.00              100.0         100.0        25.91       3.15                3.15   True
d'B              0.00              100.0         100.0        18.36       0.00                0.00   True
```
### S4
```
            mean_miss  pct_within_budget  pct_feasible  power_w_med  tok_s_med  tok_s_med_feasible  holds
controller                                                                                               
a                 0.0                0.0           0.0        87.96      64.91                 NaN  False
e                 0.0                0.0           0.0        74.36      53.85                 NaN  False
c'                0.0                0.0           0.0        45.23      28.25                 NaN  False
d'                0.0                0.0           0.0        48.59      34.21                 NaN  False
b'B               0.0              100.0         100.0        34.91      21.82               21.82   True
g'B               0.0              100.0         100.0        34.91      21.82               21.82   True
eB                0.0              100.0         100.0        34.91      21.82               21.82   True
c'B               0.0              100.0         100.0        33.60      12.70               12.70   True
d'B               0.0              100.0         100.0        26.09       8.00                8.00   True
```
### Paired comparisons on tok/s (median of A - B over seeds where BOTH runs are feasible; 90% bootstrap CI)

#### d'B minus c'B (tok/s)
```
           n  median      lo      hi
scenario                            
S0        30  -6.891  -6.909  -6.891
S1        30  -4.691  -4.745  -4.618
S1d        0     NaN     NaN     NaN
S2        30  12.018  12.000  12.018
S3        30  -3.145  -3.145  -3.136
S4        30  -4.691  -4.745  -4.618
```
#### d'B minus g'B (tok/s)
```
           n  median      lo      hi
scenario                            
S0        30   0.000   0.000   0.000
S1        30 -13.818 -13.818 -13.800
S1d       30  -7.636  -7.700  -7.545
S2        30   4.764   4.764   4.764
S3        30   0.000   0.000   0.000
S4        30 -13.818 -13.818 -13.800
```
#### c'B minus g'B (tok/s)
```
           n  median     lo     hi
scenario                          
S0        30   6.891  6.891  6.909
S1        30  -9.118 -9.164 -9.091
S1d        0     NaN    NaN    NaN
S2        30  -7.255 -7.255 -7.236
S3        30   3.145  3.145  3.145
S4        30  -9.118 -9.173 -9.091
```
#### d'B minus eB (tok/s)
```
           n  median      lo      hi
scenario                            
S0        30   0.000   0.000   0.000
S1        30 -13.818 -13.818 -13.800
S1d       30  -7.636  -7.700  -7.545
S2        30  -1.418  -1.418  -1.418
S3        30   0.000   0.000   0.000
S4        30 -13.818 -13.818 -13.800
```
#### eB minus g'B (tok/s)
```
           n  median     lo     hi
scenario                          
S0        30   0.000  0.000  0.000
S1        30   0.000  0.000  0.000
S1d       30   0.000  0.000  0.000
S2        30   6.182  6.182  6.182
S3        30   0.000  0.000  0.000
S4        30   0.000  0.000  0.000
```
#### g'B minus b'B (tok/s)
```
           n  median      lo      hi
scenario                            
S0        30  -1.564  -1.709  -1.509
S1        30   0.000   0.000   0.000
S1d       30  -4.764  -4.791  -4.700
S2        30  -6.473  -6.473  -6.473
S3        30 -13.636 -13.636 -13.636
S4        30   0.000   0.000   0.000
```
## Budget-tuned static settings (tuning seeds)

```
{
 "60": {
  "static": {
   "S0": {
    "clock": 2460.0,
    "pacing": "aligned",
    "duty": 0.3,
    "guard_ms": 0.0
   },
   "S1": {
    "clock": 2460.0,
    "pacing": "aligned",
    "duty": 0.5,
    "guard_ms": 0.0
   },
   "S1d": {
    "clock": 2460.0,
    "pacing": "aligned",
    "duty": 0.5,
    "guard_ms": 0.0
   },
   "S2": {
    "clock": 2460.0,
    "pacing": "aligned",
    "duty": 0.5,
    "guard_ms": 0.0
   },
   "S3": {
    "clock": 2460.0,
    "pacing": "aligned",
    "duty": 0.6,
    "guard_ms": 0.0
   },
   "S4": {
    "clock": 2460.0,
    "pacing": "aligned",
    "duty": 0.5,
    "guard_ms": 0.0
   }
  },
  "tuning": {
   "S0": {
    "tok_s": 30.0,
    "power_w": 53.826284852340336,
    "power_max_seen": 53.8451103827357,
    "miss_max_seen": 0.0,
    "feasible": true
   },
   "S1": {
    "tok_s": 31.352727272727275,
    "power_w": 54.99954304180386,
    "power_max_seen": 55.288152142336095,
    "miss_max_seen": 0.0,
    "feasible": true
   },
   "S1d": {
    "tok_s": 29.807272727272725,
    "power_w": 54.243456900134426,
    "power_max_seen": 54.298536385099844,
    "miss_max_seen": 0.0,
    "feasible": true
   },
   "S2": {
    "tok_s": 37.49090909090909,
    "power_w": 51.89784473754189,
    "power_max_seen": 51.90912787933853,
    "miss_max_seen": 0.0,
    "feasible": true
   },
   "S3": {
    "tok_s": 27.272727272727273,
    "power_w": 46.6666990776403,
    "power_max_seen": 46.68242426341618,
    "miss_max_seen": 0.0,
    "feasible": true
   },
   "S4": {
    "tok_s": 31.352727272727275,
    "power_w": 54.99954304180386,
    "power_max_seen": 55.288152142336095,
    "miss_max_seen": 0.0,
    "feasible": true
   },
   "GLOBAL": {
    "tok_s": 28.939999999999998,
    "power_w": 50.81981747376974,
    "power_max_seen": 55.288152142336095,
    "miss_max_seen": 0.0,
    "feasible": true
   }
  },
  "global": {
   "clock": 2460.0,
   "pacing": "aligned",
   "duty": 0.5,
   "guard_ms": 0.0
  }
 },
 "35": {
  "static": {
   "S0": {
    "clock": 1800,
    "pacing": "aligned",
    "duty": 0.7,
    "guard_ms": 0.0
   },
   "S1": {
    "clock": 1800,
    "pacing": "aligned",
    "duty": 0.7,
    "guard_ms": 0.5
   },
   "S1d": {
    "clock": 1800,
    "pacing": "aligned",
    "duty": 0.6,
    "guard_ms": 0.0
   },
   "S2": {
    "clock": 1500,
    "pacing": "aligned",
    "duty": 1.0,
    "guard_ms": 0.0
   },
   "S3": {
    "clock": 2460.0,
    "pacing": "aligned",
    "duty": 0.3,
    "guard_ms": 0.0
   },
   "S4": {
    "clock": 1800,
    "pacing": "aligned",
    "duty": 0.7,
    "guard_ms": 0.5
   }
  },
  "tuning": {
   "S0": {
    "tok_s": 1.6381818181818182,
    "power_w": 22.5981937824859,
    "power_max_seen": 22.776051278161507,
    "miss_max_seen": 0.0,
    "feasible": true
   },
   "S1": {
    "tok_s": 21.818181818181817,
    "power_w": 34.90622326763862,
    "power_max_seen": 34.92116897258264,
    "miss_max_seen": 0.0,
    "feasible": true
   },
   "S1d": {
    "tok_s": 18.08727272727273,
    "power_w": 33.04317314551032,
    "power_max_seen": 33.14197484833261,
    "miss_max_seen": 0.0,
    "feasible": true
   },
   "S2": {
    "tok_s": 35.38181818181818,
    "power_w": 32.69364822439365,
    "power_max_seen": 32.70092897219404,
    "miss_max_seen": 0.0,
    "feasible": true
   },
   "S3": {
    "tok_s": 13.636363636363637,
    "power_w": 34.938836396439676,
    "power_max_seen": 34.95456158221534,
    "miss_max_seen": 0.0,
    "feasible": true
   },
   "S4": {
    "tok_s": 21.818181818181817,
    "power_w": 34.90622326763862,
    "power_max_seen": 34.92116897258264,
    "miss_max_seen": 0.0,
    "feasible": true
   },
   "GLOBAL": {
    "tok_s": 14.311515151515152,
    "power_w": 29.172558255965072,
    "power_max_seen": 34.921168972582635,
    "miss_max_seen": 0.0,
    "feasible": true
   }
  },
  "global": {
   "clock": 1800,
   "pacing": "aligned",
   "duty": 0.8,
   "guard_ms": 0.5
  }
 }
}
```