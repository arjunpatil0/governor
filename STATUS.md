# STATUS (overwritten at every stop)
Updated 2026-10-22 · Phase: W2 (Experiment G run done and analysed; results before interpretation)

## Just did (commits; see git log)
- Logged the incidents first (journal 0032): false start with Chrome open (partial dir 20261022T062127Z kept, not analysed); WhatsApp/Discord ran idle in all W1-W2 experiments (environment limitation); you quit them at an unrecorded time ("right at the beginning or before the new run"), so block 0 is flagged and the report is given with and without it.
- Process changes (57ffdbe, tests first): meta.json now records running processes (name, count, CPU%) at run start; CLAUDE.md checklist has "quit background apps (tray)"; `--skip-blocks` option in the G report.
- Analysed G (complete run 20261022T062433Z, 170 cells): data/w2_G_results.md (witness, primary), _skip_b0.md, _allblocks.md. Pre-check (iii) PASS, witness gate PASS, 0 untrusted blocks. P1 HELD, P2 HELD, P3 DID NOT HOLD, P4 (q 0.374 ms) NOT held, P5 (s 0.148 ms) NOT held, P6 NOT held (75,971 of 8.38M fg blocks overlap) and the 3-bpsm control overlaps too, so by the registered rule concurrency is REPORTED AS A FINDING, P7 HELD (19.3% in T4), P8 NOT held (p99 0.66-1.03 ms). Excluding block 0 changes no verdict.

## Waiting for
- Reviewer checkpoint: results before interpretation (journal 0032).

## Decisions needed
1. Raw rec files: 190 `*_rec.npz` = 523 MB (the run is 539 MB; my 0.1-0.3 GB estimate was wrong). I committed everything else plus a SHA-256 manifest and did NOT push the 523 MB. Options: (a) commit and push them anyway (repo grows about 0.5 GB per such run), (b) keep local + manifest, back up elsewhere, (c) git-lfs. Which?
2. Quit time: if you can recall it more precisely, tell me and I will re-flag; otherwise the block-0 flag stands as stated.

## Notes
- Open and unexplained (not interpreted): why the control overlaps (smoke showed none), q below range, ~1 ms arrival-to-start p99, degenerate tau bootstrap CI [0.260, 0.260].
