# PAPER_MAP: claim -> evidence (updated at the end of W2, 2026-10-22)
Rule (CLAUDE.md, phase-end step 5): every claim names its results file, journal entry and commit. "Not supported" claims are included; they are results too. Citations to papers are NOT listed here until verified to exist.

| # | Claim | Status | Evidence |
|---|---|---|---|
| 1 | A compute-bound foreground's service time scales with 1/SM-clock (ratios 1.999 / 1.500 / 1.203 at 900 / 1200 / 1500 MHz vs 1800 MHz) | supported (HB1) | data/w2_B_results.md; journal 0016; c51b499 |
| 2 | Locking the clock below the compute-bound foreground's slack raises its deadline-miss fraction (900 and 1200 MHz; 10/10 blocks, Holm 0.0029) | supported without background; not testable with the memory background | data/w2_B_results.md; journal 0016 |
| 3 | The foreground's extra wait under time-slicing is proportional to the background's residual slice | NOT supported (slope 0.013 vs 1; 17% of cells within 25%) | data/w2_A_results.md; journal 0020; ea8546a |
| 4 | The wait is capped: plateau tau about 0.26 ms, independent of slice length beyond that and of arrival phase | supported, replicated on fresh seeds (G P1, P2); fine-grid tau 0.2580 ms, 90% CI [0.2564, 0.2602] (post-hoc refit) | data/w2_A_secondary_results.md; data/w2_G_results.md; data/w2_G_posthoc.md; journals 0023, 0032, 0033 |
| 5 | Foreground priority does not change the observed wait | supported (SA3, differences within +/-0.02 ms) | data/w2_A_secondary_results.md; journal 0023 |
| 6 | The ripple in the wait curve (dips near 0.35-0.40 and 0.80-0.85 ms) | NOT replicated (P3); a feature of A's realisation | data/w2_G_results.md; journal 0033 |
| 7 | GPU time-slice quantum q = 0.374 ms, switch gap s = 0.148 ms (witness blocks, %globaltimer, 1.024 us resolution) | measured; registered ranges (0.5-0.9; 0.2-0.3 ms) not met | data/w2_G_results.md; journals 0032, 0033; 0f78435 |
| 8 | The context switch is nearly synchronous across SMs (spread 1-5 us; no staggered switch) | post-hoc finding | data/w2_G_posthoc.md section 1c; journal 0033 |
| 9 | Apparent fg/bg concurrency in block-level timelines is probably a block-edge measurement artefact (0% of overlaps between two interior intervals) | post-hoc, consistent with but not proven; registered P6 did not hold and the rule reports a finding | data/w2_G_results.md; data/w2_G_posthoc.md sections 1a-1e; journal 0033 |
| 10 | Block-level gaps beyond 3 blocks per SM are intra-SM arbitration, not context switches (bg alone: 50% of blocks with ~267 us gaps at 6 blocks/SM, 0% at 1-3) | measured (smoke and full-run all-blocks view); mechanism untested | journal 0030; data/w2_G_smoke_report_allblocks.md; data/w2_G_results_allblocks.md |
| 11 | Decode proxy knee depends on the kernel: fp16 proxy 1050 MHz, int4 proxy unlocked (proxy artefact) | measured; int4 not used in governor claims | data/w2_C_results.md; journal 0014; f6f61ec |
| 12 | llama.cpp Q4_K_M decode (Llama-3.2-3B) knee 1500 MHz, energy optimum 1050 MHz at 0.526 J/token vs 0.915 unlocked; 97.25 tok/s at 56.3 W (1500 MHz) vs 101.1 tok/s at 92.0 W (unlocked) | measured, one model, batch 1 | data/w2_L_results.md; journal 0027; 47a64be |
| 13 | A proxy brackets a real engine; the clock policy must be measured on the actual workload | lesson from claims 11-12 | ADR-0002; journals 0014, 0027 |
| 14 | Instrumenting with %globaltimer/%smid changed fg-alone latency by 1.2% and the R2 wait by 0.006 ms in the full run (pre-check (iii) PASS) once the recording loop is branch-free; a branch inside the FMA loop cost 1.6x | measured | data/w2_G_results.md; data/w2_G_prechecks.md; journal 0029 |
