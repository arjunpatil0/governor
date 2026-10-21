# 0016 — W2 Experiment B results: a device-wide clock lock vs a compute-bound foreground
Date: 2026-10-21 · Phase: W2 · Author: Claude Code (run by Arjun, admin shell, AC, clean tree)
## Question
What does a device-wide SM clock lock (the lever the governor would pull for a background job) cost a foreground frame workload, with and without a memory-bound background?
## Run
Run 20261021T105205Z (10 blocks x 36 cells = 360 cells; data/raw/w2_B/20261021T105205Z, results in data/w2_B_results.md). An earlier launch (20261021T104818Z) was interrupted by accident before any cell completed (results.csv has the header only); it is ignored. Zero clock-excursion flags. The only flag is `fg_incomplete`, on 220 cells; every one of them is a cell with miss fraction 1.0 (overloaded), where the window ended before all requests finished. Cells stay in the data; per the overload rule only miss fraction and service time are interpreted there.
## Results (all from data/w2_B_results.md)
- **HB1 SUPPORTED** (fma frames, all levels): service time ratio vs 1800 MHz is 1.999 / 1.500 / 1.203 at 900 / 1200 / 1500 (predictions 2.000 / 1.500 / 1.202), CIs within 0.0005 of the median. A compute-bound foreground slows exactly in proportion to the clock.
- **Descriptive 1050 MHz**: fma ratio 1.714 (60 Hz) and 1.714 (120 Hz) vs the interpolated 1.714; i.e. the fp16-proxy knee costs a compute-bound foreground 71% longer service time.
- Memory-bound frame (mem_60hz): ratios 1.011 (900), 1.005 (1200), 1.002 (1500), 1.009 (1050). The W1 prediction at 900 (1.123) was NOT met (tolerance 0.05): the frame is less clock-sensitive than W1's model said. HB1's registered text covers the fma frames, so this is a reported miss of the memory-frame reference, not a change to the verdict.
- **HB2 with no background: SUPPORTED** for both fma frames: the deadline-miss fraction rises significantly at 900 and 1200 (Wilcoxon p = 0.00098, Holm 0.0029, 10/10 blocks); 1500 is not different from 1800 (as predicted, p = 1).
- **HB2 with the memory background: NOT SUPPORTED, and not testable as designed.** With the background present, the miss fraction is 1.0 at EVERY level including the 1800 MHz reference and unlocked (median latency 2.5 s unlocked to 12 s at 900, with a fg GPU time of 6-24 ms). The reference itself is overloaded, so there is no level at which the clock lock "causes" the misses. The effect that dominates is time-slicing with the background, not the clock.
- Power (counter, median): the lock saves board power for the no-background frames (fma_60hz: 56.5 W unlocked, 38.5 W at 1800, 26.4 W at 1200), but the 900 and 1050 cells are overloaded, so those savings are paid for with missed deadlines.
## Interpretation and limits
- A device-wide lock is only free for the foreground if the foreground is memory-bound; for a compute-bound frame the cost equals the clock ratio, so the lock level is bounded by the foreground's deadline slack: at 60 Hz fma, 1200 MHz already misses (service 18.2 ms vs 16.7 ms budget), 1500 does not (14.6 ms).
- That bound is about THIS frame size (unlocked service sized to about 53% of the budget, per the yaml); a lighter foreground would tolerate lower clocks. The data show the proportionality, not a universal threshold.
- The membg result is a finding about co-location (the 1 ms memory background with time-slicing starves the 60/120 Hz frames regardless of clock), measured here with a continuously running background and no priority control; it says nothing about duty-cycled backgrounds (A2 covers that).
- HAGS ON; board-level counter with the W1 caveats.
## Next
Commit B (results + raw data); register the llama.cpp addendum (decisions in the draft), download/build/sanity check, stop before the full run; then Experiments A and A2.
