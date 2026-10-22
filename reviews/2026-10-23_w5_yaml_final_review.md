# Final review: W5 governor pre-registration, draft 3b (experiments/w5_governor.yaml, uncommitted)
Reviewer: Claude (cloud session). Status key: [BLOCKER] fix before commit · [CHANGE] · [NOTE]

## Overall
Close to ready. The statistics now work (10 evaluation blocks, Holm over 3, the floor reachable), S5 tests the real claim, the
non-inferiority comparators are fixed, and the feasibility gate and c0 definitions are tight. Four problems would make the comparison
unfair or the stages impossible to run in order, and one piece of withdrawn text survives. All are edits to the draft; no new data needed.

## Findings
1. [BLOCKER] Stage-order contradiction: W5a needs c0 before c0 exists. W5a's foreground costs are "light 0.7 x c0, nominal c0,
   heavy 1.3 x c0", but c0 is chosen by HW0 in the W5b TUNING blocks, which come after W5a and model selection. Fix: give W5a absolute
   nominal cost levels that span the whole c0 search range and the S1 steps, e.g. {5, 7, 9, 11, 14} ms nominal (covering 0.7 x 7 ... 1.3
   x 11), plus the S1-style varying cost. Then the selected model has seen every cost W5b can use, whichever c0 the gate picks.
2. [BLOCKER] g'B is restricted to ALIGNED settings, which makes it a straw man at heavier frames. Smoke 3: aligned admits 0 tok/s
   once the measured frame time exceeds ~6.57 ms, and the S1 heavy phase (1.3 x c0) crosses that boundary at the likely c0. A static
   baseline that can't choose unaligned pacing will lose for a reason unrelated to learning. Fix: g'B (and so eB) = the best
   scenario-agnostic static over the FULL pacing space (aligned guard x duty AND unaligned duty) x clock.
3. [BLOCKER] Unequal information between controllers. d'B's model is selected on W5a data from three workloads (1B, 3B, other family),
   but g'B and c'B constants are tuned on the 3B tuning blocks only. A reviewer would say the static lost because it saw less. Fix: tune
   g'B/eB/c'B on the same known workloads the model saw: either from the W5a table (scenario-agnostic over 1B, 3B and the other family) or by
   running the tuning blocks over all three known workloads. Then S5 compares controllers with equal knowledge and only the ability to
   adapt differs.
4. [BLOCKER] HW2 pairs "over cells feasible for both", which can hide infeasibility. A controller that often breaks the SLO or budget
   drops those cells and can still win on tok/s in the rest. Fix: in HW2, an infeasible cell counts as 0 tok/s (the background's output
   has no value if the frame SLO or the budget is broken), and state it. Additionally, d'B earns its place only if it also passes HW1
   (≥ 90% feasible, mean miss ≤ 1%) in every primary scene.
5. [CHANGE] Remove the withdrawn claim everywhere. The d'B description still says "(the smoke showed that guard 0 fails on hardware)",
   inputs_from_earlier_work.hardware_smoke still says smoke 1 "showed that tokens overrun ... with guard 0", and HW4 refers to "the smoke
   finding (token overrun with guard 0)". Journal 0042 withdrew these. Replace them with the corrected statement (driver bug, fixed; the
   learned guard absorbs estimation error such as staleness after clock changes).
6. [CHANGE] Make the 8B load pre-check timing consistent. held_out_workload says it is checked "in the first tuning block", but the
   fallback changes W5a's workload list, so it must happen BEFORE W5a (stage_order already says so). State "load pre-check before W5a,
   recorded in an addendum".
7. [CHANGE] Before W5a, explain the admission mismatch: ~5% of aligned starts have logged estimate + guard > time to the next
   arrival, so the fit test should have refused them, yet they started. The driver is the actuator for every W5 cell, so check offline
   from the smoke-3 CSV whether the logged estimate is the one the fit test used (logging lag vs a real admission bug). It's cheap and
   avoids a repeat of the smoke-2 situation.
8. [NOTE] Total hardware time ≈ 5 h (W5a) + ~11 h (W5b) in sessions of ≤ 3 h. The session-break rule is good. Plan the calendar so
   the configuration (driver, OS updates, Avast definitions if possible) stays identical. A Windows or driver update mid-study would
   split the blocks.
9. [NOTE] The unexplained helper reset errors are handled safely; keep logging them. No action.

## Decision
Approve for commit after 1–6 are applied (7 before W5a starts). Commit with a dated note that lists these changes.
