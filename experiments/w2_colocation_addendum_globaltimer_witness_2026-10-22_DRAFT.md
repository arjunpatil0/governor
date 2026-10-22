# DRAFT addendum 3 to w2_colocation.yaml (Experiment G): witness blocks for all block-level analyses — NOT REGISTERED (proposal for the reviewer and Arjun; registration = the later commit that renames it, BEFORE any G data)
Date drafted: 2026-10-22 · Amends addendum 2 (experiments/w2_colocation_addendum_globaltimer_prerun_2026-10-22.md) · Motivated by the 15-cell smoke of the multi-gap kernel (journal 0030, data/w2_G_smoke_report*.md; smoke is not a result) · Changes no kernel, no cell, no data collection; analysis only.

## Finding that motivates it (smoke-grade, unlocked clocks, one block; reproducible in a minute)
With NO other process, the instrumented fma kernel at the harness grid (6 blocks per SM) shows logged gaps of about 260 us in a fixed share of its blocks. A controlled sweep of blocks per SM, bg kernel alone, 1.5 s each: 1, 2, 3 blocks/SM: 0 blocks with a gap >= G_thr; 4: 25%; 5: 40%; 6: 50% (the blocks beyond the first three per SM). In g_bgalone exactly 132,192 of 264,384 recorded blocks (50.0%) have a gap >= G_thr, median 267 us. So a block-level gap does not by itself mean that the context was switched out: blocks beyond the first three per SM are starved by the SM's warp arbitration while the earlier blocks run. Blocks 0-107 (blockIdx < 108, the first three per SM) had no gaps alone in every cell inspected. Review finding 6 expected the bgalone gap rate to measure other GPU contexts; it measures this arbitration instead.

## Proposal (replaces "all trusted blocks" in addendum 2 sections A-C)
- Every block is still recorded and the gap logs are kept. All block-level analyses (launch ON-sets and runs, q, s, OVERLAP (P6), PREEMPTED fraction (P7), G_thr from g_bgalone, the alone spans used for the sliced-span test) use WITNESS blocks only: blockIdx < 108 (3 x 36). Overflow/untrusted rule unchanged, applied to witness blocks.
- G_thr = 20 x the median block-mean read gap of the WITNESS blocks of g_bgalone (about 25 us in the smoke; the logging threshold stays 20 us, which is below it).
- The all-blocks view is also reported, labelled SECONDARY, with the arbitration artefact stated next to it.
- Instrument validity gate, fixed now: in g_bgalone the witness blocks' preempted fraction (gap >= G_thr) must be below 1%; otherwise the witness restriction does not isolate context switching and P6/P7 and q/s are reported but not interpreted.
- P7 is judged against that baseline as before (>= 1% in g_T4), now with a gap-free baseline for comparison.
- Predictions P1-P8 are unchanged in content.

## What the smoke showed with this restriction (not a result; unlocked clocks, one block, pre-check (iii) not judgeable)
bgalone witness blocks: 0 gaps >= G_thr in 132,192 blocks. Contended: preempted bg fraction 10-19% (R_2, T1, T4), q about 0.375 ms, s about 0.13 ms with 139 negative-s transitions of 3,498, and fg/bg block on-intervals that still overlap for hundreds of microseconds (g_T4: 5,230 of 43,200 witness fg blocks, 21% of them on the same SM). I read none of this as a prediction outcome. If it repeats on the locked-clock data, P4, P5 and P6 will not hold as written, and what they mean is for the reviewer.
