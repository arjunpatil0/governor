# Experiment G report (SMOKE: not a result)

Source `data\raw\w2_G_smoke\20261022T052531Z` | admin False | AC True | ambient 25.0 C | Armoury Performance | NVIDIA GeForce RTX 4070 Laptop GPU driver 616.92 | yaml e1df18ccd6898bd9 | dll 7768289069367275 | git 5fb7204f | blocks 1 | cells 15
Addenda: experiments/w2_colocation_addendum_globaltimer_2026-10-22.md and ..._prerun_2026-10-22.md (and _witness_ if registered). Each prediction: held / did not hold, with the numbers.
Block set for gap, run, overlap and preemption analyses: ALL blocks (secondary view; blocks beyond three per SM show intra-SM arbitration gaps even with no other context).

## Pre-check (iii): instrumentation overhead (registered acceptance; if it fails the timeline is NOT interpreted)

```
 block  base_on_p50  base_off_p50  wait_on  wait_off  slice_on_ms  slice_off_ms  gpu_on_ms  gpu_off_ms
     0       0.1684        0.1796  -0.1568   -0.2221       2.1582        2.1153     0.1065      0.1055
```

- median fg-alone latency, instrumented vs not: relative difference 6.2% (limit 5%)
- observed wait of R_2, instrumented -0.1568 ms vs uninstrumented -0.2221 ms: difference 0.0652 ms (limit 0.03)
- bg mean slice 2.1582 vs 2.1153 ms; fg gpu p50 0.1065 vs 0.1055 ms
- **pre-check (iii): FAIL: do not interpret the timeline (P4-P8); report the failure**

## P1-P3 on the uninstrumented R_m_off cells (fresh seeds; the block baseline is g_baseline_off)

### P1: cell-median observed wait within +/-0.03 ms of A

```
 m_ms  n_blocks  obs_wait_ms  a_wait_ms  diff_ms  within_tol
  0.5         1      -0.2922      0.226  -0.5182       False
  1.0         1      -0.1348      0.255  -0.3898       False
  2.0         1      -0.2221      0.287  -0.5091       False
  8.0         1      -0.2247      0.298  -0.5227       False
```

- P1 DID NOT HOLD

### P2: capped-wait fit on the observed slice-end axis (n = 8007 requests, all four m pooled)

- tau = 0.280 ms, 90% block-bootstrap CI [0.280, 0.280], offset -0.473 ms; registered range 0.22-0.31 ms (A: 0.260)
- P2 HELD

### P3: ripple on the unstretched axis (binned means, A's bins)

```
  lo   hi   n  mean_wait_ms
0.00 0.05 358       -0.4225
0.05 0.10 358       -0.3834
0.10 0.15 332       -0.3679
0.15 0.20 328       -0.3408
0.20 0.25 335       -0.3247
0.25 0.30 344       -0.2798
0.30 0.35 351       -0.2380
0.35 0.40 345       -0.2001
0.40 0.45 342       -0.1837
0.45 0.50 339       -0.1592
0.50 0.55 176       -0.1702
0.55 0.60 165       -0.1530
0.60 0.65 146       -0.2959
0.65 0.70 132       -0.2923
0.70 0.75 142       -0.2374
0.75 0.80 142       -0.2134
0.80 0.85 128       -0.2404
0.85 0.90 150       -0.2260
0.90 0.95 146       -0.1537
0.95 1.00 169       -0.0918
1.00 1.50 586       -0.2100
1.50 2.00 630       -0.2033
2.00 2.50 132       -0.2271
2.50 3.00 133       -0.2179
3.00 3.50 121       -0.2134
3.50 4.00 127       -0.2348
4.00 4.50 104       -0.1953
4.50 5.00 120       -0.2063
5.00 5.50 116       -0.2290
5.50 6.00 113       -0.1813
6.00 6.50 129       -0.2039
6.50 7.00 116       -0.1923
7.00 7.50 141       -0.2275
7.50 8.00  92       -0.1966
```

- local minimum 0.35-0.40: False (drop -0.038 ms below the preceding maximum); local minimum 0.80-0.85: True (drop 0.087 ms); required drop >= 0.04 ms (A: 0.300->0.214, 0.364->0.232)
- P3 DID NOT HOLD

## Timeline cells: coverage, trust and results per block (recorded-interval rule, addendum 2 section C)

Coverage and trust (fg_share = share of the cell's measured fg requests wholly inside the recorded interval; untrusted = blocks with gap-log overflow; gap_lost = gaps lost to a full global list):

```
 block   cell  n_fg_in_interval  n_bg_launches  interval_s  fg_share  bg_launches_dropped  n_untrusted_fg  n_untrusted_bg  gap_lost
     0   g_R8              2000           1277      10.669     1.000                    0               0               0         0
     0   g_T1               998           4626      11.042     1.000                    0               0               0         0
     0 g_R0.5               763           7407       3.966     0.382                13582               0               0         0
     0   g_R1              1614           7407       8.019     0.816                 2585               0               0         0
     0   g_R2              1984           5050      10.896     0.999                    0               0               0         0
     0   g_T4               400           4174      11.059     0.995                    0               0               0         0
```

Per block results:

```
 block   cell  alone_span_ms  n_sliced  q_pooled_ms  q_fg_ms  q_bg_ms   s_ms  n_neg_s  n_overlap  n_overlap_same_sm  n_overlap_diff_sm  n_ties  n_fg_blocks  g_thr_us  preempt_frac  preempt_frac_with_fg  p8_delay_p99_ms
     0   g_R8         0.0993         0          NaN      NaN      NaN    NaN        0          0                  0                  0       0       432000   41.8938        0.7120                0.5425           0.9340
     0   g_T1         1.2124       998        0.385    0.385    0.386 0.1004      114      11755               1883              11687       6       215568   41.8938        0.5652                0.1565           4.6171
     0 g_R0.5         0.0993         0          NaN      NaN      NaN    NaN        0          0                  0                  0       0       164808   41.8938        0.5000                0.0259           0.6550
     0   g_R1         0.0993         0          NaN      NaN      NaN    NaN        0          0                  0                  0       0       348624   41.8938        0.5131                0.0780           0.8734
     0   g_R2         0.0993         0          NaN      NaN      NaN    NaN        0       2592                354               2574       0       428544   41.8938        0.5519                0.1644           1.0076
     0   g_T4         4.9213       400        0.384    0.385    0.383 0.1024      194      13928               2871              13876     384        86400   41.8938        0.5956                0.1949          18.1082
```

### P4 quantum q (pooled complete runs of both contexts inside sliced fg spans) (pre-check (iii) FAILED: shown for completeness, NOT interpreted)

```
  cell  n_runs  q_pooled_ms  q_fg_ms  q_bg_ms  n_s   s_ms
g_R0.5       0          NaN      NaN      NaN    0    NaN
  g_R1       0          NaN      NaN      NaN    0    NaN
  g_R2       0          NaN      NaN      NaN    0    NaN
  g_R8       0          NaN      NaN      NaN    0    NaN
  g_T1    2182        0.385    0.385    0.386 3707 0.1004
  g_T4    6048        0.384    0.385    0.383 7392 0.1024
```

- pooled over all cells: q = 0.385 ms from 8230 complete runs; registered range 0.5-0.9 ms; P4 DID NOT HOLD

### P5 switch gap s (pre-check (iii) FAILED: shown for completeness, NOT interpreted)

- pooled s = 0.101 ms from 11099 transitions; registered range 0.2-0.3 ms; P5 DID NOT HOLD; negative-s transitions (runs overlapping in time): 308

### P6 no concurrency (pre-check (iii) FAILED: shown for completeness, NOT interpreted)

```
  cell  n_overlap  n_overlap_same_sm  n_overlap_diff_sm  n_ties  n_fg_blocks  n_untrusted_fg
g_R0.5          0                  0                  0       0       164808               0
  g_R1          0                  0                  0       0       348624               0
  g_R2       2592                354               2574       0       428544               0
  g_R8          0                  0                  0       0       432000               0
  g_T1      11755               1883              11687       6       215568               0
  g_T4      13928               2871              13876     384        86400               0
```

- fg blocks overlapping a bg block by more than 10 us: 28275 of 1675944 trusted blocks (untrusted excluded: 0); ties (<= 10 us): 390; P6 DID NOT HOLD

### P7 mid-kernel preemption of bg blocks (block has a gap >= G_thr; mean over blocks) (pre-check (iii) FAILED: shown for completeness, NOT interpreted)

```
  cell  preempt_frac  preempt_frac_with_fg
g_R0.5        0.5000                0.0259
  g_R1        0.5131                0.0780
  g_R2        0.5519                0.1644
  g_R8        0.7120                0.5425
  g_T1        0.5652                0.1565
  g_T4        0.5956                0.1949
```

- g_T4: 59.56% of recorded bg blocks preempted (registered: >= 1%); P7 HELD

### P8 arrival -> on-GPU start delay of the 0.1 ms fg (p99, ms) (pre-check (iii) FAILED: shown for completeness, NOT interpreted)

```
  cell  p99_ms
  g_R8  0.9340
g_R0.5  0.6550
  g_R1  0.8734
  g_R2  1.0076
```

- registered: p99 <= 0.4 ms for every m; P8 DID NOT HOLD

## g_bgalone: gaps with no foreground (other GPU contexts, reported baseline preemption rate; not a prediction)

```
 block  g_thr_us  bg_blocks  blocks_with_gap_ge_gthr  fraction  gaps_logged  gaps_ge_gthr  gap_len_median_us  gap_len_max_us  novf_blocks
     0   41.8938     264384                   132192       0.5       423959        403555            267.264         362.496            0
```
