# STATUS (overwritten at every stop)
Updated 2026-10-22 · Phase: W2 CLOSED. Next: W4-5 (governor MVP).

## Just did (commits; see git log)
- Answered reviews/2026-10-22_G_results_review.md (response file written). Storage: option (b), rec files stay local, SHA-256 manifest in git.
- Post-hoc re-analyses (labelled exploratory; registered verdicts unchanged), code analysis/w2_g_posthoc*.py, tests first, data/w2_G_posthoc.md:
  - Staggered switch NOT supported: across the 36 SMs the outgoing last on-time spreads 1-5 us, cross-SM overlap negative (-102 to -297 us), 0 same-SM overlaps in 5.2M SM-switches.
  - Overlaps are whole runs inside a block's first or last on-interval; 0.0% between two interior intervals (685k pairs). Reading: probably a block-edge measurement artefact, NOT concurrency (consistent with, not proven; per-warp times were not recorded).
  - tau on a 0.2 us grid: 0.2580 ms, 90% CI [0.2564, 0.2602] (registered fit 0.260 and verdict unchanged).
  - P8 table now has p50 0.207 / 0.210 / 0.271 / 0.268 ms beside the p99.
- Journal 0033 (interpretation), docs/W2_SUMMARY.md, docs/PAPER_MAP.md (14 claims), TIMELINE, CONCEPTS.

## Waiting for
- Your copy of the G run folder (below). Then your go for W4-5.

## Decisions needed
1. Copy this folder to OneDrive or an external drive (516 MB; contains the complete run and the 120 KB partial run):
   C:\Users\arjun\governor\data\raw\w2_G
   Verify afterwards: in the copy, `Get-FileHash -Algorithm SHA256` of any file under cells\*\*_rec.npz must match the line for that file in data\raw\w2_G\20261022T062433Z\REC_MANIFEST.sha256 (committed in git).
2. W4-5 scope: I suggest starting with the telemetry daemon plus a controllable background runtime, as in the plan. Say if you want a different first step.

## Notes
- Open and not scheduled: per-warp timing to settle the block-edge artefact; Nsight Compute check of the 4th-6th block starvation; q and s re-derived on interior intervals only.
- Run checklist now includes "quit background apps (tray)"; meta.json logs running processes from the next run on.
