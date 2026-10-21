# Experiment G pre-checks (i)-(iii), smoke-grade

Source `data\raw\w2_G_precheck\20261021T222514Z` | admin False | unlocked clocks unless admin | git 60b8a82a dirty False | dll 07437d821442160e | NVIDIA GeForce RTX 4070 Laptop GPU driver 616.92
NOT a result and NOT the registered acceptance: clocks were not locked (no admin), 3 blocks. The registered pre-check (iii) is re-evaluated on the full G data; this run only shows the instrumentation works and its rough cost.

## (i) %globaltimer resolution

- smallest nonzero difference between consecutive reads in one block: **1024 ns** (fraction of identical consecutive reads 0.992)

## (ii-a) one process, two streams: shared timebase against host QPC

- GPU-timer/QPC offset drift over the test 0.5 us; round trips 8 / 9 us; tolerance 119 us
- stream A: 216 blocks, 0 outside the host launch..done window
- stream B: 216 blocks, 0 outside the host launch..done window

## (ii-b) two processes (fg and bg children): same timebase

Per cell with both recordings: the two processes read the GPU timer against QPC at the same instant (dt_probe_s apart); equal timebase if offset_diff_s is within rt_sum_s (the two minimum round trips) plus drift over dt_probe_s; and fg blocks outside their request's host launch..complete window.

```
 block cell  offset_diff_s  rt_sum_s  dt_probe_s  drift_s  fg_blocks  fg_outside  fg_unmatched  bg_blocks  bg_dropped
     0 g_R2   7.152557e-07  0.000018    0.009408 0.000868     431568           0           432     668088           0
     0 g_T4   2.384186e-07  0.000160    0.003050 0.000927      86400           0             0     446256           0
     1 g_R2   5.006790e-06  0.000185    0.024591 0.000921     432000           0             0     679968           0
     1 g_T4  -7.390976e-06  0.000203    0.000063 0.000898      86400           0             0     390744           0
     2 g_T4  -7.629395e-06  0.000200    0.000063 0.000865      85320           0          1080     365040           0
     2 g_R2   9.059906e-06  0.000202    0.000061 0.000921     432000           0             0     679320           0
```

## (iii-a) controlled A/B in one process: plain vs recording kernel, alternating 0.25 s runs x 6, by gap-read stride (iterations between %globaltimer reads) and slice size

ratio = median host slice duration (launch..sync) recording / plain. median_read_gap_ns = median over blocks of block duration / reads, the quantity G_thr = 20 x that is built from.

```
 stride  units  plain_ms  rec_ms  ratio  median_read_gap_ns
     64   1000    0.0641  0.0998 1.5587           4256.0000
     64   8000    0.4103  0.6915 1.6851           4317.4603
     64  40000    1.9745  3.3759 1.7096           4339.7316
    128   1000    0.0644  0.0994 1.5410           8384.0000
    128   8000    0.4108  0.6841 1.6656           8602.4127
    128  40000    1.9982  3.3385 1.6740           8658.1981
    256   1000    0.0639  0.0982 1.5360          16768.0000
    256   8000    0.4158  0.6801 1.6376          16984.0000
    256  40000    2.0167  3.3245 1.6494          17269.4013
    512   1000    0.0639  0.0979 1.5301          33536.0000
    512   8000    0.4137  0.6831 1.6466          33984.0000
    512  40000    2.0149  3.3418 1.6612          34401.2152
```

## (iii-b) harness cells: instrumented vs uninstrumented twin (clocks NOT locked here: the fg-alone cells idle at ~210 MHz, so baseline-based numbers are not meaningful at smoke grade; the R_2 on/off columns are)

```
 block  base_on_p50  base_off_p50  r2_on_p50  r2_off_p50  wait_on  wait_off  slice_on_ms  slice_off_ms  gpu_on_ms  gpu_off_ms
     0       0.2548        0.4005     0.4438      0.3819  -0.3122   -0.3431       3.5705        2.0558     0.1454      0.3318
     1       0.6224        0.4853     0.4390      0.3810  -0.5441   -0.4185       3.5838        2.0564     0.5550      0.4060
     2       0.6374        0.3983     0.4332      0.3718  -0.6577   -0.3494       3.5800        2.0793     0.5734      0.3297
```

- fg-alone latency p50, instrumented vs not: relative difference 55.4% (limit 5%)
- observed wait of R_2 (mean latency minus the same-condition fg-alone mean), instrumented -0.5441 ms vs -0.3494 ms: difference 0.1947 ms (limit 0.03)
- R_2 latency p50 relative difference 15.2%; bg mean slice 3.5800 vs 2.0564 ms; fg gpu p50 0.5550 vs 0.3318 ms
- acceptance at smoke grade: **FAIL** (fg-alone latency and R_2 wait)
