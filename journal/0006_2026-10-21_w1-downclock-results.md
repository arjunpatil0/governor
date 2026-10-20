# 0006 — W1 downclock sensitivity: results and what they mean for the governor
Date: 2026-10-21 · Phase: W1 · Author: reviewer (results by Claude Code, e9714d9)
## Belief going in (pre-registered, experiments/w1_downclock.yaml)
H1: memory-bound kernels lose less throughput than compute-bound ones as the SM clock drops.
H2: energy per unit work of memory-bound work falls below unlocked at some locked level.
## What happened (data/w1_downclock_results.md, 120 cells, 10 blocks, 7 flagged)
- H1 supported 5/5 levels (Holm p 0.0049 each). At 1200 MHz: mem keeps 0.993 of throughput, fma keeps 0.488.
- H2 supported 5/5; best mem relative energy/work 0.649 at 1200 MHz. Counter- and sample-based energy agree.
- Exploratory: mem vs fma relative energy/work differs only at 600/900 MHz; at ≥1200 MHz fma is also ~0.68–0.70.
- mem throughput saturates near 1200 MHz (≈230 GB/s); below that it becomes clock-limited (0.81 at 600).
## Interpretation
1. The energy saving is mostly "the unlocked boost point is inefficient for any kernel", not something
   specific to memory-bound work. The memory-specific result is the *throughput* side: for memory-bound work
   the clock can drop to the knee (~1200 MHz here) almost for free.
2. On a laptop that is the useful quantity: at 1200 MHz mem draws 37.0 W vs 57.7 W unlocked for the same work rate,
   ~20 W of shared budget freed with no throughput loss.
3. The knee is set by the kernel's arithmetic intensity (roofline). Real LLM decode has more compute per byte than
   a streaming copy, so its knee will be higher; must be measured, not assumed.
## Setbacks / surprises
- **Design implication found here:** the SM clock is device-wide. Locking it for a memory-bound background job also
  slows a compute-bound foreground (fma keeps only 0.488 at 1200 MHz). Clock locking is therefore not a per-process
  knob; it is only safe when the foreground is idle, light or itself memory-bound, or it must be time-multiplexed
  with foreground phases. W2 must measure this directly.
- Single laptop, two synthetic kernels; nothing yet about real decode or a real game.
## Next
W2: residual-wait model + fg/bg grid, adding (a) a decode-like background with measured knee and
(b) the effect of a device-wide clock lock on a compute-bound foreground.
