# STATUS (overwritten at every stop)
Updated 2026-10-23 - Phase: W4-5. First hardware trial crashed on a 2475 MHz clock reading and confirmed the granularity blocker; both FIXED test-first (clamp + d'B in the shared action space); addendum O-1 written; the overnight sitting restructured (no d'B cells). Waiting for YOU to restart, run the trial again (all six cells must pass) and then the sitting.

## Just did (journal 0051)
- Clamp: live clock mapped into [600, 2460] MHz before any controller, every clamp logged (14 tests). All live-clock paths go through Governor.step.
- d'B: aligned + unaligned ModelControllers, mode chosen every 1 s by predicted tok/s with hysteresis (6 new tests + updated hybrid tests; frozen-simulator unit harness: 0 -> 12 tok/s at 10 ms frames, the unaligned plan is optimistic so the margin knob matters).
- Addendum O-1 (docs/W5B_ADDENDUM_O1.md). d'B margin grid moved to block T3b (with d'B-HGB). Sitting dry run: 127 cells. Ctrl+C fix verified elevated (PASSED).

## Your next steps (docs/W5B_TUNING_SITTING.md has the literal commands)
RESTART -> Admin helper (step 1) -> trial2 (python experiments/w5b/tune.py --out data/w5b/trial2 --armoury-mode Performance --trial) -> paste the six TRIAL lines -> if all six pass, the overnight command (step 4) within the same 2 h of uptime, with the powercfg lines; morning checks in step 5.

## Waiting for
Reviewer: c'B mode is fixed per cell while d'B can switch (asymmetry, your call); O-1.

## Risks / not verified
- Governed c'B and d'B cells have never completed on hardware; d'B dual mode only validated in the frozen simulator and on synthetic observations; unaligned instance uses the 3B L table; c0m/nominal ratio 0.954 vs 0.745 in smoke 3 unexplained; cell time and size are estimates (127 cells in the dry run).

## Notes
- Do not run pytest or rebuild before the sitting; tree committed; exe hash bb875fbc unchanged.
