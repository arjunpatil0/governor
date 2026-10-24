# STATUS (overwritten at every stop)
Updated 2026-10-24 - Phase: W4-5. READY for the unattended chain (journal 0058, addendum O-6 section 7): power headroom added (2.69 W, steering target 57.31 W at 60 W; c'B and d'B steer on it, feasibility stays on the counter with no tolerance), six d'B cells with the headroom added to T3c, and ONE chain script that runs T3c, the strict morning check, the mechanical freeze and the 6-cell evaluation trial with automatic checks, then STOPS. It cannot start evaluation block 1. Waiting for YOU: restart -> helper -> the one command in docs/W5B_T3C_SITTING.md (about 1.1 h).

## What the chain does (scripts/w5b_t3c_chain.ps1)
0 no-sleep settings; 1 T3c (31 cells: 1 discarded + 24 c'B grid-extension cells + 6 d'B cells with headroom); 2 strict morning check; 3 freeze (data/w5b/constants.json + sha256); 4 evaluation trial (6 cells incl. the held-out 8B); 5 automatic trial checks; STOP. Each step only if the previous passed. End summary prints c'B constants (rule met? grid edge?), the headroom, whether the d'B margin rule still holds with it, the constants hash and the trial cells.

## Decided / recorded
- Headroom = max(0, p95(counter - sampled), T3b, 67 cells) 1.05 W + max(0, p95(counter - 58.2 W), d'B cells at margin 0.3) 1.64 W = 2.69 W; controllers' budget parameter = (budget - headroom) / 0.97. The two terms overlap partly (conservative). If the six d'B cells fail the miss rule the headroom is KEPT and reported.
- Known limitation: tuning cells used scene time from the loop start, evaluation cells from the measured window.
- Evaluation power tolerance stays NONE (counter <= 60.0 W).

## Risks / not verified
- All on hardware (T3c with the headroom; 8B governed; eB/c'B/d'B in S2 idle phases); the chain script's run in a live PowerShell (its syntax is parse-checked); the helper log of earlier sittings (Administrators-only). d'B-HGB not built (dropped if not ready when block 4 is scheduled). S3 not built.

## Notes
- Do not run pytest or rebuild before the chain; exe hash bb875fbc unchanged. Re-freezing after review is allowed (no evaluation block will have run).
