# Experiment G pre-checks (i)-(iii), smoke-grade

Source `data\raw\w2_G_precheck\20261021T223730Z` | admin False | unlocked clocks unless admin | git c10364b9 dirty False | dll 2662e340fcd300af | NVIDIA GeForce RTX 4070 Laptop GPU driver 616.92
NOT a result and NOT the registered acceptance: clocks were not locked (no admin), 3 blocks. The registered pre-check (iii) is re-evaluated on the full G data; this run only shows the instrumentation works and its rough cost.

## (i) %globaltimer resolution

- smallest nonzero difference between consecutive reads in one block: **1024 ns** (fraction of identical consecutive reads 0.992)

## (ii-a) one process, two streams: shared timebase against host QPC

- GPU-timer/QPC offset drift over the test 0.0 us; round trips 7 / 7 us; tolerance 115 us
- stream A: 216 blocks, 0 outside the host launch..done window
- stream B: 216 blocks, 0 outside the host launch..done window

## (ii-b) two processes (fg and bg children): same timebase

Per cell with both recordings: the two processes read the GPU timer against QPC at the same instant (dt_probe_s apart); equal timebase if offset_diff_s is within rt_sum_s (the two minimum round trips) plus drift over dt_probe_s; and fg blocks outside their request's host launch..complete window.

```
 block cell  offset_diff_s  rt_sum_s  dt_probe_s  drift_s  fg_blocks  fg_outside  fg_unmatched  bg_blocks  bg_dropped
     0 g_R2  -4.768372e-07  0.000169    0.005443 0.000912     431568           0           432     799848        1813
     0 g_T4   7.390976e-06  0.000175    0.000063 0.000930      86400           0             0     799848        1055
     1 g_R2   7.867813e-06  0.000176    0.012798 0.000927     432000           0             0     799848        1917
     1 g_T4   1.144409e-05  0.000181    0.000061 0.000894      86400           0             0     799848         705
     2 g_T4  -3.814697e-06  0.000195    0.022818 0.000871      85320           0          1080     799848         390
     2 g_R2  -3.743172e-05  0.000093    0.006964 0.000924     432000           0             0     799848        1896
```

## (iii-a) controlled A/B in one process: plain vs recording kernel, alternating 0.25 s runs x 6, by gap-read stride (iterations between %globaltimer reads) and slice size

ratio = median host slice duration (launch..sync) recording / plain. median_read_gap_ns = median over blocks of block duration / reads, the quantity G_thr = 20 x that is built from.

```
 stride  units  plain_ms  rec_ms  ratio  median_read_gap_ns
     64   1000    0.0611  0.0614 1.0041           2016.0000
     64   8000    0.4205  0.4200 1.0003           2082.5397
     64  40000    1.9987  2.0032 0.9994           2057.4058
    128   1000    0.0620  0.0599 0.9662           3840.0000
    128   8000    0.4206  0.4097 0.9739           3998.4762
    128  40000    2.0115  1.9515 0.9708           3971.6805
    256   1000    0.0616  0.0593 0.9634           7680.0000
    256   8000    0.4219  0.4034 0.9556           7736.0000
    256  40000    2.0281  1.9417 0.9563           7797.4013
    512   1000    0.0615  0.0590 0.9577          14848.0000
    512   8000    0.4264  0.4035 0.9490          15520.0000
    512  40000    2.0454  1.9452 0.9503          15528.5063
```

## (iii-b) harness cells: instrumented vs uninstrumented twin (clocks NOT locked here: the fg-alone cells idle at ~210 MHz, so baseline-based numbers are not meaningful at smoke grade; the R_2 on/off columns are)

```
 block  base_on_p50  base_off_p50  r2_on_p50  r2_off_p50  wait_on  wait_off  slice_on_ms  slice_off_ms  gpu_on_ms  gpu_off_ms
     0       0.4351        0.3698     0.3707      0.3763  -0.3624   -0.3192       2.0007        2.0174     0.3676      0.3195
     1       0.4094        0.4790     0.3648      0.3648  -0.3628   -0.4140       2.0044        1.9943     0.3430      0.3922
     2       0.4432        0.1682     0.3685      0.3614  -0.3941   -0.1761       2.0084        1.9789     0.3656      0.0870
```

- R_2 latency p50, instrumented vs not (busy GPU, so clocks are comparable): relative difference 1.0% (limit 5%); bg mean slice 2.0044 vs 1.9943 ms
- fg-alone latency criterion and the R_2 observed-wait criterion (within 0.03 ms) need locked clocks: here the fg-alone cells idle at ~210 MHz, so the baseline-based wait differs by 0.044 ms and the fg-alone p50 by 17.6% for clock-state reasons, not instrumentation. NOT EVALUATED at smoke grade; to be evaluated on the full G data (R_m vs R_m_off per block); see STATUS decision 1 about the fg-alone twin

- smoke-grade verdict: (iii-a) recording/plain slice ratio at stride 64 = 0.999-1.004; R_2 on/off p50 within 1.0% -> the instrumentation cost is small in the controlled tests; the registered acceptance is still open
