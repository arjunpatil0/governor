# Response to reviews/2026-10-23_w5a_model_selection_protocol_review.md (Claude Sonnet 5.5, 2026-10-23)
1. [CHANGE] Design-based adaptation cells: APPLIED. Protocol section 3: first K cells of W in (session, order) that are unaligned with duty >= 0.5 at distinct clock labels, then fill; K = 3 primary, K = 1 sensitivity (a prefix of the K = 3 set); the same rule calibrates the training workloads. Tested (tests/test_w5a_greybox.py).
2. [CHANGE] Decision-focused metrics: APPLIED. Section 5: per held-out stratum the model picks max predicted tok/s with predicted miss <= 1% and predicted power + 1.96 sigma <= 60 W; REGRET (full best if the pick is observed-infeasible or absent) and FALSE-FEASIBLE rate of picks; false-feasible <= 5% is hard gate G1, REGRET_REL is in the 10%-of-best rule with an ABSOLUTE +0.10 margin (a ratio rule is degenerate near 0; flagged here as my choice).
3. [CHANGE] Asymmetric miss classification: APPLIED. False-feasible and false-infeasible reported separately (shares of all cells and of their true class), also for the 60 W power classification.
4. [ANSWER] (a)-(c): done as decided; scikit-learn HistGradientBoosting substituted for LightGBM (not installed), recorded in the protocol and plan addendum L.
5. [NOTE] Per-fold LOWO results: APPLIED; data/w5a/selection.md lists every fold next to the pooled result.
6. [NOTE] c14 in leave-one-condition-out: APPLIED (reported separately).
7. [NOTE] miss_frac_incl_abandoned used throughout.
8. [NOTE] Helper Ctrl+C elevated check: noted for the first W5b tuning session.
Registered before any fit: plan addendum L, commit 662d527 (protocol sha256 b56524c5...). Selection RESULT: NO candidate selected (all fail a hard gate); see journal 0047 and data/w5a/selection.md. Deviations I introduced and flagged: intervals for HGB/GP/MLP are inner-fold RMS residuals (no GP std / ensemble spread); GP is subset-of-data; predicted-overload p99 := 16.667 ms; CUSUM not evaluated offline.
