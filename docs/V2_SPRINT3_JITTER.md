# V2 sprint 3: does the pausable gate keep frames on time when the app is not perfectly regular?

## Verdict

(pending: filled in after the measurements)

Branch v2-foreground. Follows docs/V2_SPRINT2_HANDOVER.md, which showed that the 14-group gate delivers 2.4 times (3B) and infinitely more (8B) throughput than the whole-token gate with 0.00% late frames, on a perfectly regular foreground. This document is written in the order the work was done: the hint semantics, the decision rule and the forecast below were committed before any measurement.

## What the gate knows, and when (hint semantics)

The foreground publishes three things through the 40-byte record: a busy flag, the next deadline and the time of the update. Busy goes up before a frame (in the v1 loop 1 ms before the frame's scheduled arrival, not at the real submit), and goes down when the frame has actually finished, with the next deadline in both updates equal to the nominal arrival of the next frame on the fixed 60 Hz grid (scheduled time plus 16.67 ms), so the gate learns that a frame has ended only after it has ended. It is never told a frame cost or a frame's expected end, never told when a frame will really be submitted if that differs from the grid, and never told about GPU work the app does outside its frames. The gate itself keeps only its own estimate of how long a decode unit takes (the median of the last 8 clean durations, one per group index) and starts a unit only if the app is not busy and now plus that estimate plus the guard (0 ms here) is before the published deadline. Consequences for what a jitter test can stress. Frame-cost variation is mostly seen by the gate: a long frame simply keeps busy up longer, and the gate is told when it ends, so cost jitter alone does not test the gate; it shrinks the margin of frames that decode does touch and it raises the solo lateness. Submit-time jitter is not seen: the deadline the gate trusts is the nominal grid, so a frame that arrives up to 2 ms early collides with a unit the gate believed would end in time, and the busy flag now goes up only at the real submit. Unannounced bursts (a compositor or UI pass in the gap) are not seen at all: they occupy the GPU while the hint says the gap is free. The effects to watch are therefore from submit jitter and bursts; cost jitter is the baseline against which they show.

## Questions and decision rule (fixed before measuring)

Jitter on the synthetic 60 fps foreground, seeded, with the same seed and the same frame sequence across the arms of a level and repetition. Three kinds: (a) frame cost lognormal around the current scene mean with a coefficient of variation of 0.15 (moderate) or 0.30 (heavy), plus a 2x spike in 2% of frames (heavy only); (b) submit time off the schedule by up to plus or minus 1 ms (moderate) or 2 ms (heavy), with the hint updated only when the app actually submits; (c) an unannounced extra kernel of 0.5 to 1.5 ms at a random point in the gap before a frame, in 5% (moderate) or 10% (heavy) of frames, with no hint. Arms at 1800 MHz, guard 0, spin-wait as in sprint 2: SOLO (app only, no decode), 3B whole-token gate, 3B 14-group gate, 8B 14-group gate (the 8B whole-token gate gives 0 tok/s and is skipped). Levels: none (1 rep, a reproduction check against sprint 2), moderate and heavy (3 reps each); 60 s measured cells; 28 cells.

Excess late % of an arm at a level is its late-frame % minus the SOLO late-frame % at the same level (same seeds). Decode must not be blamed for lateness the app has on its own.

- PASS: the 14-group excess late is at most 1 percentage point at moderate and at most 2 at heavy, with tok/s at least that of the whole-token gate at the same level.
- OVERLAP BONUS: the 14-group excess late is below the whole-token excess late at heavy. This would be the first late-frame win from pausing; the document says whether it happened.
- FAIL: the 14-group excess late is above 5 percentage points at moderate.

Every late frame is classified as solo-caused (the SOLO cell with the same seed misses the same frame, matched by sequence index), decode-overlap (decode work overlapped it, with the overlap in ms), burst-caused (an unannounced burst in the gap before it plus decode overlap), or other (none of these). The slowdown distribution of the frames decode touched is reported per arm as in sprint 2.

## Forecast (committed before measuring)

SOLO late frames: none 0%, moderate about 0.2%, heavy about 3% (the heavy cost spikes at the 1.3x phase of S1 are 18 ms frames, and lognormal tails with a CV of 0.30 add to that). Excess late frames, 14 groups: about 0.2% at moderate (range 0 to 1) and about 0.8% at heavy (range 0.2 to 2), because the gate keeps almost all decode work out of the frames and what remains is the group in flight when an early or bursting frame arrives, at most about 1 ms for the 3B (a group is 0.7 ms) and about 1.2 ms for the 8B. Excess late frames, whole token: about 0.3% at moderate and 1.0% at heavy, because the tail of a token that the gate admitted can overlap a frame that arrives up to 2 ms early, and a whole token has a longer tail than a group. So I expect PASS at both levels and I do not expect FAIL (an excess above 5 points would need decode to overlap a large share of frames). OVERLAP BONUS: I give it a little under even odds; the expected difference between the arms is a few tenths of a percentage point, close to what three reps can resolve. Throughput: the whole-token gate loses windows when frame cost and submit time vary (its window is about 1 ms wide), so I expect it to fall from 19.95 tok/s (none) to roughly 10 to 15 at heavy, and the 14-group gate to stay near 40 to 48 tok/s. Cause breakdown: at heavy most late frames should be solo-caused (cost spikes), the decode-overlap share small, and the burst-caused share the largest part of the excess.

## Forecast vs measured

(pending)

## Table: tok/s, late %, excess late %, power per arm and level

(pending)

## Late-frame cause breakdown

(pending)

## Plot

(pending)

## Limitations

(pending)
