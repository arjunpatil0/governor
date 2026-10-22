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

Backup: the w2_G copy hash B4581EA7...BEEE3 matches the REC_MANIFEST.sha256 line for cells/b00_00_g_R2/bg_rec.npz (checked by string comparison). That verifies that ONE file; the pasted path was truncated and the other 189 files are not checked. (Later: the whole OneDrive copy verified, 190/190, journal 0036.)

---
# ADDENDUM 2026-10-22 (decisions by Arjun + reviewer; recorded BEFORE the W5 yaml and before the power-budget rerun)

## A. Primary objective changed
Primary objective: **maximise background tok/s subject to (i) the foreground deadline SLO (miss fraction <= 1%, p99 within the deadline) and (ii) a GPU power budget** (mean GPU board power over the measurement window <= budget). Budgets: **60 W ("AC-quiet")** and **35 W ("battery-like")**. The lambda Pareto front (tok/s vs W, lambda = 0.5 marked) stays as the SECONDARY view.
Reason: at lambda = 0.5, "unlocked + aligned" wins because power is cheap (data/w45_sim_followup.md, break-even lambda 0.75-0.88). Under a power budget the clock (and a throttle on the token rate) must be chosen per workload and scene, and a static unlocked setting is infeasible (74 W in S1 against a 60 W budget); that is where a per-workload model should be needed.
Consequences: (1) the frozen sim evaluation is rerun post-hoc under both budgets (labelled sensitivity; the frozen results stay); (2) aligned pacing gets a duty throttle (a token may start only after the slack test AND after the duty gap), the actuator that trades tokens for watts at a fixed clock; (3) controllers get a `power_budget_w` argument (None = the frozen behaviour); (4) the W5 yaml states the budgets as the primary factor.

## B. AI model-selection plan (for the learned part; replaces "start: ridge regression")
**Requirements.** CPU-only (the GPU belongs to the workloads); < 1 ms per predict + decide (10 Hz loop, many candidate (clock, duty) points); learn a NEW workload in <~ 10 s of data; calibrated uncertainty (the SLO bound uses an upper quantile, so a wrong confidence is a violation); deterministic given a seed; no network.
**Targets to predict, per (workload, scene, clock, pacing, duty):** fg frame-time quantiles (q50, q95, q99), bg tok/s, GPU power (energy-counter delta), and the error of each.
**Candidates (each with a CUSUM change detector on the standardised residual that triggers re-calibration / forgetting):**
1. grey-box + RLS: the current structure (clock law from W1/B, token time and power from L, interference multiplier) with online-calibrated scalars (c_hat, sigma_hat, gamma, power bias);
2. LightGBM (small, monotone constraints where physics gives them) on grey-box features + an online residual learner (RLS on its residual);
3. sparse Gaussian process (inducing points, Matern kernel) over (clock, duty, load features) with the grey-box as the mean function;
4. small MLP (<= 2 x 32, ensemble of 5 for uncertainty) with the grey-box as a skip connection.
**Pre-registered data collection (W5a, before any evaluation; a separate pre-registered hardware run).** Randomised factorial over SM clock level x pacing mode (aligned/unaligned) x duty/guard grid, balanced blocks, warm-up excluded, per-cell metadata (process list, Armoury Crate mode, temperatures). Workloads: Llama-3.2 1B, 3B (Q4_K_M, already in use) and 8B (only if it fits 8 GB with the context used: checked, not assumed), one other LLM family, one image generator (a diffusion model as a throughput background), and the synthetic frame-paced FMA fg in light / heavy / varying cost (the S1 steps). Logged through the daemon (QPC rows with per-source age) and the governed driver token ring.
**Evaluation (pre-registered).** Leave-one-workload-out (LOWO): fit on all other workloads, adapt online for 10 s on the held-out one, then score: p99 absolute error of the fg latency prediction, tok/s and power error, coverage of the stated 95% bounds (target 90-98%), prediction + decision latency on this CPU (p99). Also leave-one-scene-out for the synthetic fg.
**Selection rule.** The simplest model whose p99 error is within ~10% of the best model's p99 error AND that meets the latency bound (< 1 ms p99 for predict + decide) AND the calibration band. Order of simplicity: grey-box + RLS < LightGBM + residual < sparse GP < MLP ensemble. If grey-box + RLS meets the rule, the learned part is only the online calibration and the report says so.
**Non-evidence.** Simulator results do not count for this selection (the plant is built from the same grey-box structure); only W5a hardware data do.

## C. Fresh-exe double execution
Journal 0036 recorded that the first run of a freshly built exe took 14 s and executed its body twice. The cause is to be found (harness retry vs endpoint scanner) before any experiment depends on it; see journal 0037.

## D. Start-up clock reset
Every governor start first resets clock locks: helper RESET plus, when elevated, `nvidia-smi -rgc` and `nvidia-smi -rmc` (covers a hard-killed helper). Tested with a fake runner.

## E. Order of work
Admin setup commands -> this addendum + journal 0037 -> exe quirk investigation -> start-up reset -> power-budget rerun (post-hoc) -> synthetic foreground frame loop (test-first, no GPU run) -> W5 yaml DRAFT (uncommitted, for review). Stop for review before committing the yaml.


---
# ADDENDUM F 2026-10-22 (decisions by Arjun + reviewer; recorded BEFORE any W5b data and before smoke 2)

## F1. d'B becomes a hybrid
- **Idle branch = the eB rule** (idle detector of eB, 5 ticks without frames -> clock to the knee 1500 MHz with a free background, eB's constants). **Active branch = the learned model with the learned guard** (guard grows by the observed token-end overrun past the next frame arrival, decays slowly).
- Rationale: simulator round 3 (post-hoc; plant token timing known to be wrong) showed the learned model winning on the unseen workload (S5: +10.6 tok/s vs c'B, +5.2 vs g'B/eB) and losing only in the idle branch (S2 non-inferiority 0.726 vs eB: the pscale/pdelta power attribution made the idle plan timid), which a rule already handles.
- The hybrid has not been simulated (simulator frozen). Further fixes to the active branch use W5a hardware data and the W5b tuning blocks only.
- Honest consequence: in S2 d'B and eB use the same idle rule, so S2 checks the hand-over, not learning.

## F2. Non-inferiority comparator fixed in advance
d'B must reach >= 95% of EACH of c'B, g'B and eB in S0 and S2 (90% CI lower bound of the paired tok/s ratio), plus the required S5 superiority against each (HW2).

## F3. Smoke 2 before W5a
About 20 min of GPU time with the helper: token durations and overrun past the next frame arrival for aligned guard 0 / 0.5 / 1 / 2 ms at duty 1, guard 0 at duty 0.5, unaligned duty 1, and the background alone (does contention stretch tokens?). Diagnostic, not a result, no hypothesis tested; analysis/smoke_overrun.py (tested). Its outcome goes into a dated addendum before W5a.

## F4. reset_probe result (journal 0040)
12 of 12 resets succeeded (busy and idle GPU, lock held and not held, repeated resets): neither "reset of an unlocked clock errors" (H1) nor "reset on an idle GPU errors" (H2) reproduced. The two smoke-1 errors are unexplained; helper handling stays (reset-not-needed logging, governor-side `nvidia-smi -rgc` fallback).


---
# ADDENDUM G 2026-10-22 (after smoke 2; recorded BEFORE smoke 3, W5a and any W5b data)
- **Smoke-2 finding:** the guard-0 overrun was a driver bug, not a guard problem: a failed (mid-write) seqlock read of the pace block was treated as "fg idle", so tokens started at every fg publish whatever the guard. Fixed (workloads/background/pace_view.h; mechanism test with the real C++ reader); data/w45_smoke/smoke2_report.md; journal 0041. Everything measured with the old driver (smoke 1 token timing, smoke 2) describes a driver that ignored its own fit test.
- **Smoke 3** (docs/W45_SMOKE3_SETUP.md) before W5a: the fixed gate at constant frame costs 4 / 7 / 9 ms. Diagnostic, no hypothesis.
- **Learned guard:** design kept (journal 0041 recommendation 1-4); the possible "clean-token-only" token estimate in the driver is decided after smoke 3.
- **Hybrid d'B** implemented (controllers/hybrid.py, tests/test_hybrid.py); not simulated.
- **S2 non-inferiority** kept as a hand-over safety check (reviewer answer).
- **HW0 note:** at the nominal cost 7 ms arm a does not miss on hardware (fg p99 13.5 ms with a token running), so c0 will have to be raised on the tuning blocks for the registered feasibility gate to be satisfiable.
