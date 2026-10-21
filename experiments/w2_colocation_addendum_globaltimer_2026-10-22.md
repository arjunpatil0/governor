# Addendum to w2_colocation.yaml: on-GPU interleaving timeline with %globaltimer (Experiment G) — REGISTERED 2026-10-22 (approved by the reviewer, reviews/2026-10-22_w2_L_and_G_review.md item 6, and by Arjun; committed before any G code or data)
Date drafted: 2026-10-22 · Revised 2026-10-22 after reviews/2026-10-22_globaltimer_draft_review.md (changes 1-3 applied below) · Registered by rename (`_DRAFT` dropped) after reviewer and Arjun approval, BEFORE any Experiment G code or data exists · Motivated by A and A2 (journals 0020, 0023, 0024) and the reviewer's scope (a)-(c) in reviews/2026-10-22_w2_A_A2_review.md · Replaces the deferred diagnostic of journal 0019 (pre-stated trigger; see "Trigger" below)

## Trigger (honest status)
The reviewer's pre-stated trigger had two halves: SA2's k far from 1, or SA4's fg slowdown not tracking 1 + d. The first half was met by an artefact (co-run regressor; corrected k = 0.983, journal 0024). The second half stands: at duty 1 the slowdown of a 1 ms and a 4 ms fg is 2.65 and 2.91, above the 2.0 of loss-free equal sharing, and the 4 ms fg slowdown exceeds 1 + d at every duty >= 0.5. Also A's wait-vs-time-to-slice-end curve ripples (journal 0024) and is unexplained. The host and OS traces cannot show on-GPU interleaving (journal 0019), so a kernel-side timeline is the remaining way to see it.

## Status
EXPLORATORY and DESCRIPTIVE. No confirmatory decision rule; no multiplicity claim. Every prediction below is written before data and is reported as "held / did not hold" with the numbers, whatever happens. It changes no rule of w2_colocation.yaml or the earlier addenda.

## Instrumentation (new code, written test-first after approval; nothing is built or run by this draft)
- Fg and bg kernels (w2_kernels.cu) optionally record, per thread block, `%globaltimer` at block start and block end plus `%smid`, **and a gap detector** (review change 1): one thread per warp reads `%globaltimer` in the block's main loop and keeps the largest gap between consecutive reads and the timestamp where that gap began (two more fields per record), into a device buffer, copied to host after the cell. Recording is a compile/launch-time option; with it off, the kernels are identical to today's.
- Pre-checks that must pass before any Experiment G cell (reported in the results, not assumed): (i) `%globaltimer` resolution (smallest nonzero difference between consecutive reads in a single block, on this GPU/driver); (ii) fg and bg contexts share one timebase (a single-process test with two streams, and a two-process test, whose recorded block times must interleave consistently with host QPC timestamps to within the resolution); (iii) instrumentation overhead, covering the block stamps AND the gap-detector reads: each instrumented R_m cell against its uninstrumented R_m_off twin, fg-alone latency and bg slice durations compared (acceptance: median fg-alone latency within 5% and the A-style observed wait of the m = 2 cell within 0.03 ms; if it fails, the failure is the result and the timeline is not interpreted).
- Definitions fixed now (review changes 1 and 2):
  - A kernel's on-GPU span = [min block start, max block end]. A block's *preempted interval* = its largest recorded gap if that gap > G_thr, where G_thr = 20 x the median loop-iteration gap measured in the bgalone cell of the same block (fixed rule; the multiple 20 is registered here).
  - OVERLAP (concurrency) = an fg block executing while a bg block is resident AND inside NO preempted interval of that bg block. Intersection of [start, end] intervals alone is NOT overlap (a preempted resident bg block contains the fg blocks that ran in its gap). Same-SM and different-SM overlaps are reported separately.
  - SLICED fg span = an fg kernel whose on-GPU span exceeds its alone service time (median of the same block's fg-alone measurement of that fg size, i.e. baseline for 0.1 ms; T1/T4's alone times from the T-alone cells below) by more than 2 x 0.243 ms (2 x SA2's corrected s0, fixed now). The quantum q = the median length of a context's runs INSIDE sliced fg spans (a run = maximal stretch with no block of the other context starting); the switch gap s = the median gap between the last block end of one context's run and the first block start of the other's, inside sliced spans only. The number of sliced spans that contribute is always reported. Run lengths over all spans (including those that end because no fg work existed) are reported separately and descriptively.

## Cells (per block; 10 blocks; fresh seeds from a new seed namespace; SM 1800, mem 8001 locked; Armoury Crate Performance; AC; admin; clean tree; as A)
1. baseline: fg 0.1 ms Poisson 200 Hz alone, instrumented.
2. R_m for m in {0.5, 1, 2, 8} ms (c = 0, duty 1): A's constant-slice cells with the same fg (0.1 ms, 200 Hz, 2000 requests), instrumented (timeline and overhead check). [4 cells]
3. R_m_off for m in {0.5, 1, 2, 8}: the same cells with instrumentation OFF; P1-P3 are evaluated on these (review change 3), and each R_m is compared with its R_m_off for the overhead pre-check. [4 cells]
4. T1: fg 1 ms (100 Hz Poisson, 1000 requests) with bg m = 2, duty 1, instrumented. [1 cell]
5. T4: fg 4 ms (40 Hz Poisson, 400 requests) with bg m = 2, duty 1, instrumented. [1 cell]
6. bgalone: bg m = 2, duty 1 alone (no fg), instrumented, to measure the bg block duration distribution, the loop-iteration gap (for G_thr) and bg run lengths without an fg. [1 cell]
7. T1_alone and T4_alone: the 1 ms and 4 ms fg alone, instrumented (the alone service times used to define a sliced span). [2 cells]
Total 14 cells x 10 blocks = 140 cells, about 55 min (budget from cell structure; not measured). (The review counted 12 cells because it did not list the two T alone cells needed by the sliced-span definition.)

## Predictions, written before data
Analysis (b), replication of the capped-wait model on the UNINSTRUMENTED R_m_off cells (fresh seeds, so the first test not made on the data that suggested it):
- P1. Cell-median observed wait (mean latency minus the block baseline, as in A) at m = 0.5 / 1 / 2 / 8 ms is within +/-0.03 ms of A's values 0.226 / 0.255 / 0.287 / 0.298 ms.
- P2. The capped-wait fit on the OBSERVED slice-end axis (the 2026-10-21 addendum definition) gives tau in [0.22, 0.31] ms (A: 0.260 [0.260, 0.270]; the median-based estimate was 0.308).
- P3. On the UNSTRETCHED axis (journal 0024) the ripple recurs: binned mean wait (A's bins) shows a local minimum in 0.35-0.40 ms and in 0.80-0.85 ms that is at least 0.04 ms below the preceding local maximum (A: 0.300 -> 0.214 and 0.364 -> 0.232 ms). A flat curve would be evidence that the ripple was a feature of A's particular realisations.
Analysis (a)/(c), on-GPU timeline (T1, T4, R_m, bgalone):
- P4. Quantum: q (as defined above, inside sliced fg spans only) lies between 0.5 and 0.9 ms (from the slowdown relation 2 + 2s/q with s = 0.243 ms: q about 0.75 ms from the 1 ms fg and 0.53 ms from the 4 ms fg; the draft deliberately allows both).
- P5. Switch gap: s (inside sliced spans only) lies between 0.2 and 0.3 ms (SA2 corrected s0 = 0.243 ms [0.240, 0.245]).
- P6. No concurrency: zero fg blocks execute while a bg block is resident outside that bg block's preempted intervals (OVERLAP as defined above). One counterexample in a clean cell falsifies P6; a handful within the timer resolution are reported as ties, not overlaps.
- P7. Mid-kernel preemption: bg blocks show a preempted interval (largest gap > G_thr) that contains fg blocks; the fraction of bg blocks with such a gap is >= 1% in T4 (a 4 ms fg run is long enough to land inside resident bg blocks) and is reported for all cells; if it is about 0 the context switch happens at block boundaries.
- P8. Request timeline: for the 0.1 ms fg in R_m, the delay between arrival and the on-GPU start of the fg kernel has p99 <= 0.4 ms for every m (A: p99 latency 0.77-1.17 ms including the 0.1 ms service and the 0.155 ms host path).

## Reported, not predicted
Timeline plots/tables for one representative cell per type; bg run-length distribution; SM-id usage by context; block-duration inflation; the relation between the ripple on the wait curve and the quantum (if q is about 0.45 ms the ripple period fits; this is a post-hoc reading and stays labelled so).

## What would change my reading
Overlap found (P6 fails): the cost is contention, not time-slicing; the capped-wait and slowdown arguments must be redone. q far from 0.5-0.9 ms or s far from 0.2-0.3: the 2 + 2s/q relation is not the mechanism. Instrumentation fails its overhead pre-check (block stamps or gap detector): no interpretation of the timeline; report the failure.

## Not in scope
Part L (llama.cpp validation), any change to the registered A/A2/B/C rules, and any claim about other GPUs or driver versions.
