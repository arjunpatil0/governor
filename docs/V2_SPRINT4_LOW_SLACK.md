# V2 sprint 4: does pausable decode still help when the app leaves little free time per frame?

## Verdict

(pending: filled in after the measurements)

Branch v2-foreground. Follows docs/V2_SPRINT3_JITTER.md (PASS under moderate and heavy jitter with 8 to 11 ms of slack per frame). This document is written in the order the work was done: the step-0 finding, the decision rule and the forecast below were committed and pushed before any measurement.

## Step 0 finding: per-group prediction, and what the margin is

The gate already predicts each group's own duration. In `workloads/background/llama_handover_bench.cpp` the gate keeps one estimator per group index (`g_est`, one entry per group), each the median of that group's last 8 clean durations (a duration is clean if the unit ended before the deadline it was gated against), falling back to an exponentially weighted average (0.9 old, 0.1 new) only until the first clean one exists. The output-head group (about 1.3 to 1.9 ms for the 3B, 2.4 to 3.6 ms for the 8B depending on how the layers are grouped) therefore has its own estimate, and the short groups have theirs; no single average is used and nothing was switched. One property worth knowing in tight gaps: a group that overran its deadline is not clean and does not enter the median, so after a run of overruns the estimate can lag the true duration until clean ones return; the average over all units is not used for the decision once a clean one exists. The early-start margin m of the brief is the existing guard of the gate: a unit launches only if now plus its predicted time plus the guard is not after the published deadline, and the guard is applied before every group and before the first group of a token. Sprints 2 and 3 ran it at 0 ms; this sprint runs 0 and 1.0 ms. It is a configuration value (`GUARD_MS`), not a code change in the driver.

## Questions and decision rule (fixed before measuring)

Setup: 1800 MHz lock, spin-wait, 60 fps, moderate jitter ON with the same seeds and model as sprint 3 (frame cost lognormal with a CV of 0.15, submit time within plus or minus 1 ms with the hint updated only at the real submit, 5% unannounced bursts of 0.5 to 1.5 ms), a constant-cost foreground (scene S0 with the nominal cost calibrated). The synthetic frame cost is calibrated so that the SOLO median frame time (frame duration from launch to completion) is 12.5 ms (TIGHT, about 4.2 ms free per frame) or 14.5 ms (VERY TIGHT, about 2.2 ms free per frame); the measured SOLO medians are reported. Arms at each level: SOLO; 3B whole-token gate (guard 0); 3B 14 groups with guard 0; 3B 14 groups with guard 1.0 ms; 8B 14 groups with guard 1.0 ms; 8B 28 groups with guard 1.0 ms. 2 levels x 6 arms x 2 reps = 24 cells of 60 s (5 s warm-up). Excess late % is the arm's late-frame % minus the SOLO late-frame % at the same level and rep (same seed, same sequence).

- PASS: the best 3B group arm has excess late over SOLO of at most 1 percentage point at TIGHT and at most 2 at VERY TIGHT, with tok/s at least that of the whole-token gate. The whole-token gate cannot start a 10 ms token in a 4 ms gap, so its tok/s will be 0 and "at least the whole-token gate" is vacuous; I therefore add a condition before measuring: the arm must also deliver at least 5 tok/s (about a tenth of the regular case), and I report the literal rule and the stricter one separately. "Best" means the 3B group arm with the highest tok/s among those that meet the excess limit.
- MARGIN WORKS: guard 1.0 ms cuts the decode-attributed late frames against guard 0 at the same level (3B, 14 groups) without losing more than 15% of tok/s. Answered yes or no per level.
- FAIL: the best 3B group arm has excess late above 5 percentage points at TIGHT.

Every late frame is classified as solo-caused (the SOLO cell with the same seed misses the same frame), burst plus decode (a burst ran in the gap before it and decode overlapped it), early submit (decode overlapped it and the overlap is no more than the amount by which the frame was submitted ahead of its nominal time plus 0.3 ms: the gate's picture of the deadline was right but the frame came early), decode overlap (any other decode overlap: a group longer than predicted or launched too late), or other. The slowdown of the frames decode touched is the frame's duration divided by the same frame's duration in the SOLO cell.

## Forecast (committed before measuring)

SOLO late frames: about 3% at TIGHT and about 17% at VERY TIGHT, because lognormal frame costs with a CV of 0.15 around 12.5 ms exceed 16.7 ms in about 2.4% of frames and around 14.5 ms in about 16% (the submit jitter adds to both). Free time per frame varies a lot from frame to frame (the standard deviation of the frame time is about 1.9 ms), so a gate that needs a contiguous gap for each group will use only part of the mean free time.

| arm | TIGHT tok/s | TIGHT excess late | VERY TIGHT tok/s | VERY TIGHT excess late |
|---|---|---|---|---|
| SOLO | 0 | 0 (reference, about 3% late) | 0 | 0 (reference, about 17% late) |
| 3B whole token | 0 | 0 (never starts a token) | 0 | 0 |
| 3B 14 groups, guard 0 | about 20 (14 to 24) | about +2 pp (0.5 to 5) | about 6 (2 to 10) | about +6 pp (2 to 12) |
| 3B 14 groups, guard 1.0 | about 13 (9 to 17) | about +0.3 pp (0 to 1) | about 1 (0 to 3) | about +0.5 pp (0 to 2) |
| 8B 14 groups, guard 1.0 | about 3 (1 to 6) | about +0.3 pp (0 to 1) | about 0.5 (0 to 1.5) | about +0.2 pp (0 to 1) |
| 8B 28 groups, guard 1.0 | about 5 (2 to 8) | about +0.3 pp (0 to 1) | about 1 (0 to 2) | about +0.2 pp (0 to 1) |

Reasoning in one place. 3B at TIGHT, guard 0: the ideal is the free 4.2 ms per frame divided by the 10.3 ms of decode per token, that is 0.41 tokens per frame or about 24 tok/s at 60 frames per second, less about 10% for the part of each gap too short for the next group. The excess is the groups in flight when an early frame arrives: with guard 0 the gate fills the gap to the nominal deadline, so about half of all frames (those submitted early, by up to 1 ms) meet a group, and a frame that is already near the limit tips over. At VERY TIGHT the 3B head group (about 1.9 ms) barely fits a 2.2 ms mean gap and fits only in the shorter frames, so tok/s falls sharply, and the excess grows because the base frames are already near the deadline. Guard 1.0 removes the early-frame collisions (the group ends at least 1 ms before the nominal deadline, the size of the early offset) but costs 1 ms of every gap: at TIGHT about a quarter of the throughput, at VERY TIGHT the head group (1.9 ms) plus 1.0 ms needs a 2.9 ms gap, which only the shortest frames leave, so the 3B nearly stops. 8B: the head group is 3.6 ms with 14 groups and 3.0 ms with 28, plus 1.0 ms of guard; at TIGHT it fits only in frames shorter than about 12 ms (roughly 40%), at VERY TIGHT only in frames shorter than about 12.7 ms (about 15 to 20%), and a token also needs its other layers placed, so I expect the 8B to collapse at VERY TIGHT (below 1.5 tok/s) as you suggested.

Decision rule forecast: I expect the guard-0 3B arm to miss the 1 pp limit at TIGHT (about 2 pp), so the 3B guard-1.0 arm should be the PASS arm at TIGHT (13 tok/s, which meets the stricter 5 tok/s condition), and no arm to meet PASS at VERY TIGHT under the stricter rule (guard 1.0 delivers about 1 tok/s, guard 0 exceeds 2 pp). MARGIN WORKS: yes on the late-frame side, no on throughput (a loss of about 35% at TIGHT against the 15% allowed), so overall NO at both levels. FAIL: not expected (an excess above 5 pp at TIGHT would need the best arm to be wrong by a lot).

## Step 0 and calibration, as run

(pending)

## Forecast vs measured

(pending)

## Main table

(pending)

## Cause breakdown

(pending)

## Plot

(pending)

## Limitations

(pending)
