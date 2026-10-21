# STATUS (overwritten at every stop)
Updated 2026-10-22 · Phase: W2 (A, A2 re-analysed after review; globaltimer addendum DRAFTED, uncommitted; part L code done, run not started)

## Just did (commits)
- Review answered (reviews/2026-10-22_w2_A_A2_response.md, journal 0024), existing data only: (1) SA2 k corrected 0.395 -> 0.983 (s0 0.243 ms) with the alone-service regressor, so the "k far from 1" half of the globaltimer trigger was an artefact (journal 0023's reading is corrected, not edited); (2) re-binning against the unstretched slice end removes the sparse bins and the 0.6 ms dip but a ~0.45 ms ripple remains, tau 0.19 ms (observed-end axis: 0.26); (3) A's thermal sensitivity: HA1 unchanged, HA2 NOT SUPPORTED in all versions (3/6 -> 1/6 is lost power with 6 block pairs, not a reversal). A bug in ha2's handling of missing cells (NaN counted as significant) was found and fixed test-first. Suite: 114 passed.
- Part L code + tests committed (journal 0025; suite 127 passed; non-admin GPU smoke ok). Run-time estimate corrected to about 50 min.
- DRAFT (uncommitted): experiments/w2_colocation_addendum_globaltimer_2026-10-22_DRAFT.md, scope (a)-(c), predictions P1-P8 before data. Not registered.

## Waiting for
- Arjun/reviewer to review the draft addendum (uncommitted, so the tree is NOT clean by design). Part L code is written and tested (journal 0025); the full validation run is not started.

## Decisions needed
1. Approve the globaltimer addendum draft (commit it, then I build the instrumented kernels test-first)? Recommendation: approve after the reviewer reads it; the open points are the cell list (9 cells x 10 blocks, about 35 min) and the P4 range for q (0.5-0.9 ms).
2. Next experiment order: Experiment G (globaltimer) before the llama.cpp validation run, or the reverse? Recommendation: llama.cpp validation first (code is ready, no new addendum needed, about 50 min), then G after its addendum is approved and its kernels are built.

## Reviewer checkpoint due?
- Design change: YES (the globaltimer addendum, before it is committed). Results before interpretation: A and A2 reviewed; the three re-analyses are in journal 0024. Surprise: the ripple on the wait curve.
