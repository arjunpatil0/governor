# STATUS (overwritten at every stop)
Updated 2026-10-22 · Phase: W2 (Experiment G registered, built and smoke-tested; ready to run)

## Just did (commits; see git log)
- Applied the G witness review: addendum 3 REGISTERED (verified witness set via %smid with a fallback rule, witness rule for fg too, g_T4_3bpsm and g_bgalone_3bpsm controls with the concurrency rule). P4-P6 unchanged. Slip disclosed: commit b50cc2c holds the draft text under the final name, 675e861 the registered text (no data in between).
- Controls built test-first (17 cells per block, 170 cells; own calibration at 3 blocks per SM); smoke of all 17 cells (not a result): witness set nominal in every launch, bgalone witness gap rate 0.000% on both grids (gate passes), 0 untrusted blocks, 0 lost gaps, coverage R0.5 41% / R1 92% / rest >= 99.5%. Control g_T4_3bpsm: 0 overlaps in 43,092 fg blocks vs 11,070 of 870,048 in the main cells, i.e. by the registered rule "unexplained, not concurrency" if that repeats on locked data.
- Suite 183 passed. Response reviews/2026-10-22_G_witness_response.md, journal 0031.

## Waiting for
- Your go. Nothing else blocks the full run.

## Decisions needed
1. Two readings of mine to confirm or overrule (response items 1 and 2): gate (ii) fails only if a cell has no usable launch; fg/bg on-intervals subtract every logged gap > 20 us (addendum 2) rather than only gaps >= G_thr (about 25 us). Recommendation: keep both; they are registered as written.
2. Schedule: 170 cells; the 17-cell smoke took 6.6 min, earlier ones 4.2 and 14.6 (cool-down waits). Plan 1.2-3 h with the laptop untouched. Raw data will be about 0.1-0.3 GB; I will force-add results.csv, meta.json and the cells.

## Reviewer checkpoint due?
- Results before interpretation, after the run. Analysis: `python analysis\w2_g_analysis.py` (witness view) and `--all-blocks` (secondary).

## Full G run (admin PowerShell, AC power, clean tree, Armoury Crate Performance, Chrome and other apps closed, do not click in the window)
cd C:\Users\arjun\governor
python experiments\w2_colocation\run.py --part G --ambient-c 25 --armoury-mode Performance
