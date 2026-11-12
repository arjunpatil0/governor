# 0072 - 2026-11-12 - v2 sprint 1: pause cost of layer-group decode (written after the fact)

Written after the fact on 2026-11-12 from the commit history, docs and data; not written at the time.
Doc: docs/V2_SPRINT1_PAUSE_COST.md. Commits (git log on that file): 83db807 (2026-11-07, forecast and decision rule committed before measuring), b943fcf (2026-11-08, results and verdict). Branch v2-foreground.
- Question: if one token's decode is split into G layer groups with a pause point between groups, how much slower is each token, and how long is the longest uninterruptible piece.
- Decision rule (fixed in 83db807): GO if some G has a longest group of at most 2.5 ms and a per-token overhead of at most 15% against G = 1.
- Measured (3B Q4_K_M, SM clock locked at 1500 MHz, 3 reps of 300 tokens per configuration): G = 14 longest group 1.95 ms (p99 2.02), overhead 2.2%; G = 28 1.63 ms, 4.3%; G = 7 2.58 ms, which misses the 2.5 ms limit; graphs off +14.2%.
- Forecast was 12.6% overhead at G = 14 (100 us per boundary). Measured cost per boundary: 16 to 31 us.
- Control: a forced 2 ms pause per boundary raised token time by 6.07 ms at G = 4 and 12.17 ms at G = 7 (expected 6 and 12), so the boundaries are real pause points.
- Verdict: GO. Sprint 2 may build the real pausable decode.
- Limits (doc): the output projection (about 1.3 ms) cannot be split, so no G gets the longest piece below about 1.6 ms; prefill was not split; what the other process gains at a pause was not measured.
