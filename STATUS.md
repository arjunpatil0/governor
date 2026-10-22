# STATUS (overwritten at every stop)
Updated 2026-10-22 · Phase: W4-5. Plan approved with 3 changes; simulator + controllers done test-first (simulation only). STOPPED before the hardware smoke.

## Just did (commits; see git log)
- Recorded the three changes (docs/W45_PLAN.md, journal 0034). Backup hash B4581EA7...BEEE3 matches the manifest line for cells/b00_00_g_R2/bg_rec.npz (1 of 190 files verified).
- sim/ (params parsed from committed results, plant, scenarios, tune, run), controllers/ (a, b, b', c, c', d, d'), docs/W45_SIM_PROTOCOL.md written BEFORE any controller ran, data/sim_calibration.json (share divisor S = 2.5 fitted to A2 SA4; RMSE 0.030), data/sim_tuned.json (frozen before evaluation), data/w45_sim_results.md + w45_sim_eval.csv (30 held-out seeds). 265 tests pass.
- Results (simulation only): no governor misses 33.8% in the +/-30% fg scenario; aligned (slack-filling) controllers hold the 1% SLO in all 6 scenarios; the learned controllers beat the PI controllers (pre-registered rule: earns its place) BUT the best static aligned setting (unlocked clock, guard 0) beats all dynamic controllers on tok/s - 0.5 W in S1/S1d/S4; the dynamic ones win only in fg-idle phases and on power (about -25 to -30 W for -20 to -25 tok/s). Details: journal 0035.

## Waiting for
- Your go for Phase 3-4: telemetry daemon, llama_governed driver (aligned pacing), admin clock helper (+ /security-scan), all test-first and still without touching the GPU; then the hardware smoke needs your Administrator shell.

## Decisions needed
1. One question: keep lambda = 0.5 tok/s per W as the headline objective, or report the (tok/s, W) Pareto front instead? The winner flips with lambda (low lambda: static aligned unlocked; high lambda: c'/d' with lowered clocks). I recommend the Pareto front as the headline plus lambda = 0.5 as one marked point.

## Notes
- Plant caveats: separability of clock and duty untested; bg token time deterministic; fg jitter assumed 3%; calibration anchors are in-sample. Hardware smoke/W5 are the validation.
- Run checklist: Administrator PowerShell; AC power; clean committed tree; Armoury Crate mode stated; Chrome closed; tray apps quit; no clicking in the console.
- ECC_GATEGUARD=off is set in ~/.claude/settings.json (effective from the next Claude Code start).
