# STATUS (overwritten at every stop)
Updated 2026-10-23 · Phase: W4-5. Reviewer decisions on smoke 2 applied; the FINAL driver (pace-view fix + clean-token estimate) is built; smoke 3 READY for you. Yaml draft 3b is UNCOMMITTED (excluded from git) for re-review.

## Just did (journal 0042)
- Correction recorded: smoke-1 "guard must be learned / guard 0 unsafe" WITHDRAWN; smoke-1 aligned-driver and governor numbers (c'B 5.7% miss, tok/s) INVALID (data/w45_smoke/smoke1/README_INVALID.md); the learned controller is justified by the unseen workload and the per-workload clock choice under a power budget. No W1/W2 experiment used the pace-block reader (shm/ring code first committed 2026-10-22, after W2 closed).
- Granularity limitation recorded (plan addendum H, yaml limitations, PAPER_MAP 23, CONCEPTS): a clean token (10.1 ms) exceeds the slack at c0 >= about 6.6 ms; aligned admits <= 1 token/frame (about 60 tok/s) at light frames and about none at heavier ones; sub-token pacing = future work.
- Yaml: HW0 unchanged + c0 grid {7, 8, 9, 10, 11} ms (smallest meeting the gate); no open reviewer questions.
- Clean-token estimate implemented test-first (workloads/background/tok_estimate.h; 4 C++-vs-Python tests + source test), driver rebuilt, both estimates and the overlap flag logged per token in the driver CSV.

## Waiting for
1. You: smoke 3 with the commands in docs/W45_SMOKE3_SETUP.md (given again in chat, including warm).
2. Reviewer: re-review yaml draft 3b.

## Next (after smoke 3)
Addendum with the smoke-3 result (fit test at costs 4 / 7 / 9 ms, both estimates), then W5a (load pre-check addendum first).

## Notes
- Simulator frozen. Run checklist: Administrator PowerShell; AC power; clean committed tree; Armoury mode stated; Chrome closed; tray apps quit; no clicking; warm every new exe (the driver exe was rebuilt twice since smoke 2; `warm` is step 1).
