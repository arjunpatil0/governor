# STATUS (overwritten at every stop)
Updated 2026-10-23 - Phase: W4-5. Protocol registered (plan addendum L, 662d527); grey-box predictor written test-first; W5a selection RUN AS REGISTERED: NO candidate passes the hard gates. Stopped for review of the result.

## Result (journal 0047, data/w5a/selection.md)
- G (grey-box): false-feasible 5/10 picks (gate 5%), tok_s coverage 72%. HGB/GP/MLP: 0 false-feasible but tok_s coverage 73-77% and latency 1.9-15.6 ms (gate 1 ms). Only G meets 1 ms.
- Why: the p99 target is dominated by a backlog tail (15% of non-overloaded cells above 200 ms, up to 3.2 s) that no model predicts; tok/s differs 6-14x between workloads, so one pooled sigma per target miscalibrates (1B fold coverage 16-30%).
- Nothing selected, no pre-fixed fallback. Nothing re-run, nothing changed after seeing results.

## Waiting for
1. Reviewer + Arjun: choose (A) addendum M fixing the protocol shape, then a labelled second run; (B) accept the negative result and keep ModelController for d'B; (C) more data (not recommended). Details in journal 0047.

## Risks / not verified
- Helper Ctrl+C untested elevated (check at the first W5b tuning session). d'B never simulated. HW7 staleness data not analysed. W5b not started.

## Notes
- Do NOT rebuild the driver exe (bb875fbc) or edit registered files. scikit-learn 1.4.0 used; LightGBM not installed (decision c).
