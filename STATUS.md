# STATUS (overwritten at every stop)
Updated 2026-10-22 · Phase: W4-5. Smoke 2 analysed; driver bug fixed; hybrid d'B written test-first; smoke 3 READY for you. Yaml draft 3b is UNCOMMITTED (excluded from git) for re-review.

## Just did (journal 0041; report data/w45_smoke/smoke2_report.md)
- Guard-0 overrun explained: not the guard. The driver treated a failed (mid-write) pace-block read as "fg idle", so tokens started at every fg publish (all stretched tokens start exactly 1.0 ms before an arrival; guard 0/0.5/1/2 ms give the same 27-30% long tokens; the driver's own fit test would admit 0-0.3% of the logged starts). Mechanism reproduced with the real C++ reader (25368 phantom-idle polls in 5 s vs 0 after the fix). Fixed in workloads/background/pace_view.h, exe rebuilt (needs a warm). Not proven per token.
- Measured: clean token 10.1 ms, overlapped token 20.7 ms (2.05x), overlapped frame 13.1 ms (1.95x); fg met the deadline in every run (p99 13.5 ms). My smoke-script tok/s for the background alone (57) was wrong (context limit); true 100.2 tok/s.
- Learned-guard recommendation: keep the design; confirm with smoke 3; possible clean-token-only estimate in the driver afterwards (journal 0041).
- Hybrid d'B implemented test-first (controllers/hybrid.py, tests/test_hybrid.py 6 tests); NOT simulated, not in sim/run.py. Yaml: S2 relabelled hand-over safety check; two new reviewer questions.

## Waiting for
1. You: smoke 3 (docs/W45_SMOKE3_SETUP.md: Admin window restarts the helper; second window `warm` then `gate`; hands off), then in the ADMIN window paste `nvidia-smi -q -d CLOCK | Select-String "Applications|SM"` and `Get-Content C:\ProgramData\governor\clock_helper.log -Tail 30`.
2. Reviewer: re-review yaml draft 3b (HW0 gate needs a larger c0 than 7 ms; driver token-estimate question).

## Next (after smoke 3)
Addendum with the smoke-3 result, decide the driver token estimate, then W5a (load pre-check addendum first).

## Notes
- Simulator frozen. Everything measured with the old driver describes a driver that ignored its own fit test.
- Run checklist: Administrator PowerShell; AC power; clean committed tree; Armoury mode stated; Chrome closed; tray apps quit; no clicking; warm every new exe (the driver exe was rebuilt again).
