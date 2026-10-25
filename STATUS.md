# STATUS (overwritten at every stop)
Updated 2026-10-25 - Phase: W4-5. Reviewer decision on c'B implemented (addendum O-7 section 5, journal 0060): TWO c'B comparators, constants RE-FROZEN, trial now 7 cells. NOTHING run on hardware. Waiting for YOU: restart -> helper -> Step A (trial, about 14 min) -> if PASS, Step B (session 1 = blocks 4 and 9, about 2.4 h). Literal commands with the hash: docs/W5B_EVALUATION.md.

Addition 2026-10-25 (journal 0061): check_trial now also fails a governed cell (cB/dB/eB) without the per-tick log (pacing mode + sampled power) or the 0.5 s power trace, or with them empty / under 90% of the 65 s loop (650 ticks, 130 bins). Constants hash unchanged.

## Frozen constants (data/w5b/constants.json, sha256 f7b99650efe7fea9d392a1aee2e49a18a84a00fe69d56fb4e41bf562cc6fb4a9)
c0 7 ms; g'B 60 W = 1800_a_g0_d1, 35 W = 1500_a_g0_d1; c'B-T3b (PRIMARY) 0.5 / 0.15; c'B-T3c (secondary) 0.2 / 0.15; d'B margin 0.3; headroom 2.692 W.

## What changed
- Every block: 30 cells at 60 W (both c'B variants), blocks 4-8 +25 at 35 W = 55. Blocks 4+5 no longer fit one 3 h session (3.06 h; the runner refuses): sessions (4 9) (5 10) (6 11) (7 12) (8 13), 85 cells = 2.4 h each.
- Analysis: c'B-T3b primary (S5 Holm over 3, non-inferiority, earns_place); c'B-T3c secondary section. results.csv has final_pacing_mode. Governed cells now also log per-tick mode + sampled power (not exercised on hardware yet).
- Tuning-data result (PAPER_MAP 30): no c'B combination dominates d'B at margin 0.3 (3.08% miss vs 0.86% at 30.5 tok/s); not held out.
- ev04_S1_dB_35 (37.6 W at 35 W): a controller limit (fastest clock in the x1.3 phases, 32% of the loop at 2460 MHz; deadline first, power soft), not a plant floor (the 35 W static reaches 34.2 W at 19.5 tok/s) and no bug found; recorded as the exploratory result. Its per-tick power/mode were not logged: reconstruction uses reference cells.

## Risks / not verified
- Everything on hardware with the frozen constants (incl. the new trace logging and c'B through idle phases). The yaml still says "c'B" (read as c'B-T3b). d'B-HGB and S3 not built.

## Notes
- Full suite 604 passed, 1 skipped. Exe hash bb875fbc unchanged. Sleep settings may still be at 0 on AC.
