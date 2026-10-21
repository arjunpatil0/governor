# 0020 — Experiment A (residual-wait model): results
Date: 2026-10-21 · Phase: W2 · Author: Claude Code (run by Arjun: admin shell, AC, clean tree at 4a6fcd4, ambient 25 C)
Raw data: data/raw/w2_A/20261021T153524Z (190 cells = 19 x 10 blocks; force-added). Report: data/w2_A_results.md (`python analysis/w2_analysis.py --part A`). Execution mode: CUDA native kernels via w2_kernels.dll (no CPU fallback). HAGS ON. yaml e1df18ccd6898bd9, dll aa73f2b11a6ccb41.

## Results (pre-registered tests, numbers from data/w2_A_results.md)
- **HA1 NOT SUPPORTED.** OLS slope of observed_wait on predicted_wait 0.013 (90% block-bootstrap CI [0.013, 0.013], bound [0.8, 1.25]); intercept 0.230 ms (CI [0.219, 0.240]); cells within +/-25% of prediction 0.17 (need >= 0.70).
- **Pre-registered failure classification (evaluated in order): preempted_or_concurrent** (slope CI upper bound 0.013 < 0.8 AND median obs/pred over cells with m >= 2 = 0.11 < 0.5). Criterion (2) scheduler_capped (obs at m=8 <= 1.25 x obs at m=2, c=0: 0.298 vs 0.287 ms; pred grows 4.0x) is also numerically true, but the rule is ordered so (1) is the label. Not a judgment call by me.
- **HA2 NOT SUPPORTED** (3 of 6 significant after Holm; needed 4). Significant at m = 0.25, 0.5, 1.0 (median diffs +0.035, +0.016, +0.011 ms, Holm p 0.006, 0.006, 0.012); not at m = 2, 4, 8 (median diffs -0.007, -0.005, +0.001 ms).
- Cell medians (over blocks): observed wait 0.15 ms at m=0.25 rising to 0.30 ms at m=8 (c=0 : 0.153, 0.226, 0.255, 0.287, 0.297, 0.298 ms for m = 0.25..8), while the model's prediction rises 0.13 -> 4.2 ms (c=0). Block baseline mean latency 0.155 ms (range 0.130-0.195 over blocks). Background utilisation rho = 0.999-1.000 in every cell. fg p99 latency 0.77-1.17 ms, never near the 4-8 ms slices; completed fraction 1.0 in all cells (no overload).
- Reported-not-tested items (p99/p99.9 vs longest slice, fraction of arrivals inside a slice) are in the report/results.csv; SA1-SA4 are in A2, not run yet.

## Flags
39 of 190 cells carry `start_temp_not_reached` (start temperature target not reached before the cell began); one also `mem_clock_left_target:7001` (block 7, bg_fma_m0.5_c1.0). Per the pre-registration flagged cells stay in the data; no re-analysis excluding them has been run. Per block (blocks numbered 0-9 in results.csv; tallied from results.csv): block 1: 2, block 2: 12, block 7: 2, block 8: 12, block 9: 11, none elsewhere. Median pre-cell GPU temperature per block was 61 C in most blocks but 73 C (block 2) and 71 C (blocks 8, 9), which are the heavily flagged blocks. Whether temperature affects observed_wait is not tested here; the flagged blocks are not excluded from any reported number.

## What is NOT claimed
No mechanism. The data say the foreground's added latency does not grow with the background slice length over 0.25-8 ms; they do not say whether the GPU preempts mid-slice, runs both contexts concurrently, or something else (the Nsight traces could not show context switches, journal 0019). The observed ~0.23 ms intercept matches the pilot's "~0.3 ms switch cost" only loosely; no claim made.

## Next
Reviewer checkpoint due (results before interpretation). Then A2 (SA1-SA4). The deferred globaltimer addendum has a pre-stated trigger evaluated on A2's SA4 and SA2 results.
