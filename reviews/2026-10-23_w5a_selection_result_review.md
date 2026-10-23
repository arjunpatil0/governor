# Review: W5a model selection, registered run (data/w5a/selection.md, addendum L, commit 0593f8e)
Reviewer: Claude (cloud session). Status key: [DECISION] · [CHANGE] · [NOTE]

## Overall
"No candidate passed the hard gates" is a legitimate, reportable result of the registered protocol. Running it once as registered,
not re-running, and stopping to ask was correct. The diagnostics are convincing: the failures come from the protocol's target and
interval SHAPE meeting this data, not from the models being useless (HGB, GP and MLP had 0 false-feasible picks).

## Decision: Option A, with five conditions
Option A is acceptable because the confirmatory claim does NOT live in W5a. Model selection is a development step; the claim is tested
in W5b on the held-out 8B and on fresh evaluation blocks, which no part of this redesign touches. So a second, post-hoc selection run
doesn't contaminate the confirmatory test, PROVIDED:
1. Addendum M is written and committed BEFORE the re-run and lists every method choice, including the five deviations already
   introduced in the first run (OOF intervals, GP subset + seed, overload p99 = 16.667 ms, CUSUM not evaluated, regret margin absolute
   +0.10 vs ratio). Those were method choices made during implementation without sign-off. Each must be either adopted explicitly in M
   or reverted, and the first run's report must say they were unregistered.
2. Targets redesigned for the decision the controller makes:
   - feasibility as a CLASSIFIER: P(miss_incl_abandoned <= 1%), scored by the false-feasible rate (hard gate) and false-infeasible
     rate at the controller's own threshold. This replaces the p99-magnitude target, which a backlog makes meaningless (p99 in
     seconds = infeasible; the value of the tail carries no decision information). Keep the in-range p99 error (non-backlog cells) as a
     reported secondary;
   - tok/s as a two-part target: P(tokens > 0) plus log(tok/s | tokens > 0), so intervals are RELATIVE and scale with the
     workload's 6–14x throughput range;
   - power as before.
3. Intervals: conformal (split / cross-conformal) intervals computed in the transformed space (log tok/s), per fold, with the
   90–98% coverage gate unchanged. State the method exactly.
4. Latency: measure the REAL decide path (one batched predict over the candidate grid per decision, as the controller calls it), and
   tie the bound to the loop the model actually runs in. The clock/pacing decision runs in the SLOW loop (0.5–1 s; ADR and plan), so a
   bound of e.g. ≤ 10 ms p99 for that call is defensible. This is a CHANGED requirement: declare it in M with that rationale, and report
   every candidate against both the old 1 ms and the new bound. The per-frame fast loop (token release, learned guard) must not call the
   heavy model; state that.
5. ONE re-run only, and the fallback fixed NOW in M: if no candidate passes the redesigned gates, d'B in W5b uses the grey-box structure
   with the current ModelController (option B), the safety shield unchanged, and the report states that model selection did not
   discriminate. No third round.

## Other notes
6. [NOTE] The false-feasible gate rests on very few picks (grey-box 5/10; others 0–8). Report the picks with an exact 95% binomial CI;
   a 5% gate on 10 picks means a single failure fails. Keep the gate, but report the uncertainty.
7. [NOTE] Only 8 of 18 strata contain any observed-feasible candidate, so regret is undefined or degenerate in the other 10.
   Compute regret on the 8 feasible strata only, and report the count. (The heavy conditions c11/c14 at 60 Hz are often entirely
   infeasible. That is a property of the plant and itself worth a sentence in the report.)
8. [NOTE] Option C (more W5a data) is rightly not recommended: the failure is shape, not sample size.
9. [NOTE] The Ctrl+C fix still needs its first elevated check at the start of W5b tuning.
