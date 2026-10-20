# Response to reviews/2026-10-21_w2_prereg_review.md
Responder: Claude Code (implementer). Review file not edited. Changes committed in b86d36e (yaml + journal 0012).

1. fixed (b86d36e): HA1(i) now specifies OLS with intercept, equivalence test on the slope, intercept and its CI reported.
2. fixed (b86d36e): HB1 reference is the locked 1800 MHz cell; predictions rel_W1(1800)/rel_W1(L) = 2.00 / 1.50 / 1.20 at 900 / 1200 / 1500 MHz for fma (checked against data/w1_downclock_results.md); HB2 re-referenced to 1800 (Holm over three levels); unlocked reported descriptively with the per-frame median SM clock; frame sizes unchanged.
3. fixed (b86d36e): HC1 uses zero_method="wilcox", is INCONCLUSIVE with fewer than 6 nonzero-difference blocks, and reports the per-block knee table.
4. fixed (b86d36e): overload rule added; I recomputed 8.86/0.488 = 18.2 ms and 8.86/0.366 = 24.2 ms, matching the review. At overloaded levels only miss fraction and gpu service time are interpreted; latency percentiles are flagged non-stationary.
5. fixed (b86d36e): limitation line added (10-cluster percentile bootstrap tends to be too narrow).
6. noted: SA4's 1 + d reference line stays descriptive, unchanged.
