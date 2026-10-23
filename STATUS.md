# STATUS (overwritten at every stop)
Updated 2026-10-23 - Phase: W4-5. Before trial2: c'B now switches pacing mode inside a cell (non-learned rule), c0m redefined at a locked 1800 MHz with the SM clock logged, addendum O-2 written. Waiting for YOU to restart and run helper -> trial2 -> sitting (docs/W5B_TUNING_SITTING.md).

## Just did (journal 0052)
- SwitchingPIController (c'B): unaligned when the recent measured frame time > 6.57 + 0.3 ms, aligned below 6.57 - 0.3 ms, dwell 5 s; 8 tests. d'B keeps its prediction-based switch.
- c0m = fg alone at a LOCKED 1800 MHz (+ c0m_unlocked, SM clocks of both); no rule reads c0m. The SM clock was NOT logged in trial_fgalone, so the boost-drop hypothesis is only consistent with the files (locked 1500 MHz frame 8.50 vs predicted 8.41 ms; smoke 3's 0.745 = 1800/2460), not confirmed; trial2 logs it.
- Gate / c0 search re-read: unchanged. At c0 = 7 aligned fits a token only above ~1920 MHz (only the unlocked static), so trial_static's 0 tok/s at 1500 MHz was expected.

## Your sequence
RESTART -> Admin helper -> powercfg -> trial2 (paste six TRIAL lines + the fgalone c0m / sm_ lines) -> overnight sitting -> morning checks. Literal commands: docs/W5B_TUNING_SITTING.md.

## Waiting for
Reviewer: the fixed 6.57 ms threshold for c'B is wrong for short-token workloads (1B); token-aware alternative offered in O-2.

## Risks / not verified
- Governed c'B and d'B cells never completed on hardware; d'B/c'B switching validated only in the frozen simulator and on synthetic observations; unaligned instance uses the 3B L table; cell time and size are estimates (127 cells in the dry run).

## Notes
- Do not run pytest or rebuild before the sitting; tree committed; exe hash bb875fbc unchanged.
