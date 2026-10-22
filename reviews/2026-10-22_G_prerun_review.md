# Review: Experiment G before the full run (journal 0029, data/w2_G_prechecks.md, STATUS at 8857c4e)
Reviewer: Claude (cloud session). Status key: [BLOCKER] fix before the full run · [AGREE] · [NOTE]

## Overall
The pre-checks did their job: they found a 1.6x instrumentation cost and it was fixed (chunked branch-free loop, 0.999–1.004x).
The timebase check is convincing, and both incidents were logged honestly. But one design flaw would make P4, P5 and P6 unmeasurable or
falsely failed, and it has to be fixed (dated addendum, before any data) first.

## Findings
1. [BLOCKER] Recording only the LARGEST gap per block loses every other preemption, and the analysis needs them.
   - Every kernel here is a single wave: grid = 36 SMs x 6 blocks x 256 threads = full occupancy (w2_kernels.cu: blocks =
     g_sms * blocks_per_sm). So every block, fg or bg, is resident for the whole kernel. During fg/bg alternation no block of
     either context STARTS: the resident blocks are suspended and resumed. The q/s definition ("a run = maximal stretch with no
     block of the other context starting") then sees no runs at all; the alternation exists only as gaps inside resident blocks.
   - A bg block in an 8 ms slice is preempted ~1.6 times on average by the 200 Hz fg stream. In T4 (4 ms fg, q ~0.5 ms expected)
     both the fg and the bg blocks are suspended several times each. With only the largest gap stored:
     (a) q and s can't be reconstructed (P4, P5 unmeasurable);
     (b) P6 can FALSELY FAIL: an fg block running inside a bg block's second-largest (unrecorded) gap looks like concurrency.
   Fix: log every gap above a fixed logging threshold, not just the maximum. Per block (warp 0's lane-0 reads are enough, since a context
   switch suspends the whole block), store up to K gaps as (start, length) pairs, with logging threshold 20 us (≈10x the 2 us typical read
   gap; ≤ the ~41 us G_thr, which the analysis still applies afterwards), plus an overflow counter. K = 8 for the 0.1 ms fg stream and K = 32
   for bg and the T1/T4 fg kernels is likely enough; report overflow counts, and treat any block with overflow as untrusted for P6.
   Redefine in the addendum: a context's run = an on-interval between consecutive logged gaps of its resident blocks (aligned across
   blocks, since a context switch suspends all of them together); q = median on-interval length inside sliced fg spans;
   s = (fg gap length − the overlapping bg on-interval)/2, or another explicit formula fixed before data.
2. [BLOCKER] The bg record buffer covers only part of the window (~1.9 s at m = 0.5, ~7 s at m = 2), and later slices run the plain
   kernel, which has no gap detector. Fg records span the whole window. Pre-state that P6/P7 and the q/s analysis use only the interval
   where BOTH contexts are recorded, and report that interval per cell. Or enlarge the buffer so it covers the window (an 8 GB card
   can hold ~100–200 MB of records). Whichever is chosen, state it before data.
3. [BLOCKER] Write the P1–P8 analysis code BEFORE the run, test-first on synthetic timelines, as every earlier part did and as the yaml's
   analysis section requires ("committed before the first full run"). A synthetic timeline with alternating suspend/resume gaps would
   have exposed finding 1, so this is the check that catches design errors cheaply.
4. [AGREE] Decision 1: add g_baseline_off as a 15th cell (one-line dated addendum) so pre-check (iii) can be judged as registered.
5. [AGREE] Read interval 64 (2 us typical gap, ~1 us timer steps) and the G_thr rule as median over blocks of duration / reads: fine
   given the ~243 us switch gap. Note in the addendum that G_thr ≈ 41 us is ~20x the logging resolution.
6. [NOTE] Report the gaps seen in the bgalone cell: with no fg, any bg gap > G_thr comes from another GPU context (e.g. the Windows
   desktop compositor under HAGS). That's the baseline preemption rate P7 should be compared against, and a small finding in itself.
7. [NOTE] Run time 1.5–2.5 h (from one smoke) is fine. Schedule it when the laptop can sit untouched.

## Requested order
Addendum (findings 1, 2, 4 and the run/q/s redefinition), committed → kernel change test-first → analysis code test-first on
synthetic timelines → smoke (confirm overflow counts are ~0 and coverage matches the stated interval) → full run.
