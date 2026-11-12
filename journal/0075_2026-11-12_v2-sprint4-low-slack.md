# 0075 - 2026-11-12 - v2 sprint 4: low free time per frame (written after the fact)

Written after the fact on 2026-11-12 from the commit history, docs and data; not written at the time.
Doc: docs/V2_SPRINT4_LOW_SLACK.md. Commits (git log on that file): b24edae (2026-11-08, low-slack doc with step-0 finding, decision rule and forecast, committed before measuring), 7425326 (2026-11-08, results and changelog). Branch v2-foreground.
- Question: does pausable decode still help with 4 ms (TIGHT) or 2 ms (VERY TIGHT) free per frame, and does an early-start guard (1.0 ms) cut collisions.
- Step 0 (doc): the gate already keeps one duration estimate per group (median of the last 8 clean durations); nothing was switched.
- Verdict (doc labels): PASS at both slack levels; "MARGIN WORKS: no"; "FAIL: no".
- 3B 14-group gate, guard 0: +0.28 pp excess late frames at TIGHT (3.99 ms free) with 17.5 tok/s; +1.71 pp at VERY TIGHT (1.97 ms free) with 7.2 tok/s. Whole-token gate: 0 tok/s at both levels.
- The VERY TIGHT pass rests on the mean of two reps: rep 1 is +2.28 pp (above the 2 pp limit), rep 2 is +1.14 pp.
- Guard 1.0: decode-attributed late frames fall from 21 to 2 (TIGHT) and from 80 to 3 (VERY TIGHT), keeping 76% and 64% of the tok/s.
- The forecast was wrong about which arm passes (guard 0 was expected to miss its limits). The cause of the guard-0 overlap is not established: only 17 of 80 decode-attributed late frames at VERY TIGHT are early submits.
- Calibration: SOLO medians of 12.68 and 14.70 ms in the 60 s cells (free time 3.99 and 1.97 ms), about 0.2 ms off the targets; not recalibrated.
- Limits (doc): two reps per cell; independent jitter; one laptop GPU at a locked 1800 MHz; power at or below 50 W in every arm.
