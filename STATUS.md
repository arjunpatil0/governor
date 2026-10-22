# STATUS (overwritten at every stop)
Updated 2026-10-23 · Phase: W4-5. Smoke 3 recorded; reviewer notes 1-4 applied. Yaml draft 3b is UNCOMMITTED (excluded from git) and PRESENTED FOR FINAL REVIEW before commit and W5a.

## Just did (journal 0043; report data/w45_smoke/smoke3_report.md)
- Smoke 3 (final driver): measured frame alone 3.0 / 5.2 / 6.7 ms for nominal 4 / 7 / 9 ms. Aligned gates correctly: 60 tok/s (1 token per frame) at 3.0 and 5.2 ms, 0 tok/s at 6.7 ms, 0 misses; overrun 0% / 0.5% (max 3.3 ms). Unaligned duty 1 at nominal 9 overloads the fg (100% misses, p50 308.6 ms). Clean-token estimate steady at 10.1 ms.
- My unit error corrected: the 6.8 ms I used for nominal 7 was the contended smoke-2 median; alone it is 5.2 ms, so aligned pacing works at nominal 7 (my earlier expectation was wrong). The 6.57 ms boundary is in measured time (about nominal 8.8 ms).
- Yaml: gate needs bg tok/s >= 20% of background-alone; c0 = nominal cost, measured frame time recorded per block, grid {7..11} nominal; HW7 pre-states the clean-estimate staleness check around clock changes.
- Helper: 3 NVML reset errors in this log (first reset after a successful RESET) were handled as "reset not needed"; cause still unexplained (probe passed 12/12).

## Waiting for
1. Reviewer: FINAL review of experiments/w5_governor.yaml (draft 3b). No open questions.
2. Then (after your go): commit the yaml with a dated addendum, then W5a starts with its load pre-check addendum (8B load check, held-out choice) first.

## Notes
- Simulator frozen. Run checklist: Administrator PowerShell; AC power; clean committed tree; Armoury mode stated; Chrome closed; tray apps quit; no clicking; warm every new exe.
