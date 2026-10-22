# STATUS (overwritten at every stop)
Updated 2026-10-22 · Phase: W4-5. Simulator follow-ups, telemetry daemon, governed driver and admin clock helper built test-first with NO GPU and no admin. STOPPED before the hardware smoke.

## Just did (commits; see git log)
- Backup verified: analysis/verify_rec_backup.py -> OneDrive copy OK 190/190 (earlier only 1 file).
- Sim follow-ups (post-hoc; frozen results kept): token jitter changes nothing (0 ms guard still wins); the scenario-agnostic static = aligned + unlocked clock + guard 0 ms and equals the per-scenario oracle; simplest honest design e = that + idle-triggered clock drop (gains only in fg-idle phases, -12 W). Pareto headline in data/w45_sim_followup.md and data/w45_sim_pareto.png; break-even lambda 0.75-0.88 tok/s per W (data/w45_sim_breakeven.md). d' vs c' is the primary learned-vs-feedback comparison (d' +4.3 in S1/S4, -3.4 in S1d). Details: journal 0036.
- Built (337 tests pass, 1 skipped): ring/daemon/obs builder/NVML source/fg publisher, governor loop, control actuator, pacing header with 801 golden cases, governed llama driver (compiled, not run), admin clock helper + client.
- Security: /security-scan (AgentShield) scanned 0 files, so it is not evidence. Code review by the security-reviewer agent -> fixes (failed reset now retried, shutdown final, admin-only config and directory, tighter pipe DACL, idle-client boot, rotated rate-limited log). docs/W45_CLOCK_HELPER_SECURITY.md.

## Waiting for
- Your go for the hardware smoke (short, NOT a result): helper lock/reset/watchdog/Ctrl+C on the real NVML, daemon rates, driver pacing granularity, one 2-minute (e vs d') pair. Before it I still write the synthetic FMA frame loop (workloads/foreground, uses telemetry/fg_publisher.py) test-first, and the W5 yaml draft.

## Decisions needed
1. One question: the smoke needs a one-time admin setup. OK for me to give you the exact PowerShell commands (create C:\ProgramData\governor with an admin-only ACL, write the helper config, start the helper) and then run the smoke while you stay hands-off?

## Notes
- A hard kill of the helper leaves the clock locked until restart or `nvidia-smi -rgc`; an optional logon task running `nvidia-smi -rgc` would cover it (not created).
- The first run of any freshly built exe is intercepted by an endpoint scanner here (14 s, body ran twice): warm each new exe once before measuring.
- Run checklist: Administrator PowerShell; AC power; clean committed tree; Armoury Crate mode stated; Chrome closed; tray apps quit; no clicking in the console.
