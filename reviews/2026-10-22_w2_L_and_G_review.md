# Review: part L results (data/w2_L_results.md, journal 0027) + revised G draft
Reviewer: Claude (cloud session). Status key: [NOTE] · [ADD] (report/journal only) · [APPROVE]

## Part L
1. [NOTE] Clean run: 90/90 cells, all layers on GPU, memory locked, 0 flags, identical greedy tokens in 10/10 blocks
   (shortest shared prefix 345). The real-engine knee (1500 MHz) falls between the two proxies, as journal 0014 anticipated.
2. [ADD] Main descriptive finding, from results.csv medians (board counter, W1 caveats):
   unlocked 101.1 tok/s at 92.0 W; 1500 MHz 97.2 tok/s (0.96) at 56.3 W; 1200 MHz 93.1 tok/s (0.92) at 49.9 W;
   1050 MHz 89.4 tok/s (0.88) at 47.1 W (the J/token optimum, 0.526 vs 0.915, −42.5%).
   So real 3B Q4_K_M decode at the knee keeps 96% of its speed and draws ~36 W less, a large share of a laptop's shared power
   budget. Put this table (power and tok/s next to J/token) in the L report and the journal.
3. [ADD] The lesson about proxies: the fp16 proxy put the knee at 1050 MHz, but the real engine needs 1500 MHz (Q4_K_M dequant
   adds compute per byte). A proxy can only bracket a real engine, so the governor's clock choice must come from measuring the
   actual workload (or a learned per-workload model), not from a proxy. This strengthens the case for the learned component (ADR-0002).
4. [NOTE] Open item resolved: the 10 "Reliability" cells are exactly the 10 llama_unlocked cells, the same unlocked-limit behaviour
   W1 found (journal 0005). Record it as resolved.
5. [NOTE] HL2's optimum (1050) is 12% slower. A governor would pick between 1200 and 1500 depending on the background's
   throughput target. That's a policy decision for W4–5, not a W2 result.

## G draft (revised)
6. [APPROVE] Review changes 1–3 are applied correctly: gap detector with a fixed G_thr rule, overlap redefined as concurrency
   outside preempted intervals, q/s measured only inside sliced spans with span counts reported, uninstrumented _off twins for
   P1–P3. The extra T1_alone/T4_alone cells are necessary. Approved for registration as written.
