# W4-5 plan: governor MVP (DRAFT, awaiting approval; written 2026-10-22, no code yet)

## Goal (Arjun + reviewer, 2026-10-22)
Demo: a foreground with a frame deadline keeps deadline misses <= 1% while a real llama.cpp background runs; maximise background tok/s and minimise GPU power, versus no governor.
Order: plan -> simulator -> controllers vs simulator -> daemon + actuators -> hardware smoke. Stop before any full experiment. W5 yaml is committed before any governor data.

## What the committed results give the simulator, and what they do not
| Plant term | Source | Gap |
|---|---|---|
| fg service time vs SM clock (compute-bound): 1/f, ratios 1.999 / 1.500 / 1.203 at 900 / 1200 / 1500 vs 1800 | data/w2_B_results.md | measured WITHOUT background |
| fg slowdown vs bg duty (4 ms fg: 1.36 / 1.67 / 2.13 at duty 0.25 / 0.5 / 0.75; 9 ms fg: 1.17 at 0.25, overloaded at >= 0.5) | data/w2_A_secondary_results.md SA4 | measured at 1800 MHz, synthetic bg with 2 ms slices, only two fg sizes |
| co-run wait cap tau 0.258 ms; q 0.374 ms, s 0.148 ms; long-fg slowdown 2 + 2s/q = 2.79 | data/w2_G_results.md, data/w2_G_posthoc.md | q, s share the on-interval definition (possible bias) |
| bg tok/s and J/token vs SM clock (97.25 tok/s at 56.3 W at 1500; 101.1 at 92.0 unlocked; 0.526 J/token at 1050) | data/w2_L_results.md | bg ALONE; one model, batch 1 |
| actuator latencies, NVML update intervals | data/capability_audit.md | see risks |

Not measured anywhere, and the simulator must say so in its header:
1. fg time as a JOINT function of (clock, duty). Marginals only. The simulator assumes separability (clock factor x duty factor); W5 hardware smoke tests it.
2. bg tok/s while sharing with a fg (L is bg alone), and bg tok/s vs duty for token-level pacing. A2's duty was slice-level (2 ms), llama decode is ~10 ms per token, so token pacing is a different burst regime.
3. fg behaviour with idle phases (needed for "knee clock when fg is idle").
The simulator is therefore parameterised only from committed results PLUS a separability assumption, and carries a sensitivity switch (interaction term) so every controller result is also shown under a pessimistic interaction.

## Phase 0: housekeeping (this session)
- Settings: ECC_GATEGUARD=off set in ~/.claude/settings.json env (done; takes effect on the next Claude Code start). Kept: tdd-workflow, /ecc:plan, /code-review, /security-scan.
- Pending from Arjun: OneDrive hash of the w2_G copy (REC_MANIFEST.sha256 comparison). Not blocking.

## Phase 1: simulated plant (RED/GREEN first)
Files: sim/plant.py, sim/params.py (reads the numbers FROM the committed result files at load time, no typed constants, same rule as B's HB1 predictions), tests/test_sim_plant.py.
- Inputs per step: SM clock (MHz), bg duty (0-1), fg state (active/idle), time. Outputs: fg frame-time distribution (median, tail via a lognormal fitted to SA4 p99/p50), bg tok/s, GPU power (from L, interpolated in clock), temperature (first-order lag, optional).
- Overload region: the plant must reproduce A2's overload (9 ms fg at duty >= 0.5) as a hard infeasible zone, not smooth it away.
- Tests (RED first): reproduces each committed anchor within its CI (B ratios, SA4 slowdowns, L tok/s and W); monotonicity (higher duty never speeds the fg; lower clock never speeds the fg); rejects any parameter that cannot be traced to a file; deterministic given a seed.
- Gate: all anchor tests pass; header prints the three unmeasured assumptions above.

## Phase 2: controllers vs the simulator
Files: controllers/{none,static,pi,model}.py, sim/scenarios.py, sim/run.py, tests/test_controllers_sim.py, analysis/w5_sim_report.py.
- (a) none: duty 1.0, clocks unlocked.
- (b) best static: offline grid over (clock, duty) per scenario family, chosen on tuning seeds, evaluated on held-out seeds.
- (c) PI on fg frame-time error -> duty (anti-windup, rate limit, safe fallback duty 0 if the miss rate trips), plus deadline-aware clock rule: lowest clock whose PREDICTED frame time <= budget x margin; knee clock (1500 MHz for llama.cpp Q4_K_M, L) when the fg is idle. Margin and PI gains tuned on tuning seeds only. The int4 knee is not used.
- (d) model-based: per-workload predictor calibrated online (start: ridge regression on clock, duty, fg state; online RLS update with forgetting), constrained choice of (clock, duty) each step maximising bg tok/s - lambda x power subject to predicted miss <= budget with a safety margin; hard fallback to (c)'s safe point when prediction error exceeds a threshold.
- Scenarios (written down BEFORE running controllers): steady fg; fg idle/active phases; thermal drift (clock cap); bg model swap (different knee: fp16 proxy 1050 vs llama 1500) to test whether the learned part earns its keep; model mismatch (separability broken by the interaction term).
- Metrics: fg miss fraction (target <= 1%), bg tok/s, mean GPU power, J/token, actuator changes per minute.
- Honest rule (reviewer): (d) must beat (c) on bg tok/s or power at equal miss rate, with a block-bootstrap CI over seeds; if it does not, we report that and keep (c).
- Sim results are labelled simulation, never quoted as hardware. A controller is frozen (parameters committed) before any hardware run.
- Gate: (c) holds <= 1% miss in every feasible scenario; (d) vs (c) result recorded either way.

## Phase 3: telemetry daemon
Files: telemetry/daemon.py, telemetry/ring.py (shared-memory ring), tests/test_daemon.py.
- One process, target 10-20 Hz, QPC timestamps (same timeline as the W2 runs). Sources: fg frame times (own instrumentation, ADR-0005; fg publishes (t_start, t_end, deadline) to a shared ring), bg tokens (driver publishes token end times), NVML power, SM/mem clock, temperature, event reasons, cumulative energy counter (total_energy_j, 0.49 ms call; used for J, not integrated power).
- Every row carries sample AGE per source: the capability audit shows NVML power updating at a median 22 ms (p90 500 ms), utilisation 1 s, temperature 1.77 s, so a 20 Hz poll mostly returns repeated values. The daemon logs a change flag and never presents a stale value as fresh.
- Output: append-only CSV per run with an execution-mode header; logging must not stall the loop (queue + writer thread; test with an injected slow disk).
- Tests (RED first): timestamps monotone; loop period p99 within budget on a no-GPU fake source set; stale-flag logic; drop counter when the ring overflows.

## Phase 4: actuators
4a. llama.cpp pacing. NEW driver workloads/background/llama_governed_bench.cpp (the L driver stays untouched so L stays reproducible). Reads duty from a named file mapping updated by the governor; sleeps (duty_gap logic from workloads/common/loadgen.py) between tokens; publishes token times to the ring; same GPU-only checks as the L driver (aborts if any layer is off the GPU; EXEC_MODE line). Token-level pacing means duty granularity of about one token (~10 ms): the simulator and the controller see the real granularity.
4b. SM clock lock via a minimal allowlisted admin helper: actuators/clock_helper.py (elevated, one process).
- Interface: named pipe, ACL limited to the current user SID; two verbs only: LOCK <mhz> (mhz must be in an allowlist read from a config file writable only by admin, e.g. the levels W1/W2 used) and RESET. No shell, no subprocess, no path or free-text arguments; calls NVML directly (nvmlDeviceSetGpuLockedClocks / nvmlDeviceResetGpuLockedClocks) to avoid nvidia-smi spawn cost (audit: 443 ms per call; ADR-0004 had ~81 ms) and the command-injection surface. Verify by running that NVML locking works and how fast; if not, fall back to a fixed-argv nvidia-smi call.
- Fail-safe: reset on normal exit, on exceptions (finally), on console close/Ctrl+C/Ctrl+Break (SetConsoleCtrlHandler), on client disconnect, and on watchdog timeout (no heartbeat from the governor for N seconds, N from config). The lock has no server-side expiry, so the helper's own death is covered by: reset on startup, and a documented manual recovery (nvidia-smi -rgc). Whether locks survive a driver reset or reboot will be CHECKED by running, not assumed.
- Rate limit on LOCK (the controller cannot flap the clock faster than the measured actuation latency).
- /security-scan on the helper (and config) before any hardware run; findings answered in a response file.
- Tests: protocol fuzz (unknown verb, huge payload, non-integer, out-of-allowlist), reset-on-disconnect, reset-on-watchdog with a fake NVML, no code path that starts a process (static check).
4c. bg CPU priority/EcoQoS: actuators/cpu_qos.py (audit: priority class, affinity, EcoQoS, job-object cap all work unprivileged; EcoQoS cut a spin loop 13x, so it can hurt the CPU side of decode; the simulator gets a CPU-side term only if measured, otherwise the actuator is logged but not controlled in the MVP).

## Phase 5: hardware smoke (short; NOT a result)
- Checks only: helper locks/resets and survives kill -9 of the governor (watchdog), daemon rates, driver pacing granularity, measured actuation latency, one 2-minute (a)/(c) pair to confirm the plant is roughly right and the demo is feasible. No hypothesis is tested; nothing from it is quoted as a finding.
- Needs an Administrator PowerShell, AC power, tray apps quit, no parallel work from me while it runs (CLAUDE.md run protocol; I state the Armoury Crate mode before).

## Phase 6: W5 pre-registration (before any governor data)
experiments/w5_governor.yaml (+ dated addenda later): hypotheses (HW1: (c) vs (a): miss <= 1% and bg tok/s ratio; HW2: (c) vs (b); HW3: (d) vs (c); HW4: power and J/token vs (a)), scenarios, fg workload and deadline, warm-up, blocks, randomised order, tuning/eval split, primary tests (paired Wilcoxon, Holm), decision rules including the "(d) does not beat (c)" outcome, abort criteria (clock not restored, thermal cap, driver reset), and the commit hash of the frozen controller parameters. Committed and reviewed before the first full run. I stop there.

## Foreground definition (needs your OK)
A synthetic frame-paced fg from the W2 DLL (compute-bound FMA frames, own timing), deadline = frame period (e.g. 60 Hz, 16.7 ms), size chosen by a FEASIBILITY GATE: with no governor the miss rate must be clearly above 1%, and with the best static (clock, duty) it must be achievable below 1%. Otherwise the demo is vacuous. B warns that W2's fma_60hz fg against the memory bg already missed about 100% at 1800 MHz, so the size matters. A real application as fg (game/video) is W6+.

## Risks
| Risk | Likelihood | Mitigation |
|---|---|---|
| Separability of clock and duty effects is false | Medium | Sensitivity switch in the sim; smoke measures one joint point; W5 calibration block pre-registered |
| Clock actuation too slow/lumpy for a per-frame rule (nvidia-smi 443 ms) | High | Clock rule runs on a slow loop (about 1-2 Hz), duty on a fast one; NVML-direct helper measured in Phase 4 |
| NVML power/temp are slow or stale at 20 Hz | High | Age flags; energy counter for J; controllers use fg frame times as the fast signal |
| Token-level pacing too coarse for tight duty control | Medium | Granularity is in the sim; fallback is pacing every N tokens |
| (d) cannot beat (c) | Medium | Pre-agreed: report it; keep (c) |
| Helper leaves a clock lock after a crash | Medium | Multi-path reset, startup reset, manual recovery documented, security scan |
| Simulator tuned on the same data used to claim hardware success | Medium | Controllers frozen before hardware; hardware eval on pre-registered seeds, never tuned on |
| Background apps / thermals add noise | Medium | Run checklist, processes in meta.json, thermal flags |

## Out of scope for W4-5
VRAM paging governance, Linux/MPS arm, PresentMon, ryzenadj, power limit (unsupported), multi-GPU, real-application fg, any hardware run longer than the smoke.

## Complexity
High: roughly six working sessions (my estimate, not a measurement), plus one admin-hardware session for the smoke.

## Commit plan
One commit per RED, GREEN, refactor checkpoint (tdd-workflow), a docs commit per phase, a journal entry per session, STATUS.md at every stop, push each session.

---
# APPROVED 2026-10-22 with three modifications (Arjun + reviewer). Supersedes the unmodified parts of this plan where they conflict.
Instruction (verbatim): "approve the W4-5 plan with three changes, recorded in the plan and journal ... Then start: simulator -> controllers vs simulator (test-first). Stop before hardware smoke."

1. **Frame-synchronous ("slack-filling") pacing is an actuator option.** Pacing mode `aligned`: bg decode tokens are released right after each fg frame completes, into the predicted slack before the next frame (n tokens such that n x token time <= predicted slack x margin). Mode `unaligned`: the plan's duty cycle (gap after each token = token time x (1/duty - 1), as workloads/common/loadgen.py duty_gap). Both are compared in the simulator and in the W5 evaluation as a pacing-mode factor: controllers c (PI -> duty, unaligned), c' (PI on the slack budget, aligned), d (model-based, unaligned), d' (model-based, aligned).
2. **Fg-variability scenario.** Frame cost steps/drifts by about +/-30% (light/heavy phases), so adaptation is needed. Best-static is tuned on the tuning seeds only and evaluated on held-out seeds.
3. **Synthetic frame-paced FMA fg for the MVP, with the feasibility gate** (no governor clearly above 1% misses; best static below 1%). A real application as fg is W6.

Execution scope now: simulator, then controllers vs simulator, test-first. STOP before the hardware smoke (needs Arjun's go, Administrator shell, Armoury Crate mode stated).

Backup: the w2_G copy hash B4581EA7...BEEE3 matches the REC_MANIFEST.sha256 line for cells/b00_00_g_R2/bg_rec.npz (checked by string comparison). That verifies that ONE file; the pasted path was truncated and the other 189 files are not checked.
