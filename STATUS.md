# STATUS (overwritten at every stop)
Updated 2026-10-24 - Phase: W4-5. T1-T3 sitting verified (137 cells, c0 = 7); FINDING: all governed c'B cells report implausible power (63-106 W at 0-10 tok/s, 59-63 C) -> c'B constants VOID; c'B now has a token-aware threshold; T3b is prepared but gated on a diagnostic. Waiting for YOU: restart -> helper -> the diag+gate+T3b block (docs/W5B_T3B_SITTING.md).

## Verified (journal 0053, addendum O-3)
- 0 incidents, c0 = 7, background-alone 1B 234 / 3B 96.5 / Phi 72.2 tok/s, c0m 7.05 ms locked 1800 and 6.71 ms unlocked at SM 1890 (no-boost confirmed). g'B 60 W = 1800_a_g0_d1 (feasible in 3 of 6 cells), 35 W = 1500_a_g0_d1 (1 of 6): registered fallback. Ctrl+C fix works.

## Just did
- Token-aware c'B threshold (period - clean token; 6.57 ms for the 3B), test-first, addendum O-3. Second independent power measure in every cell + morning flag; --diag A/B + automatic gate; T3b (d'B margins + c'B re-tune, 67 cells) built.

## Waiting for
1. You: the restart -> helper -> diag -> (gate) -> T3b block. If the gate FAILS nothing else runs: paste the output.
2. Reviewer / you: d'B-HGB design points (addendum O-3 section 5): margin as required P(feasible) tau = 0.8 + 0.5 m; online calibration; slow loop. Not built.

## Risks / not verified
- Cause of the governed-cell power anomaly unknown (energy counter inflated vs real load); governed d'B/c'B behaviour on hardware unverified; c'B clock flip-flops at cell start; d'B-HGB does not exist (dropped if not ready before block 4).

## Notes
- Do not run pytest or rebuild before the run; exe hash bb875fbc unchanged.
