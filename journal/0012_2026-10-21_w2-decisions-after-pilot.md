# 0012 — W2 design decisions after the pilot (what changed and why)
Date: 2026-10-21 · Phase: W2 (pre-registration draft) · Author: Claude Code (decisions by Arjun)
## Question
What does the W2 pre-registration change, given the pilot (journal 0011)?
## Belief going in
0004/0008: foreground wait follows rho·E[S²]/(2E[S]) for non-preemptive background slices; the plan was to test that on an unlocked GPU with an isolated-foreground baseline.
## What the pilot showed (journal 0011, data/pilot/w2/)
1. The "isolated" foreground baseline depends on clock state: at light load the GPU sat near 1500 MHz, and the first requests after idle ran at 210 MHz and queued for 0.17–0.37 s.
2. In one unregistered co-run cell (2 ms background slices) foreground latency was 0.40 ms p50 against a residual-wait prediction of 1.07 ms, did not depend on arrival phase within the slice, and background slices containing a foreground completion ran ~0.3 ms longer (replicated in two pilot runs).
## Decisions (Arjun, 2026-10-21)
1. Experiment A runs at a fixed SM clock of 1800 MHz and a fixed memory clock of 8001 MHz (admin, `-lgc`/`-lmc`), reverted in a finally block; any cell whose logged SM/mem clock leaves the target during the window is flagged. Reason: removes the DVFS confound in finding 1.
2. HA1 stays exactly as planned. A secondary "preemption characterisation" is added and explicitly marked as motivated by the pilot: phase independence (regress foreground wait on arrival phase), background slice stretch per foreground request versus foreground service time (estimate of the constant switch cost), a priority control (foreground normal vs raised priority on a subset), and a foreground-size factor (0.1, 1, 4 ms plus the ~9 ms B frame) with foreground slowdown versus background duty cycle for long work.
3. 2 s of foreground traffic per cell are warm-up and are excluded from all statistics (finding 1).
4. All predictions use realised slice durations (covers the +14.8% deviation of the 0.25 ms mem slice).
## Choices made while writing the yaml (mine; for review)
- 10 blocks for the primary A (not 5): a paired one-sided Wilcoxon with n blocks has minimum p = 1/2ⁿ, so n = 5 (0.031) can never pass Holm over six tests; n = 10 gives 0.001, as in W1.
- The secondary runs as a separate 10-block part, descriptive (bootstrap CIs, no multiplicity claim).
- Main-grid foreground priority is NORMAL. The pilot's co-run cell used a HIGH-priority foreground, so the priority control is how that difference is tested.
- Experiment B levels are fixed at 900/1200/1500/1800/unlocked; the Experiment C knee is added by a dated addendum before B runs, if not already there.
- HA1 gets an explicit failure classification (preempted_or_concurrent / scheduler_capped / other), evaluated in a stated order.
- Memory clock locked at 8001 in all W2 cells (W1 left it unlocked).
## Interpretation
If the pilot signature holds in the registered run, HA1 will be rejected and the finding becomes the preemption characterisation. The design keeps HA1 unmodified so that a rejection is a real test and not a retrofit.
## Setbacks / surprises
Writing the yaml exposed a statistical-power constraint (above) that the approved plan's 5 blocks would have violated.
## Next
Arjun reviews `experiments/w2_colocation.yaml` (uncommitted draft). After approval: commit it, then the prerequisites in its `implementation_prerequisites` (duty option in the DLL, `run.py`, `w2_analysis.py`), tests first, then Experiment C.

## Review of the draft (reviews/2026-10-21_w2_prereg_review.md) and changes applied before commit
All four [CHANGE] findings accepted; finding 5 added as a limitations line; finding 6 kept as is (SA4's 1 + d is descriptive).
1. HA1(i) now states OLS WITH intercept, equivalence test on the slope, intercept and its CI reported (a constant switch cost, pilot ~0.3 ms, would bias a no-intercept fit).
2. HB1's reference is the locked 1800 MHz cell, not unlocked: frames run at ~53% duty and the pilot showed the unlocked clock dropping at light load, so W1's continuous-load
   relative throughputs need not describe an unlocked frame. Predictions: service(L)/service(1800) = rel_W1(1800)/rel_W1(L); from data/w1_downclock_results.md
   (0.732/0.366, 0.732/0.488, 0.732/0.609) that is 2.00 at 900, 1.50 at 1200, 1.20 at 1500 for fma. HB2 is re-referenced the same way (L in {900, 1200, 1500} versus 1800, Holm over three). Unlocked is descriptive with the per-frame SM clock.
3. HC1: scipy zero_method="wilcox"; fewer than 6 blocks with a nonzero int4 − fp16 knee difference means INCONCLUSIVE; per-block knee table reported.
4. Overload rule added for B (fma service 8.86/0.488 = 18.2 ms at 1200 MHz and 8.86/0.366 = 24.2 ms at 900 MHz exceed 16.67 ms; 120 Hz overloaded from 1200): only miss fraction and gpu service time are interpreted there; latency percentiles are flagged non-stationary.
5. Limitations: a 10-cluster percentile bootstrap tends to be anti-conservative.
Why it matters: findings 2 and 4 would each have made a hypothesis fail or become uninterpretable for reasons unrelated to what it tests.
