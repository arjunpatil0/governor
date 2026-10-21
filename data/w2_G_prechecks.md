# Experiment G pre-checks (i)-(iii), smoke-grade

Source `data\raw\w2_G_precheck\20261021T221533Z` | admin False | unlocked clocks unless admin | git 10a58ab2 dirty False | dll d70d42e3d1a1dd06 | NVIDIA GeForce RTX 4070 Laptop GPU driver 616.92
NOT a result and NOT the registered acceptance: clocks were not locked (no admin), 3 blocks. The registered pre-check (iii) is re-evaluated on the full G data; this run only shows the instrumentation works and its rough cost.

## (i) %globaltimer resolution

- smallest nonzero difference between consecutive reads in one block: **1024 ns** (fraction of identical consecutive reads 0.992)

## (ii-a) one process, two streams: shared timebase against host QPC

- GPU-timer/QPC offset drift over the test 0.7 us; round trips 7 / 7 us; tolerance 116 us
- stream A: 216 blocks, 0 outside the host launch..done window
- stream B: 216 blocks, 0 outside the host launch..done window

## (ii-b) two processes (fg and bg children): same timebase

Per cell with both recordings: offset difference between the processes vs the sum of the two round trips (equal timebase if the difference is within the round trips + drift), and fg blocks outside their request's host launch..complete window.

```
 block cell  offset_diff_s  rt_sum_s  drift_s  fg_blocks  fg_outside  fg_unmatched  bg_blocks  bg_dropped
     0 g_R2       0.000139  0.000015 0.001046     431568           0           432     799848         929
     0 g_T4       0.000116  0.000015 0.001072      86400           0             0     775872           0
     1 g_R2       0.000134  0.000015 0.001068     432000           0             0     799848        1011
     1 g_T4       0.000124  0.000017 0.001034      86400           0             0     711720           0
     2 g_T4       0.000123  0.000016 0.001008      85320           0          1080     660096           0
     2 g_R2       0.000060  0.000016 0.001060     432000           0             0     799848         997
```

## (iii) instrumentation overhead (instrumented vs uninstrumented twin, per block; medians below)

```
 block  base_on_p50  base_off_p50  r2_on_p50  r2_off_p50  wait_on  wait_off  slice_on_ms  slice_off_ms  gpu_on_ms  gpu_off_ms
     0       0.4767        0.3540     0.3775      0.3750  -0.4044   -0.2914       2.4209        2.0611     0.3871      0.2939
     1       0.4361        0.4400     0.3792      0.3720  -0.3605   -0.3596       2.4277        2.0591     0.3594      0.3656
     2       0.4559        0.3716     0.3823      0.3742  -0.3954   -0.3006       2.4298        2.0766     0.3871      0.2939
```

- fg-alone latency p50, instrumented vs not: relative difference 22.7% (limit 5%)
- observed wait of R_2 (mean latency minus the same-condition fg-alone mean), instrumented -0.3954 ms vs -0.3006 ms: difference 0.0947 ms (limit 0.03)
- R_2 latency p50 relative difference 1.3%; bg mean slice 2.4277 vs 2.0611 ms; fg gpu p50 0.3871 vs 0.2939 ms
- acceptance at smoke grade: **FAIL** (fg-alone latency and R_2 wait)
