# Review: draft addendum 3 (witness blocks), smoke findings, decisions (journal 0030, STATUS)
Reviewer: Claude (cloud session). Status key: [CHANGE] before registering · [AGREE] · [NOTE]

## Overall
Good catch, and good method: the blocks-per-SM sweep (0/0/0/25/40/50%) turned "gap = suspension" from an assumption into a tested
claim, and found it false for blocks beyond the third per SM. Restricting block-level analysis to witness blocks is the right fix,
and keeping every block recorded means nothing is lost. Register addendum 3 with three additions.

## Findings
1. [CHANGE] Verify the witness set instead of assuming it. "blockIdx < 108 = the first three blocks per SM" depends on the block
   scheduler's placement, which isn't guaranteed. Add to the validity gate (computed per cell from the recorded %smid):
   every SM hosts exactly 3 witness blocks, and in g_bgalone the witness preempted fraction is < 1% (as drafted). If placement
   differs, define witnesses data-driven per launch as the 3 earliest-starting blocks on each SM, a rule fixed now.
2. [CHANGE] Apply the witness restriction to the FOREGROUND as well, and define "fg block executing" as its on-intervals
   (span minus its own logged gaps ≥ G_thr). The fg kernels also run 6 blocks/SM, so non-witness fg blocks have the same
   arbitration gaps. Make sure OVERLAP in P6 compares witness-fg on-intervals with witness-bg on-intervals only.
3. [CHANGE] Add an arbitration-free control so any concurrency claim can be checked: g_T4_3bpsm, the T4 cell with BOTH fg
   and bg kernels at 3 blocks/SM (every block is a witness; the sweep shows no arbitration gaps there), plus g_bgalone_3bpsm
   for its G_thr/gate. +2 cells (17/block, 170 total). Pre-state: if P6 fails in the main cells, concurrency is only reported as
   a finding if it also appears in g_T4_3bpsm. Different-context work overlapping in time on separate SMs (79% of the smoke's
   witness overlaps were on different SMs) would be an extraordinary result for a GeForce part without MPS, so it needs this
   control before anyone believes it.
4. [AGREE] Decision 2: keep P4, P5, P6 exactly as written. The smoke is unlocked, one block, and explicitly not a result.
   Changing predictions after seeing it would undo the pre-registration. If they fail on locked data, report that they failed.
   The smoke hints (q ~0.375 ms, s ~0.13 ms) are already recorded in journal 0030 with their timestamp, which is enough.
5. [AGREE] Decision 3: 1–2.5 h is fine, plus a few minutes for the two control cells.
6. [NOTE] The arbitration starvation itself (blocks 4–6 per SM stalled ~267 us while blocks 1–3 run, in the plain single-context
   kernel) is a small micro-architectural finding of its own, probably the warp scheduler favouring older warps when 48 warps compete
   for issue. It doesn't affect any earlier wall-clock result, but it does mean per-block "service time" isn't uniform within a kernel.
   Log it as an open observation; a later Nsight Compute warp-state check could confirm the mechanism. Not in scope now.
7. [NOTE] R0.5's 38% coverage is acceptable under the recorded-interval rule. Report P6/P7 per m with their coverage.

## Order
Apply 1–3 to the draft → register addendum 3 (rename + commit) → kernel/design change for the 3-bpsm cells test-first → re-smoke
the two new cells → full run.
