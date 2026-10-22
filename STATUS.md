# STATUS (overwritten at every stop)
Updated 2026-10-22 · Phase: W4-5. Decisions applied; smoke 2 prepared and READY for you to run. Yaml draft 3b is UNCOMMITTED (excluded from git) for re-review.

## Just did (journal 0040)
- reset_probe: 12/12 resets ok (busy/idle, locked/unlocked): neither hypothesis reproduced; the two smoke-1 reset errors stay unexplained; helper handling unchanged.
- d'B = hybrid (idle = eB rule; active = learned model + learned guard): plan addendum F + yaml, before any W5b data. Not simulated (frozen); controller code to be written test-first AFTER smoke 2.
- Non-inferiority fixed: d'B >= 95% of EACH of c'B, g'B, eB (yaml HW2). S2 now checks the hand-over, not learning (stated in the yaml).
- Smoke 2 built: analysis/smoke_overrun.py (tests GREEN) + `overrun` step; commands in docs/W45_SMOKE2_SETUP.md. CLAUDE.md checklist line and PAPER_MAP rows 15-19 added.

## Waiting for
1. You: run smoke 2 (docs/W45_SMOKE2_SETUP.md: Admin window restarts the helper; second window `warm` then `overrun`; Performance mode, Chrome closed, hands off), then Ctrl+C the helper and paste `nvidia-smi -q -d CLOCK | Select-String "Applications|SM"` plus the helper's last lines.
2. Reviewer re-review of experiments/w5_governor.yaml (draft 3b; one new question at its end).

## Next (after smoke 2)
Diagnose the guard-0 overrun from data/w45_smoke/smoke2 (addendum before W5a), write the hybrid d'B test-first, W5a (load pre-check addendum first).

## Notes
- Simulator frozen; round 3 is not evidence about hardware.
- Run checklist: Administrator PowerShell; AC power; clean committed tree; Armoury mode stated; Chrome closed; tray apps quit; no clicking; warm every new exe once (the governed driver exe was rebuilt: `warm` is step 1).
