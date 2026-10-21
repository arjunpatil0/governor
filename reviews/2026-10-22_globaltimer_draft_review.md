# Review: Experiment G draft (experiments/w2_colocation_addendum_globaltimer_2026-10-22_DRAFT.md) + HL3 reading
Reviewer: Claude (cloud session). Status key: [CHANGE] edit before registering · [AGREE] · [NOTE]

## Overall
The structure is right: an honest trigger status, pre-checks with a failure path, predictions written before data, and a fresh-seed
replication. Three changes are needed, because as written P6 and the q definition would mis-measure exactly what G exists to see.

## Findings
1. [CHANGE] Block start/end stamps can't tell preemption from concurrency, so P6 conflicts with P7. Each bg block in an m = 2 ms
   slice is resident for roughly the whole slice (the grid fills the GPU at once). If a 0.1 ms fg kernel preempts the bg context mid-block,
   the bg block's [start, end] interval contains the fg blocks, and P6's "any fg block interval intersects a bg block interval" counts
   that as OVERLAP even though execution was time-sliced. P7 expects precisely those cases. Fix: add a gap detector inside every block.
   Each block (one thread per warp is enough) reads %globaltimer in its main loop and keeps the largest gap between consecutive reads,
   with that gap's start timestamp (two more fields per record; optionally the top-k gaps). A preempted block shows a gap ≥ the
   switch time; an uninterrupted block shows only loop-iteration-sized gaps. Redefine:
   - preempted interval of a block = its largest gap if gap > G_thr (G_thr fixed now, e.g. 20× the median loop-iteration gap,
     measured in the bgalone cell);
   - OVERLAP (concurrency) = an fg block executing while a bg block is resident AND inside no preempted interval of that bg block.
   P6 then means "no fg block executes during a bg block's non-gap time"; P7 becomes "bg blocks show a gap that contains fg blocks".
   The overhead pre-check (iii) must cover the gap-detector reads.
2. [CHANGE] Define q only where both contexts have pending work. In T1/T4, fg arrives Poisson at 10–16% load, so most bg "runs" end
   because no fg work exists, not because the quantum expired. Define q as the median length of a context's run INSIDE an fg kernel's
   on-GPU span whenever that span exceeds its alone service time by > 2s (the kernel was sliced), and report how many sliced spans
   contributed. Same restriction for s. Report the unrestricted run lengths separately, descriptively.
3. [CHANGE] Keep the capped-wait replication (P1–P3) uninstrumented. As drafted, R_m is instrumented and only R_2_off is a control,
   so a failed P1 could be blamed on instrumentation. Add R_m_off for m = 0.5, 1, 8 (R_2_off exists): +3 cells, 12 per block, ~+12 min.
   P1–P3 are evaluated on the _off cells; the instrumented R_m serve the timeline and the overhead check (each R_m vs R_m_off).
4. [NOTE] P4's [0.5, 0.9] range is fine. Keep the ripple-period reading (~0.45 ms) labelled post-hoc, as drafted.
5. [AGREE] HL3: comparing greedy tokens over the shared prefix is the right reading when a fixed time window yields different token
   counts. Add: report the shared-prefix length per cell, and require ≥ 64 shared tokens for the check to count.

## Order and housekeeping
Agree: run the llama.cpp validation first. But the clean-tree guard will refuse it while the G draft is untracked. Either add the
draft to .git/info/exclude (as with the llama.cpp draft) or commit it under its _DRAFT name with "NOT REGISTERED" in the header;
registration is then the later commit that renames it. Also commit STATUS.md (currently modified).
