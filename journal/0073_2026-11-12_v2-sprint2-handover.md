# 0073 - 2026-11-12 - v2 sprint 2: GPU handover with pausable decode (written after the fact)

Written after the fact on 2026-11-12 from the commit history, docs and data; not written at the time.
Doc: docs/V2_SPRINT2_HANDOVER.md. Commits (git log on that file): 09a0cd0 (2026-11-08, handover doc with decision rule and forecast, committed before measuring), d70dca5 (2026-11-08, results). Branch v2-foreground.
- Question: does pausable decode free the GPU for a 60 fps application, on hardware.
- Verdict (doc): WIN on throughput by the rule fixed before measuring; the handover forecast was wrong. Late frames were 0.00% in every end-to-end cell, so the win is not a late-frame win.
- Forecast (stated in the doc): whole-token decode would make a foreground frame wait about 10 ms. Measured: the worst mid-token wait over 6,172 frames was 1.69 ms (p99 0.87 ms). The GPU time-slices between processes (quantum about 0.37 ms), so the app shares the GPU rather than waiting for the whole token.
- 8B profile: token 21.0 ms; overhead 1.4% at G = 14 (longest group 3.61 ms), 2.9% at G = 28 (2.99 ms).
- End to end (12 cells, 3 reps, 60 s, static aligned gate at 1800 MHz, guard 0): S1 3B 19.95 to 47.9 tok/s; S5 8B 0.0 to 24.2 tok/s, going from the whole-token gate to 14 groups; power 57.9 to 59.2 W; power_rejected 0.
- Limits (doc): both arms static, no power control, no run where the baseline misses; one machine, one GPU and driver; the WDDM explanation was not tested by varying the quantum.
- Next (doc, owner's decision): test where the baseline misses (the learned governor's unaligned mode, bursty frame costs); split the output head by rows to bring the 8B longest group under 2.5 ms.
