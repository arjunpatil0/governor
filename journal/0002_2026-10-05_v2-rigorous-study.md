# 0002 — v2: a rigorous 4-arm chunking study, and a wrong explanation (reconstructed)
Date: 2026-10-01..05 · Phase: pre-project · Author: reviewer (from variance_gpu_project abed29f, 4bd648a)
## Belief going in
H1: ADAPTIVE beats STATIC-MATCHED (same mean chunk size) on total time by >=5%, p<0.05.
## What we did
4 arms (ADAPTIVE, STATIC-LARGE, STATIC-MATCHED, INVERTED), 4 workloads (A–D), n=20, paired Wilcoxon,
randomised arm order, warm-up, causal observer. RTX 4070 Laptop, Windows.
## What happened
ADAPTIVE was slowest on every variable workload (e.g. B: 11,823 ms vs 2,757 ms STATIC-LARGE). H1 rejected.
Explanation written at the time: per-launch overhead (~0.75 ms, calibrated) multiplied by more launches.
## Setbacks / surprises
The explanation was not checked against the logged data. See 0003: it was wrong.
## Lesson
A rigorous design does not protect an untested mechanism claim. Check every causal explanation against the data.
