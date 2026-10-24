# STATUS (overwritten at every stop)
Updated 2026-10-24 - Phase: W4-5. T3b verified (67 cells; all 66 governed cells on the sampled source, 0 energy reads, counter vs sampled at most 2.9%); addendum O-6 written (c'B grid extension T3c, evaluation power tolerance = none, evaluation details); the evaluation runner is built and tested in the simulator. Waiting for YOU: restart -> helper -> the T3c command (docs/W5B_T3C_SITTING.md, 25 cells, about 42 min).

## Verified / decided (journal 0057, addendum O-6)
- d'B margin 0.3: mean miss 0.875% (rule met), 58.6 W, 26.5 tok/s; per scene S1 3B 2.0%, Phi 3.25%; S0 all 0 miss. Expected headline (pending evaluation): in S0 d'B makes 18.6 (3B) / 13.6 (Phi) tok/s where every budget-compliant aligned static makes none.
- c'B: rule not met in the T3b grid (3.3-5.8% miss); fallback at the grid edge (target 0.5) -> T3c extends to targets 0.35, 0.2 (24 cells), unchanged rule on the full grid, one extension only.
- Evaluation power tolerance: NONE (feasible only if counter power <= 60.0 W / 35.0 W; d'B at 58.1-59.9 W so some cells may score 0). O-4 contingency (5 s settle): does NOT trigger (0 of 66 cells with 3+ clock changes in the first 5 s).
- NOT checked: the helper log of the T3b sitting (Administrators-only; the T3c doc asks you to paste the notable lines).

## Built (test-first, 65 related tests pass)
- Evaluation runner: eval_lib / evaluate.py / freeze.py (frozen constants checked by sha256, whole blocks, 3 h session check, incomplete blocks discarded, results.csv for the registered analysis, 6-cell supervised trial); a simulator dry run of block 4 fed the analysis. Not run on hardware.

## Waiting for
1. You: T3c (docs/W5B_T3C_SITTING.md). Then I freeze data/w5b/constants.json, commit it, and give you the evaluation trial and session commands with the literal hash (docs/W5B_EVALUATION.md).
2. d'B-HGB: build only after T3c + freeze + evaluation trial; dropped if not ready when block 4 is scheduled (O-6 section 6).

## Risks / not verified
- Evaluation path on hardware (8B governed, eB/c'B/d'B in S2 idle phases, scene-time origin), S3 not built, d'B-HGB not built, helper log unchecked.

## Notes
- Do not run pytest or rebuild before the run; exe hash bb875fbc unchanged.
