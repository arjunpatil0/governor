# Review: Experiment G results (data/w2_G_results.md, journal 0032, STATUS at 3137cff)
Reviewer: Claude (cloud session). Status key: [BLOCKER] before any interpretation is written · [RE-ANALYSE] existing data · [NOTE]

## Overall
A clean, well-instrumented run. Overhead check passed (1.2%, 0.006 ms), the witness gate passed (0.000%), there was no overflow, and
verdicts were applied as registered. Two results are strong. P1 and P2 are the first INDEPENDENT confirmation of the capped-wait plateau
(fresh seeds, uninstrumented: 0.226/0.262/0.295/0.304 ms vs A's 0.226/0.255/0.287/0.298). And q and s are remarkably crisp. The one
result that must NOT be written up yet is "concurrency", for the reasons below.

## Findings
1. [BLOCKER] "Concurrency reported as a finding" follows the registered rule, but the data point to a more mundane mechanism that has to
   be ruled out before the word "concurrency" appears in any interpretation:
   - Overlaps occur ONLY where context switches happen inside sliced fg spans: T1 and T4 (and the T4 control). The R cells have
     n_sliced = 0 and exactly 0 overlaps across 6.9M fg blocks. If the two contexts truly ran concurrently, short fg kernels landing
     in long bg slices should overlap too.
   - ~99% of overlaps are on DIFFERENT SMs.
   - 1,128 "negative-s" transitions: runs overlapping AT the switch boundary.
   Leading alternative: a STAGGERED context switch. The save/restore proceeds SM by SM (or per TPC/GPC), so at each boundary the
   incoming context starts on SMs that have already switched while the outgoing context is still finishing on others. That gives
   different-SM overlaps bounded by the stagger width, clustered at run boundaries. That's time-slicing with a non-atomic switch,
   not concurrent sharing. Re-analyse on the local rec files (exploratory, labelled post-hoc):
   (a) overlap duration distribution, compared with s (0.148 ms) and q (0.374 ms);
   (b) position of each overlap relative to the nearest run boundary: concentrated within ~s of boundaries → staggered switch;
       spread through runs → genuine concurrency;
   (c) per-transition stagger: across SMs, the spread of the outgoing context's last on-time and the incoming context's first
       on-time; compare the stagger width with the overlap durations;
   (d) inspect 10–20 SAME-SM overlaps by hand (2,617 in the control): two contexts' blocks executing on one SM at once would be the
       most surprising claim of all, so check read cadence, timestamp attribution and gap-threshold edge cases on those blocks.
   Report the registered verdict exactly as computed ("P6 did not hold; the control overlaps, so the rule reports it as a finding"),
   and put the mechanism analysis next to it. Don't assert concurrency unless (b) and (c) show overlaps spread through runs, well beyond
   the boundary stagger.
2. [RE-ANALYSE] The degenerate tau CI [0.260, 0.260] is almost certainly a GRID artefact: every tau so far is a multiple of 0.01 ms
   (0.260, 0.270, 0.280), so the fit searches a 10 us grid and every bootstrap resample lands on the same grid point. Report it as
   "0.26 ms, uncertainty below the 0.01 ms grid", or refit with a finer grid or a continuous optimiser (as a labelled sensitivity,
   registered fit unchanged).
3. [NOTE] P4/P5 failed, but the measured q and s fit the mechanism better than the predictions did. q = 0.370–0.377 ms in every
   block and both fg sizes (≈365 x the 1.024 us timer step) looks like a fixed hardware/driver time-slice. With the measured values,
   the slowdown relation 2 + 2s/q = 2 + 2(0.148)/0.374 ≈ 2.79, right between A2's observed 2.65 (1 ms fg) and 2.91 (4 ms fg). So the
   relation looks right, and the inputs for P4/P5 were wrong (SA2's s0 = 0.243 ms is per-intrusion stretch, likely about two switches,
   not one switch). That's a post-hoc reading; label it so.
4. [NOTE] P3 failed: the ripple did not recur on fresh data, so it was a feature of A's realisation. Drop it from any mechanism story.
5. [NOTE] P8 (p99 arrival→on-GPU start 0.66–1.03 ms vs 0.4 ms) mostly measures the host/WDDM submission path, not GPU arbitration.
   Report the p50 next to the p99, and the R0.5 value (0.66 ms, where no bg block is preempted) as the submission floor.
6. [NOTE] Raw rec files (decision 1): choose (b). Keep them local with the SHA-256 manifest in git, and copy the run folder to a second
   place (external drive, or the OneDrive folder on this laptop). GitHub's free git-lfs quota (about 1 GB) would be used up by two such
   runs, and plain git can't be undone.

## Next
Re-analyses 1 (a–d) and 2 → interpretation entry. Then W2 is complete: write the W2 phase summary and PAPER_MAP entries, and move to
W4–5 (governor MVP). Characterisation should stop here. The open micro-questions (staggered switch, arbitration starvation) can be follow-ups.
