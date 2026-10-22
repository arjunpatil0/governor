# STATUS (overwritten at every stop)
Updated 2026-10-22 · Phase: W4-5. Hardware smoke DONE (plumbing, not a result); part L checked (clean); simulator round 2 with the unseen-workload scene S5 done; W5 yaml draft 2 written and still UNCOMMITTED, waiting for re-review. The clock helper is still running in your Administrator window.

## Just did (commits; see git log)
- Hardware smoke (data/w45_smoke/smoke1, journal 0038): helper lock/reset/watchdog/disconnect on real NVML work (settle 0.12-0.41 s, watchdog 3.6 s); daemon 20 Hz, 0 drops; frame loop matches the plant's clock law within 1.1%; governed llama driver runs all-GPU with the frame loop; governor loop (c'B) runs end to end. Plant vs hardware: unaligned no-governor case close (p99 13.56 vs 13.7 ms); aligned guard 0 is NOT safe on hardware - tokens end 1-4 ms after the next frame start (fg p99 13.5 ms instead of about 5.5) and duty 0.5 gives 20 tok/s instead of 31. Cause not established; the token ring now logs token durations.
- Part L first-launch check: clean (90/90 cells, token logs reproduce results.tokens exactly, no duplicates, first cell in line with the others, exe had run before). L's headline is not affected.
- Simulator round 2 (post-hoc, S5 unseen workload, d'B v2, new seeds 300-329): on the unseen workload d'B v2 gets 36.2 tok/s at 60 W vs 31.3 for the statics tuned elsewhere and 25.9 for the feedback controller; the workload-aware oracle gets 38.7. Under the pre-stated reading d'B v2 still does NOT earn its place (loses S0 by 5.0 tok/s vs c'B; loses S2 by 0.4 vs eB). d'B v2 failed its own tuning criterion (the idle branch ignores the 35 W budget) - a defect to fix in a round 3 with fresh seeds.
- Response to the yaml review: reviews/2026-10-22_w5_yaml_response.md. Yaml draft 2 (blockers 1-2, changes 3, 5 applied) is in experiments/w5_governor.yaml, excluded locally from git.

## Waiting for
1. NOW: stop the helper. In its window press Ctrl+C once, wait for the prompt, and paste back: (a) the last lines of that window, (b) `nvidia-smi -q -d CLOCK` (the "Clocks" and "Applications Clocks" sections), (c) `Get-Content C:\ProgramData\governor\clock_helper.log -Tail 40`. Then tell me "helper stopped"; I will load the GPU for 5 s and check that the SM clock is no longer locked.
2. Your re-review of experiments/w5_governor.yaml (open questions at its end: the 8B fallback rule; whether S5 must be required in the "earns its place" reading - I would require it).

## Decisions needed
1. One question: round 3 (fix the d'B v2 idle-budget defect and the S0/S2 small losses, fresh seeds 400-429) before any W5a hardware time - yes or no?

## Notes
- Smoke limits: Chrome was running, Armoury Crate mode not recorded, single runs. Not a result.
- Every new exe needs a one-time warm-up (the governed driver exe was rebuilt after the smoke because the token ring gained a duration field; it will be warmed again by the registry).
- Run checklist: Administrator PowerShell; AC power; clean committed tree; Armoury Crate mode stated; Chrome closed; tray apps quit; no clicking in the console; warm every new exe once.
