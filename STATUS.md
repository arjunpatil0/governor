# STATUS (overwritten at every stop)
Updated 2026-10-22 · Phase: W4-5. Reviewer notes 1-4 applied; round 3 (LAST simulator round) done; simulator now FROZEN. STOPPED for review. W5 yaml draft 3 is UNCOMMITTED (excluded from git) and waits for your re-review.

## Just did (commits; see git log; journal 0039)
- Helper reset incident: the log does not support "reset errors when already unlocked" (back-to-back resets worked); both failures came after the GPU was idle. Fix (tests GREEN): reset error in a known-unlocked state is logged "reset not needed", otherwise a real failure; the governor runs `nvidia-smi -rgc` when the helper reports `OK dirty`. Diagnostic NOT run yet: elevated shell, helper stopped: `python experiments/w4_smoke/reset_probe.py`.
- Armoury/Chrome: run.py refusal is a tested function checked first; meta.json records chrome_running; the smoke writes meta.json.
- Round 3 (post-hoc, seeds 400-429): d'B v3 (learned guard from observed overrun, budget-respecting idle branch, power loop). Pre-registered reading: S5 wins hold against c'B (+10.6 tok/s), g'B and eB (+5.2); S0 non-inferior (ratio 0.969); S2 FAILS (ratio 0.726 vs eB): a bg-power-scale/duty-offset interaction made the idle branch too timid (diagnosed, not fixed: the sim is frozen). Verdict: does NOT earn its place.
- Yaml draft 3: 8B fallback by load pre-check only; S5 required + 0.95 non-inferiority reading; learned guard; Armoury/Chrome recorded. It now parses (draft 2 had YAML syntax errors).

## Waiting for
1. Your re-review of experiments/w5_governor.yaml (2 questions at its end: fixed vs per-scene non-inferiority comparator; second short smoke before W5a?).
2. Optional: run reset_probe.py as above and tell me the output.

## Decisions needed
1. One question: do a SECOND short hardware smoke (about 20 min, helper + GPU, token-duration ring and learned-guard overrun signal) before W5a, to find out why guard 0 overruns on hardware - yes or no? I recommend yes: the whole learned-guard design depends on it and the simulator can no longer answer it.

## Notes
- Simulator frozen. Its token timing is wrong (smoke); round 3 is not evidence about hardware.
- Open: CLAUDE.md run-checklist line "record Armoury mode and Chrome state in meta.json" (not yet added); PAPER_MAP entries at phase end.
- Run checklist: Administrator PowerShell; AC power; clean committed tree; Armoury Crate mode stated; Chrome closed; tray apps quit; no clicking in the console; warm every new exe once (the governed driver exe was rebuilt: it will be warmed again).
