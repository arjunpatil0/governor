# Concepts (plain language, for studying; each entry says where it first mattered)

## Time-slicing (WDDM)
Two programs share one GPU on Windows by taking turns, like two people sharing one phone: each gets the GPU for a slice, then the OS swaps contexts (no spatial sharing as with MPS). A short job that arrives while the other program holds a slice waits for it to end or is switched in. First mattered: [0011](../journal/0011_2026-10-21_w2-pilot.md) (pilot), [0017](../journal/0017_2026-10-21_b-review-and-llama-driver.md).

## Residual wait
If a request arrives at a random moment while a background slice is running, the expected wait is the remaining part of that slice. For slice lengths S and busy fraction rho: predicted wait = rho x E[S^2] / (2 E[S]). Longer and more variable slices make requests wait longer (the "inspection paradox": you are more likely to arrive during a long slice). Experiment A tests this. [0008](../journal/0008_2026-10-21_w2-plan-approved-with-modifications.md).

## Utilisation (rho)
The fraction of time the background keeps the GPU busy. The wait formula is multiplied by rho because with gaps the foreground sometimes finds the GPU free. It is measured per cell from realised slice times, not assumed.

## Roofline, compute-bound, memory-bound
A kernel is limited either by arithmetic speed (compute-bound: slows in proportion to the SM clock) or by memory bandwidth (memory-bound: barely cares about the SM clock). Which one depends on the arithmetic done per byte moved. [0006](../journal/0006_2026-10-21_w1-downclock-results.md).

## Knee
The lowest clock at which throughput is still at least 95% of unlocked. Below it you lose speed; above it you only waste power. Here the knee is a property of the specific kernel, not of a workload class (fp16 proxy: 1050 MHz; B's memory frame differs from W1's memory kernel). [0014](../journal/0014_2026-10-21_w2-experiment-c-results.md), [0017](../journal/0017_2026-10-21_b-review-and-llama-driver.md).

## Slack reclamation (deadline-aware downclocking)
If a job finishes well before its deadline, slow the hardware to use the slack and save power. Here: fma 60 Hz frames at 1500 MHz use about 43% less board power with no missed frames. The real-time literature has a name for this (the reviewer cites Pillai and Shin, SOSP 2001; I have NOT verified that citation). [0017](../journal/0017_2026-10-21_b-review-and-llama-driver.md).

## Overload and survivorship bias
If requests arrive faster than they are served, the queue grows without bound and latency depends on how long you watched. Percentiles computed only over finished requests look better than the truth, so the completed fraction is always shown next to them.

## Ceiling effect
A test cannot show "worse" if the reference is already at the maximum (100% missed frames). HB2 with the background is like that: uninformative, not evidence either way. [0017](../journal/0017_2026-10-21_b-review-and-llama-driver.md).

## Pre-registration
Writing down hypotheses, measurements and decision rules in a committed file before any data, and changing them only through dated addenda written before the affected data exist. It stops you picking the story after you see the numbers.

## Equivalence test (HA1)
"The slope is not different from 1" proves nothing with noisy data. Equivalence asks the opposite: is the slope's 90% confidence interval entirely inside [0.8, 1.25]? Only then do we claim the model fits. [0008](../journal/0008_2026-10-21_w2-plan-approved-with-modifications.md).

## Holm correction
When you test several hypotheses, some pass by luck. Holm adjusts the p-values stepwise (smallest p times the number of tests, next smallest times one fewer, and so on) so the chance of any false positive stays at the stated level. Used for B's levels and A's variance tests.

## Paired one-sided Wilcoxon, minimum p
A rank test on within-block differences. With n blocks the smallest possible one-sided p is 1/2^n (all differences in the same direction), so 10 blocks are needed to reach p near 0.001; that is why every W2 experiment has 10 blocks.

## Block-cluster bootstrap
Resample whole blocks (not single cells) with replacement to get a confidence interval, because cells inside one block share conditions (temperature, time) and are not independent.

## Construct validity
Does what you measured stand for what you care about? The int4 decode proxy's naive scalar dequantisation makes it compute-bound, so its knee says nothing about real Q4 decode; only the direction of the effect transfers. [0015](../journal/0015_2026-10-21_b-levels-and-c-validity-statement.md).

## HAGS (hardware-accelerated GPU scheduling)
A Windows setting that moves GPU scheduling from the OS into the GPU. It is ON on this machine and held fixed; it may change how preemption looks. [0010](../journal/0010_2026-10-21_hags-state.md).

## Cold start / DVFS
An idle GPU runs at a low clock (210 MHz) and takes time to ramp when work arrives, so the first requests are slow. That is why experiments lock clocks and use a warm-up or pre-roll. [0011](../journal/0011_2026-10-21_w2-pilot.md).

## NVML energy counter
The GPU's own cumulative energy reading. Reading it too often inflates it, so it is read exactly twice per window. It is board-level (the whole card), good for comparing conditions, not for absolute watts. [ADR-0006](../decisions/ADR-0006_energy-measurement.md).

## CUDA event interval (fg_gpu_ms) under time-slicing
A CUDA event is a timestamp the GPU takes when it reaches that point in a stream. The difference between two events is GPU-timeline time between them, not time my kernel computed: if the GPU is switched to another program in between, that time is counted; time spent waiting before the first event is not. Alone it equals service time; co-run it is ambiguous. [0019](../journal/0019_2026-10-21_nsys-traces-and-fg-gpu-ms.md).

## Wait saturation vs the residual-wait prediction
The model said a request arriving during a long background slice must wait out the rest of it (mean about E[S^2]/(2E[S]), 4 ms for 8 ms slices). Measured, the added wait stayed at about 0.15-0.30 ms for slices from 0.25 to 8 ms. Whatever the GPU does, it does not make the foreground sit through the whole slice. This says what the wait is NOT; it does not yet say why (preemption, concurrency or a scheduler cap all fit a flat curve; A2 is designed to narrow that). [0020](../journal/0020_2026-10-21_experiment-a-results.md).

## Console QuickEdit stall
A Windows console in QuickEdit mode freezes the program writing to it as soon as you click in the window (to select text), until you press Enter. For a timed experiment that is a silent pause between cells. Disabling QuickEdit at startup removes the risk. [0023](../journal/0023_2026-10-22_a2-incidents-and-results.md).

## Sensitivity analysis
Running the registered analysis twice, once on all data and once without cells you suspect are contaminated, to see whether the conclusion depends on them. The registered result stays the headline; the sensitivity run tells you how much to trust it. [0023](../journal/0023_2026-10-22_a2-incidents-and-results.md).

## Post-hoc (exploratory) hypothesis
A hypothesis formed after seeing the data. It can suggest what to test next but cannot confirm itself on the same data: it was built to fit them. Here, tau was suggested by A's medians, so re-fitting it on A's own cells describes A rather than tests it. [0022](../journal/0022_2026-10-21_a2-addendum-and-armoury-mode-record.md), [0023](../journal/0023_2026-10-22_a2-incidents-and-results.md).

## Regressor artefact
If the x-variable in a regression is itself distorted by the effect you are studying, the slope is wrong. SA2 first used the foreground's service time measured WHILE sharing the GPU (inflated by the sharing), which made the slope look like 0.4; using the alone service time gives 0.98. Always ask: was x measured under the same conditions as y? [0024](../journal/0024_2026-10-22_review-reanalysis.md).

## Statistical power and the smallest possible p-value
A rank test on n paired blocks cannot give a one-sided p below 1/2^n. With 6 pairs the floor is 0.0156, and after multiplying by 6 for Holm it is 0.094, so no result there can ever be called significant. Dropping data can turn "significant" into "not significant" without the effect changing: that is lost power, not a reversal. [0024](../journal/0024_2026-10-22_review-reanalysis.md).

## %globaltimer and %smid
Two PTX special registers a kernel can read. %globaltimer is a nanosecond-scale GPU timer (on this RTX 4070 Laptop it advances in steps of 1024 ns, measured in the G pre-check); %smid is the id of the SM the block runs on. Reading them at the start and end of every thread block gives the on-GPU timeline of a kernel, which Nsight and the host cannot show for time-sliced contexts.

## Gap detector
Inside the instrumented kernel one thread per warp reads %globaltimer every 64 loop iterations and keeps the largest gap between consecutive reads. A thread block that is descheduled mid-execution (context switch to another process) shows up as one gap far larger than the usual 2 microsecond gap. The threshold is 20 x the typical gap measured in a bg-alone cell (registered rule).

## Instrumentation overhead pre-check
Before interpreting a timeline you check that recording it did not change the thing recorded. G's first recording kernel was 1.6x slower because a branch inside the FMA loop broke its instruction scheduling; moving the timer read outside the inner loop brought the cost to 0.4% (journal 0029).
