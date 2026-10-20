# W1 downclock results

Source: `C:\Users\arjun\governor\data\raw\w1_downclock\20261020T213210Z\results.csv` | run 20261020T213210Z | admin True | AC True | ambient 24.0 C | NVIDIA GeForce RTX 4070 Laptop GPU | driver 616.92 | yaml 1c680f61dc105389 | git 20ae44a6
Execution mode: CUDA native kernels via bench_kernels.dll (no CPU fallback). Blocks: 10. Flagged rows: 7 of 120.

## Per-cell summary (median [IQR] over blocks; ratios are within-block vs the unlocked cell)

| kernel | clock | n | SM MHz (med) | throughput | rel. throughput | power W (counter) | energy/work J | rel. energy/work | flags |
|---|---|---|---|---|---|---|---|---|---|
| mem | 600 | 10 | 600 | 187.8 GB/s | 0.809 [0.809-0.809] | 34.7 | 0.1852 J/GB | 0.737 [0.719-0.762] | 1 |
| mem | 900 | 10 | 900 | 206.2 GB/s | 0.889 [0.888-0.903] | 35.5 | 0.1725 J/GB | 0.696 [0.687-0.709] | 0 |
| mem | 1200 | 10 | 1200 | 230.5 GB/s | 0.993 [0.993-0.993] | 37.0 | 0.1607 J/GB | 0.649 [0.627-0.672] | 0 |
| mem | 1500 | 10 | 1500 | 231.4 GB/s | 0.997 [0.997-0.997] | 39.7 | 0.1716 J/GB | 0.687 [0.672-0.694] | 0 |
| mem | 1800 | 10 | 1800 | 231.7 GB/s | 0.998 [0.998-0.999] | 44.3 | 0.1913 J/GB | 0.767 [0.748-0.789] | 0 |
| mem | unlocked | 10 | 2475 | 232.1 GB/s | 1.000 [1.000-1.000] | 57.7 | 0.2488 J/GB | 1.000 [1.000-1.000] | 0 |
| fma | 600 | 10 | 600 | 4526.4 GFLOP/s | 0.244 [0.243-0.244] | 19.3 | 0.0043 J/GFLOP | 0.995 [0.970-1.045] | 3 |
| fma | 900 | 10 | 900 | 6789.0 GFLOP/s | 0.366 [0.365-0.366] | 22.5 | 0.0033 J/GFLOP | 0.761 [0.749-0.777] | 2 |
| fma | 1200 | 10 | 1200 | 9051.2 GFLOP/s | 0.488 [0.487-0.488] | 26.2 | 0.0029 J/GFLOP | 0.681 [0.646-0.701] | 1 |
| fma | 1500 | 10 | 1500 | 11289.7 GFLOP/s | 0.609 [0.607-0.609] | 33.1 | 0.0029 J/GFLOP | 0.697 [0.670-0.698] | 0 |
| fma | 1800 | 10 | 1800 | 13576.9 GFLOP/s | 0.732 [0.730-0.732] | 44.5 | 0.0033 J/GFLOP | 0.762 [0.753-0.768] | 0 |
| fma | unlocked | 10 | 2460 | 18553.1 GFLOP/s | 1.000 [1.000-1.000] | 79.9 | 0.0043 J/GFLOP | 1.000 [1.000-1.000] | 0 |

## H1: memory-bound keeps more throughput than compute-bound (one-sided paired Wilcoxon, Holm over 5 levels)

| clock | n | median(ratio_mem - ratio_fma) | p | p (Holm) | rank-biserial | significant |
|---|---|---|---|---|---|---|
| 600 | 10 | +0.565 | 0.0010 | 0.0049 | +1.00 | yes |
| 900 | 10 | +0.524 | 0.0010 | 0.0049 | +1.00 | yes |
| 1200 | 10 | +0.506 | 0.0010 | 0.0049 | +1.00 | yes |
| 1500 | 10 | +0.388 | 0.0010 | 0.0049 | +1.00 | yes |
| 1800 | 10 | +0.267 | 0.0010 | 0.0049 | +1.00 | yes |

Decision (registered: >= 4 of 5 levels): **H1 SUPPORTED** (5/5 significant).

## H2: energy per unit work for memory-bound falls below unlocked (one-sided Wilcoxon on ratio-1 < 0)

| clock | n | median rel. energy/work (mem) | p | p (Holm) | rank-biserial | significant |
|---|---|---|---|---|---|---|
| 600 | 10 | 0.737 | 0.0010 | 0.0049 | +1.00 | yes |
| 900 | 10 | 0.696 | 0.0010 | 0.0049 | +1.00 | yes |
| 1200 | 10 | 0.649 | 0.0010 | 0.0049 | +1.00 | yes |
| 1500 | 10 | 0.687 | 0.0010 | 0.0049 | +1.00 | yes |
| 1800 | 10 | 0.767 | 0.0010 | 0.0049 | +1.00 | yes |

Decision (registered: >= 1 level): **H2 SUPPORTED** (5/5 significant).

## Secondary (exploratory): relative energy/work, mem vs fma (paired, one-sided mem < fma)

| clock | n | median(rel_epw_mem - rel_epw_fma) | p (Holm) |
|---|---|---|---|
| 600 | 10 | -0.271 | 0.0049 |
| 900 | 10 | -0.071 | 0.0049 |
| 1200 | 10 | -0.028 | 0.1260 |
| 1500 | 10 | -0.005 | 0.5566 |
| 1800 | 10 | +0.001 | 0.6152 |

## Sensitivity: H2 with sample-based energy (mean 20 Hz power x wall time) instead of the energy counter

| clock | n | median rel. energy/work (mem, samples) | p (Holm) | significant |
|---|---|---|---|---|
| 600 | 10 | 0.724 | 0.0049 | yes |
| 900 | 10 | 0.678 | 0.0049 | yes |
| 1200 | 10 | 0.639 | 0.0049 | yes |
| 1500 | 10 | 0.683 | 0.0049 | yes |
| 1800 | 10 | 0.762 | 0.0049 | yes |

Counter-based H2: supported (levels ['600', '900', '1200', '1500', '1800']); sample-based H2: supported (levels ['600', '900', '1200', '1500', '1800']). **Both energy sources agree on the decision and on the significant levels.**

## Flags (validity checks; cells stay in the data)

 block kernel level                       flags
     0    fma   600 energy_vs_samples:19.6/17.0
     4    fma   600 energy_vs_samples:21.2/17.4
     5    fma  1200 energy_vs_samples:28.4/24.2
     5    mem   600 energy_vs_samples:36.9/31.5
     7    fma   600 energy_vs_samples:20.7/17.9
     7    fma   900 energy_vs_samples:23.4/20.2
     8    fma   900 energy_vs_samples:24.7/20.7

Distinct checksums per kernel (registered check: identical across reps): {'fma': 1, 'mem': 1}

## The 94 W vs 28.5 W numbers from the capability audit

- Current audit file (admin=True, run 2026-10-20T23:18:27): NVML power_w single read under the 4096x4096 fp16 matmul load, clock unlocked: **95.151 W**; clock-lock row: `median SM clock 2385 -> 1200 (target 1200) -> 2430 MHz after revert; power while locked 28.5 W`.
- Earlier non-admin audit (git 7120171, 2026-10-20T22:52:03): NVML power_w single read under the same matmul load, unlocked: **95.206 W**, SM clock read 2430 MHz.
- These are single instantaneous NVML reads from different runs, not matched measurements. The matched comparison is the table above.