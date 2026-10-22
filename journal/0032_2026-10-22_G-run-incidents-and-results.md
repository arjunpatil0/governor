# 0032 — Experiment G full run: incidents, environment limitation, results (before interpretation)
Date: 2026-10-22 · Phase: W2 · Author: Claude Code · Run dir: data/raw/w2_G/20261022T062433Z (complete) · Reports: data/w2_G_results.md (witness view, primary), data/w2_G_results_skip_b0.md (block 0 excluded), data/w2_G_results_allblocks.md (secondary)

## Incidents (Arjun's report, logged before analysis)
1. **False start.** The first launch (run dir data/raw/w2_G/20261022T062127Z, local 11:51:27) was started with Chrome open. Arjun interrupted it with Ctrl+C within seconds, reset the clocks, killed the child processes and restarted. The partial dir holds only calibration files, meta.json, an empty results.csv (header only) and one cell directory (b00_00_g_R2, last file written 11:51:56). It is kept as a record and is NOT analysed. The complete run is 20261022T062433Z (started 11:54:33 local, last cell written 13:25).
2. **Environment limitation (all experiments so far, W1-W2 incl. G).** The WhatsApp and Discord desktop apps ran idle in the background during every experiment up to and including G. No process list was recorded for any of them, so the load they added (CPU, GPU compositing) is unmeasured. Treat as a limitation of all W1-W2 data, not as an effect found.
3. **Apps quit during G.** Arjun quit WhatsApp and Discord from the system tray. Exact time not noted; Arjun's recollection: "right at the beginning or before even starting the new run". No log can confirm it (meta.json has no process list for this run). Handling: the earliest cells are the only ones that can overlap that moment, so block 0 of the complete run (cells written 11:55-about 12:00, 17 cells) is flagged as possibly affected and the report is given with and without it. If the quit was later than block 0, this flag misses it; the time is unverified.

## Process changes (commit 57ffdbe, tests first)
- meta.json now has `processes` (name, instance count, summed CPU% over a 1 s window) for every part and mode; workloads/common/procsnap.py, tests/test_procsnap.py (RED: module missing; GREEN 3 passed). Not present in the G run.
- CLAUDE.md run checklist now includes "quit background apps from the system tray".
- analysis/w2_g_analysis.py gained `--skip-blocks` (test first: RED then GREEN) for the sensitivity view. Suite 187 passed. The registered analysis is unchanged.
- Import-order slip caught before use: my first edit imported procsnap before sys.path setup in run.py; fixed (module import moved below the path block) and checked with `run.py --help` before committing.

## Results (witness view, all 170 cells; numbers from data/w2_G_results.md; no interpretation here)
- Pre-check (iii) PASS: fg-alone latency difference 1.2% (limit 5%); R2 wait 0.3010 instrumented vs 0.2947 ms (diff 0.0063, limit 0.03).
- Witness gate (i) PASS: bgalone witness preempted fraction 0.000% (2,665,332 blocks) and bgalone_3bpsm 0.000% (2,633,148). Gap-log overflow: 0 untrusted blocks.
- P1 HELD (R0.5/1/2/8 off-cell waits 0.2264/0.2617/0.2947/0.3042 vs A 0.226/0.255/0.287/0.298). P2 HELD (tau 0.260 ms; the reported bootstrap CI [0.260, 0.260] is degenerate, which I did not investigate). P3 DID NOT HOLD.
- P4 DID NOT HOLD: q = 0.374 ms (28,460 complete runs; T1 and T4 only, since the 0.1 ms fg cells have no sliced span). P5 DID NOT HOLD: s = 0.148 ms (39,054 transitions, 1,128 with negative s).
- P6 DID NOT HOLD: 75,971 of 8,376,912 fg witness blocks overlap a bg block by more than 10 us (T1 24,880; T4 51,091; the four R cells 0). Control g_T4_3bpsm overlaps too (15,985 fg blocks; same-SM 2,617, different-SM 15,871). By the registered concurrency rule this is REPORTED AS A FINDING. (The smoke had shown 0 control overlaps; the smoke was unlocked-clock, one block, and is not a result.)
- P7 HELD: g_T4 19.26% of recorded bg blocks preempted (registered >= 1%); R0.5 0.0%, R1 2.68%, R2 10.4%, R8 42.5%, T1 14.0%.
- P8 DID NOT HOLD: arrival-to-GPU-start p99 0.659 / 0.880 / 1.006 / 1.025 ms for m = 0.5/1/2/8 (limit 0.4). Coverage: g_R0.5 fg_share about 0.40 and g_R1 about 0.78-0.80 (recorded-interval rule), others >= 0.995.
- Sensitivity, block 0 excluded: every verdict identical (q 0.374, s 0.148, P6 70,012 of 7,539,264, control still overlaps, P7 19.44%).
- Secondary all-blocks view (arbitration artefact present): q 0.383, s 0.118, P6 366,952 of 16,754,256, P7 g_T4 59.63%; verdicts identical. The artefact is visible: g_bgalone has 50.0% of blocks with gaps (about 345 us median) alone, vs 0.000% on witness blocks.

## Data handling
- Large files not committed: the 190 `*_rec.npz` (523 MB of the 539 MB run; my earlier estimate of 0.1-0.3 GB was wrong). Committed instead: results.csv, meta.json, calibration, per-cell logs/specs/windows/samples, and REC_MANIFEST.sha256 (SHA-256 of every rec file). The rec files stay on Arjun's disk until a decision on how to store them (question in STATUS.md).

## Open
- Reviewer checkpoint: results before interpretation. Questions the data raises (not answered): why the control overlaps; why q is 0.374 not 0.5-0.9; why P8 delays are 1 ms; degenerate tau CI.
