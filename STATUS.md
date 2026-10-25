# STATUS (overwritten at every stop)
Updated 2026-10-25 - Phase: W4-5. T3c reviewed, constants RE-FROZEN, evaluation commands prepared; NOTHING run on hardware since the chain (journal 0059, addendum O-7). Waiting for YOU: restart -> helper -> Step A (trial re-run, about 15 min) -> if PASS, Step B (blocks 4 and 5, about 2.5 h). Literal commands with the hash: docs/W5B_EVALUATION.md.

## Frozen constants (data/w5b/constants.json, sha256 4aa2541d14271e00a9cfc245e2ad71aecab3ded795ce00a5c92193f1834f5974)
c0 7 ms; g'B 60 W = 1800_a_g0_d1, 35 W = 1500_a_g0_d1; c'B target 0.2 ki 0.15 (O-7 pick = registered pick; the miss rule is NOT met; grid edge; 0.6 tok/s); d'B margin 0.3; headroom 2.692 W (steering parameter 59.080 W at 60 W).

## Decided / recorded (addendum O-7, docs/W5B_ADDENDUM_O7.md)
- c'B fallback = fastest combination within d of the lowest mean miss; d = p95|replicate miss diff| / sqrt(6) = 0.0816 points from 7 pairs (1 strict c'B, 6 d'B near replicates) -> NO change of pick: c'B stays the degenerate lowest-miss setting (0.6 tok/s), so d'B-vs-c'B non-inferiority is close to vacuous. The estimate is weak (one c'B pair). YOUR decision: better c'B noise estimate (about 12 replicate cells, 20 min) or an extra c'B comparator (e.g. t0.5 ki0.15, 17.3 tok/s) - not done.
- BUG fixed: headroom was computed over merged T3c data (dbh cells ran with 2.84 W, first freeze 2.64 W); now T3b cells only = 2.692 W as registered. The d'B confirmation (0.861% mean miss) ran at 2.84 W; reported, not re-run.
- 1B d'B 47.0 vs 68.9 tok/s = a mode flip (unaligned vs aligned) decided in the first 2 s; not a bug; 1B not in the evaluation; d'B can be bimodal: report the final pacing mode per cell.

## Risks / not verified
- Everything on hardware with the frozen constants (trial re-run is the first). Helper log: reported clean by you, not seen by me. First-trial observations: g'B 60 W S0 3B = 0 tok/s; d'B 35 W S1 3B drew 37.6 W (>35, infeasible); d'B 8B S5 5.03% miss. d'B-HGB not built (dropped if not ready when block 4 is scheduled); S3 not built.

## Notes
- Exe hash bb875fbc unchanged. Sleep settings may still be at 0 on AC (the chain set them); Step A says how to re-set them if reverted.
