# R1: does a local LLM hurt a real game's frames, and does a cheap fix already work? Forecast and decision rule

Branch `real-game`, written 2026-11-10, revised 2026-11-11 after the reviews recorded at the end, committed and pushed before any measurement. The rule may be amended by a separate commit until the first cell is run; no amendment after that. Smoke cells and the sweep are data.

## Terms

SOLO is the game alone. UNGATED is the game plus the LLM decoding flat out, with nothing limiting it. A hitch is a frame whose frame time is above 25.0 ms (1.5 times the 16.67 ms period). GPU busy is PresentMon's time per frame during which the GPU worked on that frame. "Build the gate" would mean building a mechanism that starts LLM work only in the GPU idle time that the game's frame cadence predicts, which is what v2 did with a hint from the app; it costs weeks of engineering and is what this sprint decides for or against.

## Question

On this laptop, under normal-user conditions, (1) does a local LLM decoding next to a real game worsen the game's frame times, (2) does a one-line fix (a lower GPU scheduling priority for the LLM process, or running the LLM on the integrated GPU) already solve it, and (3) is the game's frame timing predictable enough from outside to drive a gate with no help from the game. This sprint builds no mechanism: no pause patch, no predictor-driven gate, no clock lock, no helper.

## Conditions

The GPU runs unlocked, as for a normal user: no clock lock, no clock helper, no power-limit change. The foreground is a real Direct3D or Vulkan program capped at 60 fps, not the synthetic kernel loop. The game is the Unigine Superposition benchmark (free Basic edition), the fallback named in the brief, because no installed game has a repeatable benchmark without kernel anti-cheat (GTA V ships BattlEye; Fortnite ships Easy Anti-Cheat). Stock llama.cpp at commit 620d2225c without the pause patch in every arm, model Llama-3.2-3B Q4_K_M. PresentMon 2.6.0 console build (sha256 b2a706bc6ad475749e3b7e3409263aa1e6906d45bdcf993f6dbc0f660188f1af, signed by Intel Corporation) captures every cell, SOLO included, so its overhead is common to all arms, and the window is cut on QPC time (`--qpc_time`).

Settings that change the result are fixed, not merely recorded: AC power, the Armoury Crate mode, HAGS on or off, the display and GPU mode (dGPU-direct or hybrid), the cap method with vsync state and panel refresh rate, the Superposition preset, how the scene is started (benchmark sequence or static camera, restarted every cell) and which executable PresentMon targets. Their values are written to `docs/R1_SETUP.md` and committed before the first cell. A change to any of them voids the sweep. Chrome and tray apps are closed. In SOLO the LLM process is absent. The LLM process is started and the model loaded before the warm-up of its cell, with the game already running, and sits idle until the window opens.

Preset acceptance, applied to SOLO data only: SOLO holds the 60 fps cap with GPU busy time per frame between 6 and 10 ms (median over a 20 s SOLO capture) and a hitch share below 1%. No loaded-arm result is looked at before the preset is frozen and committed in `docs/R1_SETUP.md`, together with the number of smoke runs. If the accepted preset cannot be found, the sprint stops and reports; it does not reinterpret.

## Arms and design

Each cell is 60 s measured after a 20 s warm-up. Arms: SOLO; UNGATED; PRIO_IDLE (the LLM process set to the lowest GPU scheduling class with `D3DKMTSetProcessSchedulingPriorityClass`, the status checked and the class read back at the start and end of the cell); DUTY50 (the LLM sleeps for its own measured token time after each token, no hint; reference only, see the rule); IGPU (the LLM on the Radeon 780M through the Vulkan backend; the build is timeboxed to one hour and the arm is dropped, with the reason recorded, if it fails). A separate LLM-alone cell gives the reference tok/s.

Five reps. In each rep the order is SOLO, then the four arms in an order shuffled from the seed 89770043, then SOLO again. Between cells the rig rests until the GPU temperature is within 3 C of the temperature at the start of the rep, for at least 30 s and at most 180 s, and logs the rest time. The reference for an arm in a rep is the mean of that rep's two SOLO cells, and comparisons are paired by rep. The signed difference between the closing and the opening SOLO of each rep is reported as drift, separately from the absolute difference, which is the noise.

Primary metrics, from PresentMon: the p99 of frame time and the hitch share. Secondary: p50, 1% low fps (1000 divided by the mean of the slowest 1% of frame times), GPU busy per frame, tok/s from the driver's per-token log inside the measured window only, GPU power from two reads of the NVML energy counter, VRAM used and temperature at the start and end, median SM clock and throttle-reason bitmask from a 50 ms NVML sampler that runs in every cell. "Frame time" is the PresentMon column named in the schema committed in `tools/realgame/presentmon.py`, taken from a real header captured in the smoke cell and committed before the sweep; frames PresentMon marks as dropped stay in the data. A cell is flagged as paging if the game's shared GPU memory (the PDH "GPU Process Memory" Shared Usage counter) exceeds its SOLO level by more than 64 MB.

No cell is excluded. A cell that fails (a crash, a PresentMon gap, a failed priority call) causes its whole rep to be rerun with the same seed, and every attempt is reported. Flagged cells (paging, throttling) stay in the rule and are listed. A PRIO_IDLE cell whose read-back is not the idle class makes PRIO_IDLE void for the sweep: it counts as not within limits and cannot support BUILD THE GATE. UNGATED is valid only if the LLM produced tokens throughout the window (tok/s above 25% of the LLM-alone reference); otherwise the sweep is voided.

## What the rule can resolve

A cell has about 3,600 frames, so its p99 rests on about 36 frames, which come in clusters. Under a hard cap the SOLO p99 sits near 17 ms, so the 5% limit is about 0.85 ms, close to the limiter's own jitter, and 0.5 pp of hitch share is about 18 frames. With five reps no significance is claimed (a Wilcoxon test cannot go below p = 0.0625); the decision uses the mean of the five paired values, the median and the worst rep are reported beside it, and a percentile bootstrap over the five values is reported for information only (it has 126 distinct resamples and undercovers, so it gates nothing).

## Decision rule (thresholds fixed now)

Per rep, the p99 worsening of an arm is its p99 minus the mean p99 of that rep's two SOLO cells, divided by that mean; the hitch increase is its hitch share minus the mean hitch share of the two SOLO cells, in percentage points. An arm is within limits if (a) the mean paired p99 worsening is below 5%, (b) the mean paired hitch increase is below 0.5 pp, and (c) no single rep has a worsening of 10% or more or an increase of 1 pp or more. An arm is harmful if the mean paired p99 worsening is at least 15% and the mean hitch increase is at least 2 pp.

Noise precondition (added in review, for the owner to confirm): a claim that an arm is within limits is allowed only if the mean over reps of the absolute difference between the two SOLO cells is below 2.5% in p99 and below 0.25 pp in hitch share, and the SOLO hitch share is below 1% in every rep. A harmful finding does not need the precondition.

Branches are evaluated in this order and the first that holds is declared.

1. NO PROBLEM: UNGATED is within limits (and the precondition holds). It is reported as holding for this preset and this game only; no heavier-preset rerun follows.
2. SIMPLE FIX: PRIO_IDLE or IGPU is within limits and keeps a mean paired tok/s ratio to UNGATED of at least 0.70 (IGPU: a mean tok/s of at least 15.0 inside the window with the game running, instead of the ratio). If both qualify, both are reported and the one with the higher tok/s is named the fix.
3. FIX TOO SLOW: UNGATED is harmful, PRIO_IDLE or IGPU is within limits, and neither meets its throughput condition. This is a result in itself: a fix protects the game at a cost in throughput that the rule judged too high, and the numbers are reported without a next step beyond that.
4. BUILD THE GATE: UNGATED is harmful, the IGPU arm was measured (not dropped), PRIO_IDLE is valid, neither PRIO_IDLE nor IGPU is within limits, and the predictability test passes. A dropped IGPU arm sends the result to OPEN unless PRIO_IDLE decides it.
5. OPEN: anything else, including UNGATED neither within limits nor harmful. The follow-up for OPEN is declared now: one repeat of SOLO, UNGATED and the arm in question with 10 reps, under this same rule, and nothing else.

DUTY50 is reference only: it shows what a naive throttle does and cannot be the fix of branch 2 (the brief names PRIO_IDLE and IGPU; this is for the owner to confirm). Whether WDDM applies the priority class to compute queues submitted through CUDA is the experiment itself; there is no positive control, and a null result means "no effect observed with a verified read-back", not that the mechanism cannot work.

## Predictability test (offline, from the captures)

For each SOLO frame, predict its GPU start time from the cadence of the previous N frames: the previous start plus the mean interval over the window. N = 8 is the test; N = 4 and N = 16 are sensitivity checks and do not decide. The GPU start time is not a PresentMon column; I derive it as the CPU start time plus the GPU latency of the version-2 metrics, so the error is partly the error of that proxy, and the result says so. Report the p50, p95 and p99 absolute error in ms, the same error for the baseline that predicts "previous start plus 16.67 ms", and the distribution of GPU idle time per frame (frame time minus GPU busy). Because a gate needs the end of the game's GPU work and not only its start, the same prediction is made for the end of work (start plus GPU busy). PASS if, for N = 8 on SOLO, the p95 error of both the start and the end is at most 1.5 ms and the median idle time per frame is at least 3 ms. The idle condition follows from the preset acceptance (6 to 10 ms busy in a 16.67 ms frame) and cannot fail; the cadence conditions mostly measure the limiter. A pass is therefore necessary and not sufficient evidence for a gate, which is why branch 4 also requires UNGATED to be harmful. The same prediction is run on the UNGATED captures and reported as supplementary (the cadence under LLM overlap), without deciding anything. Not tested: live access to the capture with low latency.

## Forecast

Reference numbers, from the v1 characterisation and not from this machine in this configuration: the LLM alone unlocked gave 101.1 tok/s at 92 W; in the v1 smoke test an overlapped token took 2.05 times as long and an overlapped frame 1.95 times as long; the v1 time-slice fit implies each process runs at about 1/2.5 to 1/2.8 of its solo speed when both have work (assumed to carry over to a game). The forecasts are conditional on the preset satisfying the acceptance rule (SOLO GPU busy per frame 6 to 10 ms, central estimate 8 ms). They are guesses with ranges; I have not measured this game.

| Quantity | Forecast (range) |
|---|---|
| LLM alone, tok/s | 100 (85 to 115) |
| SOLO bracket: mean absolute p99 difference between a rep's two SOLO cells | 2% (0.5 to 6%); hitch share difference 0.1 pp (0 to 0.5) |
| UNGATED: p99 worsening | +35% (+8 to +120%); at 8 ms busy, 1.95 times gives 15.6 ms, just inside the deadline, so only the tail crosses it |
| UNGATED: hitch increase | +4 pp (0.5 to 30) |
| UNGATED: tok/s | 45 (30 to 65) |
| UNGATED: GPU power | 95 W (75 to 115) |
| PRIO_IDLE: p99 worsening | +20% (+3 to +80%) |
| PRIO_IDLE: hitch increase | +2 pp (0.2 to 20) |
| PRIO_IDLE: tok/s as a share of UNGATED | 75% (40 to 100%) |
| DUTY50: p99 worsening | +20% (+5 to +90%) |
| DUTY50: hitch increase | +2 pp (0.3 to 25) |
| DUTY50: tok/s | 26 (16 to 38) |
| IGPU: tok/s | 14 (8 to 22); probability of at least 15: 40% |
| IGPU: p99 worsening | +3% (0 to +15%) |
| IGPU: hitch increase | +0.2 pp (0 to 2) |
| Predictability: p95 error at N = 8, start | 0.6 ms (0.2 to 2.5) |
| Predictability: median GPU idle per frame | 7 ms (6.7 to 10.7, by the preset acceptance) |

Probabilities of the branch: NO PROBLEM 10%, SIMPLE FIX 25%, FIX TOO SLOW 10%, BUILD THE GATE 25%, OPEN 30%, with a 15% chance that the IGPU build fails and the arm is dropped (which moves mass from branches 2 and 4 into OPEN). The first forecast I wrote put the UNGATED effect at +70% and NO PROBLEM at 3%; a reviewer pointed out that the 1.95 times figure I cited puts an 8 ms frame at 15.6 ms, and I revised the forecast down to what that number implies. Reasoning in one place. WDDM time-slices the GPU between processes, so a token that overlaps a frame stretches it; a flat-out decode overlaps most frames, but with 8 ms of busy time in a 16.67 ms frame only the frames that meet the longer slices or a stall cross the deadline. I expect the scheduling priority class to help only partly, because I do not know that WDDM applies it to CUDA compute queues. DUTY50 halves the duty but is not aligned to the frames. The iGPU leaves the game's GPU alone, so its cost is shared memory bandwidth and CPU; its tok/s is bounded by the system memory bandwidth over the 2 GB of weights read per token (the memory type and speed are read from the machine before the sweep; at a peak near 90 GB/s and 35 to 50% efficiency the estimate is 12 to 18 tok/s, so 14 is a guess near the 15 tok/s line).

## What the rule licenses

One benchmark, one preset, one scene, one cap method, one laptop, one model. A result is a statement about that configuration. It decides whether to spend the next engineering effort, and it does not show that a real game with variable load and CPU contention behaves the same, or that a 5% worsening of p99 is visible to a player; those limits go into the results document.

## Out of scope

No predictor-driven gate, no cb_eval port, no clock lock, no edits to any v1 or v2 registered file, no threshold tuning after data.

## Review before push

Sprint brief steps 2 and 4. Subagents (model, purpose, outcome):

| Subagent | Model | Purpose | Outcome |
|---|---|---|---|
| inventory | Haiku | list installed skills, plugins, agents; find PresentMon; GPU state | confirmed ECC 2.2.3 agents and llm-council; PresentMon absent |
| ecc:planner | Sonnet | implementation and measurement plan | 37-test plan; found that the stock decode driver stops at n_ctx 2048 so a new driver is needed, that PresentMon 1.x has no GPU-busy column, and that GPU start is not a column |
| design review | Opus | confounds, decision rule, forecast consistency | 16 defects; all applied below except where noted |
| llm-council advisors (5) | Sonnet | Contrarian, First Principles, Expansionist, Outsider, Executor on the rule | converged on the same holes |
| council peer reviews (5) | Sonnet | anonymised review of the five responses | unanimous that the strongest point was "BUILD THE GATE is a residual, not a finding"; listed what all five missed |
| chairman | the main session, not a subagent | synthesis | deviation from the skill, which spawns a separate chairman; the five peer reviews were short and agreed, so I synthesised them directly |

What changed from the first draft: the settings are fixed in a committed setup file and a change voids the sweep; a rest rule replaces the fixed 30 s; the preset acceptance, the paging definition, the no-exclusion and rerun rule and the PRIO_IDLE validity rule are stated; "within limits" gained a worst-rep clause and "harmful" was defined; BUILD THE GATE now requires UNGATED to be harmful, the IGPU arm to be measured and PRIO_IDLE to be valid, and a branch FIX TOO SLOW was added; branch order and the DUTY50 and IGPU-dropped handling were made explicit; the noise precondition was tightened from the limit to half the limit and no longer blocks a harmful finding; N is fixed at 8 and the end of work is predicted as well as the start; the OPEN follow-up is declared; the forecast was corrected where it contradicted its own sources (UNGATED effect, DUTY50 tok/s, power, idle range, IGPU bandwidth), labelled where it uses v1 numbers, and given an IGPU-drop probability; the sweep seed is written down. Not applied: the council's "partial" branch (it adds a judgment zone after the data), a power analysis (a stated resolution paragraph replaces it), and a separate positive control for the priority class (not available; stated). Points for the owner to confirm before the first cell: the noise precondition, DUTY50 as reference only, the added end-of-work prediction, and the setup file.
