# Experiment G report (SMOKE: not a result)

Source `data\raw\w2_G_smoke\20261022T055838Z` | admin False | AC True | ambient 25.0 C | Armoury Performance | NVIDIA GeForce RTX 4070 Laptop GPU driver 616.92 | yaml e1df18ccd6898bd9 | dll 7768289069367275 | git 4ee8f80f | blocks 1 | cells 17
Addenda: experiments/w2_colocation_addendum_globaltimer_2026-10-22.md and ..._prerun_2026-10-22.md (and _witness_ if registered). Each prediction: held / did not hold, with the numbers.
Block set for gap, run, overlap and preemption analyses: ALL blocks (secondary view; blocks beyond three per SM show intra-SM arbitration gaps even with no other context).

## Pre-check (iii): instrumentation overhead (registered acceptance; if it fails the timeline is NOT interpreted)

```
 block  base_on_p50  base_off_p50  wait_on  wait_off  slice_on_ms  slice_off_ms  gpu_on_ms  gpu_off_ms
     0       0.4564        0.1697  -0.3794   -0.1092       2.1333        2.1178     0.3963      0.1014
```

- median fg-alone latency, instrumented vs not: relative difference 169.0% (limit 5%)
- observed wait of R_2, instrumented -0.3794 ms vs uninstrumented -0.1092 ms: difference 0.2702 ms (limit 0.03)
- bg mean slice 2.1333 vs 2.1178 ms; fg gpu p50 0.3963 vs 0.1014 ms
- **pre-check (iii): FAIL: do not interpret the timeline (P4-P8); report the failure**

## P1-P3 on the uninstrumented R_m_off cells (fresh seeds; the block baseline is g_baseline_off)

### P1: cell-median observed wait within +/-0.03 ms of A

```
 m_ms  n_blocks  obs_wait_ms  a_wait_ms  diff_ms  within_tol
  0.5         1      -0.1773      0.226  -0.4033       False
  1.0         1      -0.1477      0.255  -0.4027       False
  2.0         1      -0.1092      0.287  -0.3962       False
  8.0         1      -0.1185      0.298  -0.4165       False
```

- P1 DID NOT HOLD

### P2: capped-wait fit on the observed slice-end axis (n = 7980 requests, all four m pooled)

- tau = 0.250 ms, 90% block-bootstrap CI [0.250, 0.250], offset -0.368 ms; registered range 0.22-0.31 ms (A: 0.260)
- P2 HELD

### P3: ripple on the unstretched axis (binned means, A's bins)

```
  lo   hi   n  mean_wait_ms
0.00 0.05 316       -0.3179
0.05 0.10 338       -0.2643
0.10 0.15 342       -0.2611
0.15 0.20 358       -0.2363
0.20 0.25 338       -0.2095
0.25 0.30 344       -0.1605
0.30 0.35 331       -0.1264
0.35 0.40 331       -0.1076
0.40 0.45 380       -0.0665
0.45 0.50 377       -0.0358
0.50 0.55 179       -0.0898
0.55 0.60 141       -0.0347
0.60 0.65 144       -0.2085
0.65 0.70 140       -0.1664
0.70 0.75 139       -0.1461
0.75 0.80 155       -0.0721
0.80 0.85 146       -0.1201
0.85 0.90 136       -0.0871
0.90 0.95 163       -0.0613
0.95 1.00 166       -0.0165
1.00 1.50 617       -0.1085
1.50 2.00 594       -0.0827
2.00 2.50 156       -0.1099
2.50 3.00  97       -0.1138
3.00 3.50 113       -0.1034
3.50 4.00 129       -0.1082
4.00 4.50 122       -0.0974
4.50 5.00 130       -0.1110
5.00 5.50 110       -0.1489
5.50 6.00 120       -0.1176
6.00 6.50 128       -0.1017
6.50 7.00 122       -0.0987
7.00 7.50 109       -0.1434
7.50 8.00  79       -0.0770
```

- local minimum 0.35-0.40: False (drop -0.019 ms below the preceding maximum); local minimum 0.80-0.85: True (drop 0.085 ms); required drop >= 0.04 ms (A: 0.300->0.214, 0.364->0.232)
- P3 DID NOT HOLD

## Witness validity gate (addendum 3 section A)

- all-blocks view: the witness gate does not apply (secondary view, arbitration artefact present)
- gate (i): PASS; gate (ii) placement is reported per cell below (nominal / fallback / excluded launches)

## Timeline cells: coverage, trust and results per block (recorded-interval rule, addendum 2 section C)

Coverage and trust (fg_share = share of the cell's measured fg requests wholly inside the recorded interval; untrusted = blocks with gap-log overflow; gap_lost = gaps lost to a full global list):

```
 block   cell  n_fg_in_interval  n_bg_launches  interval_s  fg_share  bg_launches_dropped  n_untrusted_fg  n_untrusted_bg  gap_lost  fg_w_nominal  fg_w_fallback  fg_w_excluded  bg_w_nominal  bg_w_fallback  bg_w_excluded
     0   g_R2              2000           5198      11.079     0.995                    0               0               0         0             0              0              0             0              0              0
     0   g_R8              2000           1304      10.889     0.998                    0               0               0         0             0              0              0             0              0              0
     0   g_T1              1000           4579      10.997     0.998                    0               0               0         0             0              0              0             0              0              0
     0   g_T4               396           4323      11.429     1.000                    0               0               0         0             0              0              0             0              0              0
     0 g_R0.5               813           7407       3.984     0.406                12997               0               0         0             0              0              0             0              0              0
     0   g_R1              1847           7407       9.282     0.924                 1640               0               0         0             0              0              0             0              0              0
```

Per block results:

```
 block   cell  alone_span_ms  n_sliced  q_pooled_ms  q_fg_ms  q_bg_ms   s_ms  n_neg_s  n_overlap  n_overlap_same_sm  n_overlap_diff_sm  n_ties  n_fg_blocks  g_thr_us  preempt_frac  preempt_frac_with_fg  p8_delay_p99_ms
     0   g_R2         0.3748         0          NaN      NaN      NaN    NaN        0       1296                198               1290       0       432000   41.9598        0.5507                0.1670           1.0433
     0   g_R8         0.3748         0          NaN      NaN      NaN    NaN        0          0                  0                  0       0       432000   41.9598        0.7160                0.5560           0.9628
     0   g_T1         1.2093      1000       0.3871   0.3860   0.3881 0.0983      115      13497               2493              13434      35       216000   41.9598        0.5661                0.1599           4.5496
     0   g_T4         4.9213       396       0.3860   0.3871   0.3860 0.1014      212      14625               2704              14528     160        85536   41.9598        0.5914                0.1860          30.3578
     0 g_R0.5         0.3748         0          NaN      NaN      NaN    NaN        0          0                  0                  0       0       175608   41.9598        0.5000                0.0276           0.6504
     0   g_R1         0.3748         0          NaN      NaN      NaN    NaN        0       6912               1752               6882       0       398952   41.9598        0.5216                0.0875          13.7934
```

### P4 quantum q (pooled complete runs of both contexts inside sliced fg spans) (a validity gate FAILED: shown for completeness, NOT interpreted)

```
  cell  n_runs  q_pooled_ms  q_fg_ms  q_bg_ms  n_s   s_ms
g_R0.5       0          NaN      NaN      NaN    0    NaN
  g_R1       0          NaN      NaN      NaN    0    NaN
  g_R2       0          NaN      NaN      NaN    0    NaN
  g_R8       0          NaN      NaN      NaN    0    NaN
  g_T1    2161       0.3871   0.3860   0.3881 3673 0.0983
  g_T4    6067       0.3860   0.3871   0.3860 7355 0.1014
```

- pooled over all cells: q = 0.386 ms from 8228 complete runs; registered range 0.5-0.9 ms; P4 DID NOT HOLD

### P5 switch gap s (a validity gate FAILED: shown for completeness, NOT interpreted)

- pooled s = 0.100 ms from 11028 transitions; registered range 0.2-0.3 ms; P5 DID NOT HOLD; negative-s transitions (runs overlapping in time): 327

### P6 no concurrency (a validity gate FAILED: shown for completeness, NOT interpreted)

```
  cell  n_overlap  n_overlap_same_sm  n_overlap_diff_sm  n_ties  n_fg_blocks  n_untrusted_fg
g_R0.5          0                  0                  0       0       175608               0
  g_R1       6912               1752               6882       0       398952               0
  g_R2       1296                198               1290       0       432000               0
  g_R8          0                  0                  0       0       432000               0
  g_T1      13497               2493              13434      35       216000               0
  g_T4      14625               2704              14528     160        85536               0
```

- fg blocks overlapping a bg block by more than 10 us: 36330 of 1740096 trusted blocks (untrusted excluded: 0); ties (<= 10 us): 195; P6 DID NOT HOLD

#### Concurrency rule (addendum 3 section B): the 3-blocks-per-SM control g_T4_3bpsm

```
 block  n_overlap  n_overlap_same_sm  n_overlap_diff_sm  n_ties  n_fg_blocks  n_untrusted_fg  preempt_frac  interval_s
     0          0                  0                  0       0        43092               0         0.226      10.551
```

- P6 failed in the main cells but the arbitration-free control shows NO overlap: the main-cell overlaps are UNEXPLAINED and are NOT reported as concurrency.

### P7 mid-kernel preemption of bg blocks (block has a gap >= G_thr; mean over blocks) (a validity gate FAILED: shown for completeness, NOT interpreted)

```
  cell  preempt_frac  preempt_frac_with_fg
g_R0.5        0.5000                0.0276
  g_R1        0.5216                0.0875
  g_R2        0.5507                0.1670
  g_R8        0.7160                0.5560
  g_T1        0.5661                0.1599
  g_T4        0.5914                0.1860
```

- g_T4: 59.14% of recorded bg blocks preempted (registered: >= 1%); P7 HELD

### P8 arrival -> on-GPU start delay of the 0.1 ms fg (p99, ms) (a validity gate FAILED: shown for completeness, NOT interpreted)

```
  cell  p99_ms
  g_R2  1.0433
  g_R8  0.9628
g_R0.5  0.6504
  g_R1 13.7934
```

- registered: p99 <= 0.4 ms for every m; P8 DID NOT HOLD

## g_bgalone: gaps with no foreground (other GPU contexts, reported baseline preemption rate; not a prediction)

```
 block            cell  g_thr_us  bg_blocks  blocks_with_gap_ge_gthr  fraction  gaps_logged  gaps_ge_gthr  gap_len_median_us  gap_len_max_us  novf_blocks
     0       g_bgalone   41.9598     264384                   132192       0.5       423620        403363            267.264         364.544            0
     0 g_bgalone_3bpsm   23.9875     135648                        0       0.0            0             0                NaN             NaN            0
```
