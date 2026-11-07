# V2 sprint 2: does pausable decode free the GPU for the real-time app, on hardware?

## Verdict

(pending: filled in after the measurements)

Branch v2-foreground. Follows docs/V2_SPRINT1_PAUSE_COST.md, which measured what a pause costs the decode (2.2% at 14 groups, longest group 1.95 ms on the 3B) and left open what the other process gains. This document is written in the order the work was done: the forecast and the decision rule below were committed before any measurement.

## Questions and decision rule (fixed before measuring)

1. Handover latency: how long does the foreground's first kernel wait behind the decode, for whole-token decode (G = 1) against 14 groups (G = 14), when the decode is between groups and when it is mid-group?
2. The 8B group profile: the longest group at G = 1, 14 and 28.
3. End to end, on hardware: S1 (3B) and S5 (8B), gate on, 60 s cells, 3 reps, whole-token gate (the v1 behaviour) against the 14-group pausable gate, with tok/s, late-frame % and power from the energy counter.

Decision rule for question 3:

- WIN: the 14-group gate cuts late frames against the whole-token gate in S5 with no loss in tok/s, or raises tok/s with late frames no worse.
- NEUTRAL: the difference is within noise.
- LOSS: worse on both.

## Forecast (committed before measuring)

Stated forecast for handover latency (from the brief): with whole-token decode the worst wait for the foreground's first kernel is about one token (about 10 ms); with 14 groups it is about one group (about 2 ms) plus the WDDM context switch (0.15 to 0.37 ms). For the 8B I expect the output head to be larger than the 3B's 1.3 ms, so the longest group at G = 28 should be above 2.5 ms, and G = 14 around 3 to 4 ms (an 8B layer is about 0.65 ms, from the 3B's per-layer time scaled by size, and the head about 1.8 ms because the vocabulary projection is 4096 wide instead of 3072 for the same 128k vocabulary).

A competing hypothesis, recorded so the result can be read against it: the earlier time-slice measurements (q = 0.374 ms, s = 0.148 ms, docs/W2_SUMMARY.md) show that the GPU switches between contexts every quantum, so a foreground kernel submitted while a decode graph is running may start within about one quantum whatever the group length, and the cost shows up as a slower frame (about 2.8 times longer when both have work) rather than as a long wait. If that holds, the first-kernel delay will be similar for G = 1 and G = 14 (a few tenths of a millisecond), and the benefit of groups will only appear through the gate: the decode can stop launching work when a frame is due, which whole-token decode cannot do for a token that does not fit.

For the end-to-end cells: in S1 most tokens of the 3B fit the slack and I expect little difference (within a few percent in tok/s, late frames near zero for both). In S5 the 8B token (about 21 ms) never fits a gap, so the whole-token gate should produce about 0 tok/s with 0% late frames, and the 14-group gate should produce a few to ten tok/s; the late-frame effect is the open question, since the v1 governor's late frames in S5 came from interleaving costs under time-slicing that the simulator does not model.

## Measured

(pending)

## Limitations

(pending)
