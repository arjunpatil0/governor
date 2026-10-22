# STATUS (overwritten at every stop)
Updated 2026-10-22 · Phase: W4-5. STOPPED MID-WORK because the usage limit was reached. Helper stopped by Arjun (clock unlocked, SM 1980 MHz, -rgc/-rmc run).

## Done since the last STATUS (committed unless noted)
- Reviewer note 1: helper now treats an NVML reset error as "reset not needed" when it knows no lock is held (distinct log line), real failure otherwise; governor-side `nvidia-smi -rgc` fallback when the helper reports `OK dirty` (ControlActuator fallback_reset). Tests GREEN. Log evidence partly contradicts "errors on already-unlocked": two back-to-back resets succeeded; both failures followed GPU idleness. Diagnostic for you (elevated, helper stopped): `python experiments/w4_smoke/reset_probe.py` -> data/w45_smoke/reset_probe.json (not run yet).
- Reviewer note 2: run.py Armoury refusal is now a tested function (checked first); `chrome_running` added to meta; smoke writes meta.json (Armoury NOT_RECORDED flagged, Chrome, processes).
- Round 3 groundwork (UNCOMMITTED, tests partly RED): plant/ObsBuilder/Governor report per-token slack overrun (`overrun_ms`); new tests for d'B v3 (learned guard from overrun, budget-respecting idle branch, power loop on the model duty) are written but ModelController v3 is NOT implemented; one plant overrun test still fails (ValueError in test_sim_plant.py:245, not yet diagnosed).

## Not done (next session)
1. Finish v3 in controllers/model.py (guard_fb, _plan_idle under budget, pdelta power loop), fix the plant overrun test, round 3 script on seeds 400-429 (last sim round) with the reviewer's reading: S5 REQUIRED (win vs c'B, g'B, eB) and non-inferiority >= 95% of the best comparator in S0 and S2 (CI lower bound of the paired ratio), tuning on tuning seeds only.
2. Update experiments/w5_governor.yaml (uncommitted draft 2): 8B fallback chosen by load pre-check only; the new "earns its place" reading; learned guard in d'B; Armoury mode + Chrome recorded; then stop for re-review.
3. Journal 0039 (smoke incident: reset error; reviewer decisions), response notes, commit.

## Notes
- Do not trust the tree as clean: uncommitted edits in sim/plant.py, telemetry/obs_builder.py, controllers/runtime.py and new tests (some RED).
