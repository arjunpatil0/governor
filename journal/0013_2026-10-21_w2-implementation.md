# 0013 — W2 implementation prerequisites built test-first; stopped before the first full run
Date: 2026-10-21 · Phase: W2 (implementation) · Author: Claude Code
## Question
Is everything the pre-registration (b86d36e) needs implemented and tested, so that Experiment C can be run?
## What we did (commits on the governor branch)
- Review round: reviews/2026-10-21_w2_prereg_review.md, findings 1–4 applied and 5 added as a limitation, in b86d36e; response in 95fca8f.
- RED/GREEN pairs: `108f1a6`/`c62f840` design expansion and clock-excursion flags (`experiments/w2_colocation/design.py`); `a8bc5a5`/`e629322` OLS-with-intercept, median CI, phase / slice-stretch / duty-gap helpers and the decision logic
  (`analysis/w2_stats.py`, `analysis/w2_analysis.py`, `workloads/common/loadgen.py`); `7cab6d7`/`f5d15b6` the DLL duty-cycle option (GPU integration tests: requested utilisation 0.25/0.5/0.75 achieved within ±0.04).
- Harness `70ab8b9` plus later edits: `experiments/w2_colocation/run.py` (parts A, A2, B, C). The parent holds NVML only; calibration, background, foreground and decode run as child processes on one QPC timeline; clock resets run in a finally block.
- 90 tests pass (`python -m pytest tests -q`).
## What happened
- Smoke runs of all four parts pass end to end. They are not results: one block, three cells, 0.5–1.5 s windows, no admin, no clock control. Flags fired as designed (clock excursions because nothing was locked, energy counter vs samples on short windows, `fg_incomplete:0.81` for an overloaded 120 Hz frame behind a memory background, ρ = 0.7500 for a requested duty of 0.75).
- Report drivers (A, B, C, A2) were exercised on synthetic inputs generated in the scratchpad (nothing synthetic in the repo): decisions came out as constructed. This checks the glue, not the science.
- Decode start-up measured at 0.07 s plus ~2 s CUDA context, so the per-cell start lead is 5 s (it had been 9 s for C, which would have taken the C run to ~1.8 h instead of ~1 h).
## Setbacks / surprises
1. **A property of the registered HA1.** Criterion (ii) (cell medians within ±25% of the prediction) fails for a world with a constant switch cost: with wait = prediction + 0.3 ms the slope is ~1 and the intercept recovers 0.3 ms, but small-m cells are then more than 25% off, so HA1 is "not supported" (test `test_constant_switch_cost_lands_in_the_intercept_but_fails_the_registered_25pct_rule`).
   The pilot suggested a switch cost of about 0.3 ms. HA1 was kept exactly as registered per Arjun's decision, so a rejection stays a real test; the intercept is reported next to it. Whether to add an intercept-adjusted secondary is Arjun's call and, if wanted, needs a dated addendum before Experiment A's data.
2. **The laptop was on battery during the last smoke runs** (power_plugged False): 55–60 W and 77 tok/s versus ~98 W and 104 tok/s on AC. The harness now refuses a full run off AC (the registration says AC); W1's harness only logged it.
3. A synthetic-input mistake of mine (service(1800) = 8.86 ms; the real value is 8.86/0.732 = 12.1 ms at 60 Hz and 4.42/0.732 = 6.0 ms at 120 Hz) briefly produced a misleading HB2 line; the functions were right, the generator wrong.
4. Fixed on the way: Windows could not delete an npz that was still open (now loaded and closed), my first bash append of the report driver failed to parse and wrote nothing (rewritten via a file).
## Known limitations of what was built
- SA3 pairs the high-priority cells (A2 run) with the normal-priority cells (A run) by block index across two sessions; A2 has no 0.1 ms fg-alone baseline (the registered 19-cell count has none), so the A run's baseline is used.
- The B background (memory slices, 1 ms) is calibrated at 1800 MHz and not re-calibrated per level; B frame units come from the pilot (sized unlocked).
- `dxdiag` is captured once per 6 h and reused (approved once per session), so a HAGS change between runs inside that window would not be seen.
## Decisions
None new; implementation of the registered design.
## Next
Arjun runs Experiment C from an Administrator PowerShell on AC with a clean tree; then `python analysis\w2_analysis.py --part C`; results and raw files are committed; C's knee feeds the B-level addendum before B runs.
