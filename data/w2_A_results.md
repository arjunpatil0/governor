# W2 Experiment A: residual-wait model | REGISTERED ANALYSIS (all cells)

Source: `data\raw\w2_A\20261021T153524Z` | run 20261021T153524Z | admin True | AC True | ambient 25.0 C | NVIDIA GeForce RTX 4070 Laptop GPU | driver 616.92 | yaml e1df18ccd6898bd9 | dll aa73f2b11a6ccb41 | git 4a6fcd4b
HAGS: DriverSupportState:Stable Enabled:True. Execution mode: CUDA native kernels via w2_kernels.dll (no CPU fallback).

Blocks: 10, cells per block: 19.

## HA1

- slope 0.013, 90% block-bootstrap CI [0.013, 0.013] (equivalence bounds [0.8, 1.25]): equivalent = False
- intercept 0.230 ms, 90% CI [0.219, 0.240]
- cells within +/-25% of prediction: 0.17 (need >= 0.70)
- **HA1 NOT SUPPORTED**; classification: **preempted_or_concurrent**

## HA2 (variance raises wait)

 m_ms  n  median_diff        p   p_holm  significant
 0.25 10     0.034747 0.000977 0.005859         True
 0.50 10     0.015502 0.000977 0.005859         True
 1.00 10     0.011237 0.002930 0.011719         True
 2.00 10    -0.006639 1.000000 1.000000        False
 4.00 10    -0.004965 0.903320 1.000000        False
 8.00 10     0.000788 0.460938 1.000000        False

**HA2 NOT SUPPORTED** (3/6 significant after Holm).

## Cell medians over blocks (obs = mean latency - block baseline; pred from realised slices)

 m_ms  cv   obs_ms  pred_ms
 0.25 0.0 0.153071 0.134827
 0.25 0.5 0.169220 0.166915
 0.25 1.0 0.189923 0.266214
 0.50 0.0 0.225745 0.268379
 0.50 0.5 0.231098 0.333967
 0.50 1.0 0.236915 0.533333
 1.00 0.0 0.254608 0.533547
 1.00 0.5 0.263948 0.665186
 1.00 1.0 0.271949 1.058739
 2.00 0.0 0.286855 1.063273
 2.00 0.5 0.284988 1.328185
 2.00 1.0 0.282041 2.122992
 4.00 0.0 0.296655 2.124681
 4.00 0.5 0.293756 2.657513
 4.00 1.0 0.294028 4.204745
 8.00 0.0 0.298112 4.238881
 8.00 0.5 0.301091 5.333775
 8.00 1.0 0.300854 8.484729

## Flags (cells stay in the data): 39 of 190

 block           cell_id                                             flags
     1    bg_fma_m1_c1.0                            start_temp_not_reached
     1    bg_fma_m2_c0.5                            start_temp_not_reached
     2    bg_fma_m4_c1.0                            start_temp_not_reached
     2    bg_fma_m1_c0.0                            start_temp_not_reached
     2    bg_fma_m2_c1.0                            start_temp_not_reached
     2 bg_fma_m0.25_c0.5                            start_temp_not_reached
     2    bg_fma_m2_c0.0                            start_temp_not_reached
     2 bg_fma_m0.25_c0.0                            start_temp_not_reached
     2          baseline                            start_temp_not_reached
     2  bg_fma_m0.5_c0.5                            start_temp_not_reached
     2    bg_fma_m1_c1.0                            start_temp_not_reached
     2 bg_fma_m0.25_c1.0                            start_temp_not_reached
     2  bg_fma_m0.5_c1.0                            start_temp_not_reached
     2    bg_fma_m1_c0.5                            start_temp_not_reached
     7  bg_fma_m0.5_c1.0 start_temp_not_reached;mem_clock_left_target:7001
     7    bg_fma_m8_c0.5                            start_temp_not_reached
     8          baseline                            start_temp_not_reached
     8    bg_fma_m1_c1.0                            start_temp_not_reached
     8    bg_fma_m1_c0.5                            start_temp_not_reached
     8  bg_fma_m0.5_c1.0                            start_temp_not_reached
     8    bg_fma_m2_c0.0                            start_temp_not_reached
     8    bg_fma_m4_c1.0                            start_temp_not_reached
     8  bg_fma_m0.5_c0.0                            start_temp_not_reached
     8    bg_fma_m8_c0.0                            start_temp_not_reached
     8    bg_fma_m2_c0.5                            start_temp_not_reached
     8    bg_fma_m1_c0.0                            start_temp_not_reached
     8    bg_fma_m4_c0.5                            start_temp_not_reached
     8    bg_fma_m8_c0.5                            start_temp_not_reached
     9    bg_fma_m4_c1.0                            start_temp_not_reached
     9  bg_fma_m0.5_c0.5                            start_temp_not_reached
     9    bg_fma_m8_c1.0                            start_temp_not_reached
     9  bg_fma_m0.5_c1.0                            start_temp_not_reached
     9 bg_fma_m0.25_c0.5                            start_temp_not_reached
     9 bg_fma_m0.25_c0.0                            start_temp_not_reached
     9    bg_fma_m8_c0.0                            start_temp_not_reached
     9    bg_fma_m1_c1.0                            start_temp_not_reached
     9    bg_fma_m2_c0.5                            start_temp_not_reached
     9          baseline                            start_temp_not_reached
     9    bg_fma_m4_c0.0                            start_temp_not_reached

---

# W2 Experiment A | SENSITIVITY: excluding 36 non-baseline cells flagged start_temp_not_reached (baselines kept; registered rules unchanged)

Source: `data\raw\w2_A\20261021T153524Z` | run 20261021T153524Z | admin True | AC True | ambient 25.0 C | NVIDIA GeForce RTX 4070 Laptop GPU | driver 616.92 | yaml e1df18ccd6898bd9 | dll aa73f2b11a6ccb41 | git 4a6fcd4b
HAGS: DriverSupportState:Stable Enabled:True. Execution mode: CUDA native kernels via w2_kernels.dll (no CPU fallback).

Blocks: 10, cells per block: 19.

## HA1

- slope 0.013, 90% block-bootstrap CI [0.012, 0.013] (equivalence bounds [0.8, 1.25]): equivalent = False
- intercept 0.230 ms, 90% CI [0.218, 0.241]
- cells within +/-25% of prediction: 0.17 (need >= 0.70)
- **HA1 NOT SUPPORTED**; classification: **preempted_or_concurrent**

## HA2 (variance raises wait)

 m_ms  n  median_diff        p   p_holm  significant
 0.25  8     0.034747 0.003906 0.023438         True
 0.50  6     0.016587 0.015625 0.078125        False
 1.00  6     0.011237 0.015625 0.078125        False
 2.00  8    -0.008276 1.000000 1.000000        False
 4.00  7    -0.001246 0.656250 1.000000        False
 8.00  8     0.000788 0.371094 1.000000        False

**HA2 NOT SUPPORTED** (1/6 significant after Holm).

## Cell medians over blocks (obs = mean latency - block baseline; pred from realised slices)

 m_ms  cv   obs_ms  pred_ms
 0.25 0.0 0.163067 0.134825
 0.25 0.5 0.177630 0.166943
 0.25 1.0 0.188179 0.266218
 0.50 0.0 0.224531 0.268186
 0.50 0.5 0.234963 0.333756
 0.50 1.0 0.243696 0.533333
 1.00 0.0 0.252569 0.533712
 1.00 0.5 0.263948 0.665654
 1.00 1.0 0.273059 1.053583
 2.00 0.0 0.286855 1.063264
 2.00 0.5 0.286107 1.326567
 2.00 1.0 0.283319 2.122588
 4.00 0.0 0.300391 2.124618
 4.00 0.5 0.293523 2.667068
 4.00 1.0 0.294814 4.198264
 8.00 0.0 0.298112 4.238881
 8.00 0.5 0.300326 5.333775
 8.00 1.0 0.307453 8.488607

## Flags (cells stay in the data): 3 of 154

 block  cell_id                  flags
     2 baseline start_temp_not_reached
     8 baseline start_temp_not_reached
     9 baseline start_temp_not_reached

---

# W2 Experiment A | SENSITIVITY: excluding start_temp_not_reached cells and every block whose baseline was flagged (61 cells dropped; registered rules unchanged)

Source: `data\raw\w2_A\20261021T153524Z` | run 20261021T153524Z | admin True | AC True | ambient 25.0 C | NVIDIA GeForce RTX 4070 Laptop GPU | driver 616.92 | yaml e1df18ccd6898bd9 | dll aa73f2b11a6ccb41 | git 4a6fcd4b
HAGS: DriverSupportState:Stable Enabled:True. Execution mode: CUDA native kernels via w2_kernels.dll (no CPU fallback).

Blocks: 7, cells per block: 19.

## HA1

- slope 0.013, 90% block-bootstrap CI [0.013, 0.014] (equivalence bounds [0.8, 1.25]): equivalent = False
- intercept 0.230 ms, 90% CI [0.217, 0.242]
- cells within +/-25% of prediction: 0.17 (need >= 0.70)
- **HA1 NOT SUPPORTED**; classification: **preempted_or_concurrent**

## HA2 (variance raises wait)

 m_ms  n  median_diff        p   p_holm  significant
 0.25  7     0.035468 0.007812 0.046875         True
 0.50  6     0.016587 0.015625 0.078125        False
 1.00  6     0.011237 0.015625 0.078125        False
 2.00  7    -0.006973 1.000000 1.000000        False
 4.00  7    -0.001246 0.656250 1.000000        False
 8.00  7     0.001183 0.187500 0.562500        False

**HA2 NOT SUPPORTED** (1/6 significant after Holm).

## Cell medians over blocks (obs = mean latency - block baseline; pred from realised slices)

 m_ms  cv   obs_ms  pred_ms
 0.25 0.0 0.154152 0.134823
 0.25 0.5 0.170694 0.167041
 0.25 1.0 0.188179 0.266218
 0.50 0.0 0.226960 0.268663
 0.50 0.5 0.227569 0.333429
 0.50 1.0 0.243696 0.533333
 1.00 0.0 0.256622 0.533847
 1.00 0.5 0.266960 0.664005
 1.00 1.0 0.273059 1.053583
 2.00 0.0 0.287068 1.062950
 2.00 0.5 0.292289 1.334836
 2.00 1.0 0.283319 2.122588
 4.00 0.0 0.300391 2.124744
 4.00 0.5 0.293523 2.647958
 4.00 1.0 0.294814 4.198264
 8.00 0.0 0.293583 4.240129
 8.00 0.5 0.307974 5.289286
 8.00 1.0 0.309918 8.540849

## Flags (cells stay in the data): 0 of 129

none