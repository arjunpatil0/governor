# 0033 — Experiment G: interpretation (post-hoc mechanism analysis) and W2 close
Date: 2026-10-22 · Phase: W2 · Author: Claude Code · Review: reviews/2026-10-22_G_results_review.md · Response: reviews/2026-10-22_G_results_response.md · Evidence: data/w2_G_results.md (registered, unchanged verdicts), data/w2_G_posthoc.md (post-hoc), journal 0032
Everything labelled POST-HOC below was chosen after seeing the registered results. Registered verdicts are as computed in journal 0032.

## Registered verdicts (unchanged)
P1, P2, P7 held; P3, P4, P5, P6, P8 did not hold; for P6 the registered rule reports concurrency "as a finding" because the 3-blocks-per-SM control overlaps too.

## Post-hoc re-analysis (data/w2_G_posthoc.md)
1. **Staggered switch: not supported.** Across 36 SMs the outgoing context's last on-time spreads by 1-5 us and the incoming first on-time by 1-4 us (per switch, p50 to p90, all three cells). The cross-SM overlap is negative (-102 to -297 us at p50): every SM finishes the outgoing context before any SM starts the incoming one. Same-SM overlaps in the merged-run view: 0 of 5.2M SM-switches. So the context switch looks nearly synchronous across SMs, with a per-SM gap of about 103 us (control), 148-161 us (T4), 133 and 298 us (T1 bg->fg, fg->bg).
2. **The block-level overlaps are whole runs sitting inside one block's first or last interval.** Overlap duration p50 287 / 365 / 388 us (T1 / T4 / control), about one quantum. Overlap midpoints lie 143-195 us from the nearest run boundary (control: 0.1% within s against 83% for uniformly placed points). All same-SM overlaps (4,644 / 11,762 / 2,621) cover an entire run of one context, within 30 us of an interval edge of one block. New test (not in the review): 0.0% of 685,000 overlap pairs involve two interior on-intervals; a bg interior interval takes part in under 0.4% of pairs (control 0 of 94,345).
3. **Reading.** This is what a block-edge measurement artefact would produce: a block's on-interval runs from the earliest warp start to the latest warp end, gaps are logged from thread 0 only, so stalls of the other warps before thread 0 starts or after it finishes are invisible. It is consistent with the data, not shown: per-warp times were not recorded. It is not what concurrency would produce, which would also overlap interior intervals. I therefore do not claim concurrency. The registered line stays "P6 did not hold; control overlaps; rule reports a finding"; the interpretation is that the finding is probably a property of the on-interval definition at block edges.
4. **tau.** Fine grid (0.2 us): tau = 0.2580 ms, 90% CI [0.2564, 0.2602]; the degenerate CI was a 10 us grid artefact. P2 verdict unchanged.
5. **q and s.** q in T4 is 0.3748-0.3779 ms in every block (about 365 x the 1.024 us timer step); s pooled 0.148 ms. With the review's relation 2 + 2s/q = 2.79 (arithmetic checked), between A2's observed 2.65 (1 ms fg) and 2.91 (4 ms fg): a post-hoc reading in which the inputs for P4/P5 were wrong (A2's 0.243 ms is per-intrusion stretch, probably two switches) and the slowdown relation holds. Caveat from me: q and s use the same on-interval definition as finding 2, so if first/last intervals are extended by the artefact, s is biased low and q high. Not re-derived.
6. **P8.** p50 0.207 / 0.210 / 0.271 / 0.268 ms, p99 0.659 / 0.880 / 1.006 / 1.025 ms (m = 0.5/1/2/8). The R0.5 value (no bg block preempted) is the submission floor; the p99 mostly measures the host/WDDM submission path. Not interpreted as GPU arbitration.
7. **P3.** The ripple did not recur on fresh data: a feature of A's realisation, dropped from the mechanism story.

## What W2 supports (traceable to files; see docs/PAPER_MAP.md)
Compute-bound foreground slows in proportion to the clock (HB1); the residual wait on a co-run foreground plateaus at about 0.26 ms and this replicated on independent seeds (A2 exploratory fit, then G P1/P2); decode knees depend on the engine (proxy fp16 1050 MHz, llama.cpp Q4_K_M 1500 MHz, energy optimum 1050 MHz 0.526 J/token vs 0.915 unlocked); time-slice quantum about 0.375 ms with a synchronous switch gap of about 0.1-0.15 ms (measured with %globaltimer, witness blocks); the "preempted_or_concurrent" ambiguity from A is narrowed: block-edge artefacts probably account for the apparent concurrency.

## Open (follow-ups, not in W2)
- Why blocks beyond three per SM are starved (Nsight Compute warp-state check).
- Whether the block-edge artefact is real: record per-warp start/end times, or re-derive q, s and P6 on interior intervals only.
- Why the control has overlaps at all in locked-clock data while the unlocked smoke showed none.
- Environment limitation: WhatsApp/Discord ran idle in W1-W2 (journal 0032).
