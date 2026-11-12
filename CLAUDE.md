# CLAUDE.md - SLO-aware resource governor (governor/)

Owner: Arjun, final-year B.E. AI & ML student. Predecessor: `../variance_gpu_project`
(archived; see its ARCHIVE_NOTE.md).

## Working style
- Blunt and accurate. Depth over frameworks. One question at a time, only when blocked.
- Never fabricate or estimate metrics as if measured. Every number in docs/README traces to a logged file.
- Verify hardware capabilities by running commands. Verify a paper exists before citing it or claiming novelty.

## Hardware (verified Oct 2026 via nvidia-smi / wmic / nvcc)
- CPU: AMD Ryzen 9 7940HS w/ Radeon 780M.
- GPU: NVIDIA GeForce RTX 4070 **Laptop**, 8188 MiB, compute capability 8.9, driver 616.92.
  Max clocks: SM 3105 MHz, mem 8001 MHz. Power limit: 91.69 W current, 80 W default, 140 W max
  (`power.limit` query returns N/A; whether `-pl` works is a capability-audit item). SM count: see capability_audit.json.
- Windows 11 (WDDM): no MPS, no MIG. Linux dual-boot arm (MPS, RAPL, sched_ext) optional, later.
- Toolchain: nvcc 13.1; MSVC `cl` is NOT on PATH (load vcvars before nvcc). Python 3.12.4, torch 2.4.1+cu118.
- CUDA builds: always `nvcc -arch=sm_89 -O3 -lineinfo`. Never allow a silent CPU-simulation fallback:
  fail loudly and log the execution mode in every results file.

## Lessons from the old project (do not repeat)
- Chunk boundaries are barriers: T_total ~ W/S + sum_i L_i (L_i = slowest warp in chunk i), R^2 0.97-0.98 on v2 traces.
  The "launch overhead" explanation was wrong (host overhead 2-34 ms/run).
- DLS theory (Kruskal-Weiss, factoring) needs many independent workers and no global barrier.
- Keep the method: hypotheses fixed in advance, paired Wilcoxon, randomised arm order, warm-up, matched baselines,
  causal observer. Reuse CudaExecutor chunked launches as the background-slicing actuator.

## Problem
On a power/thermal-limited laptop with one consumer GPU, background local-AI work causes head-of-line blocking,
power theft and VRAM paging that wreck foreground p99. Goal: governor that sets background slice size, pacing,
CPU/GPU placement and GPU clocks to maximise bg throughput - lambda*energy s.t. fg p99 <= SLO and temp <= limit.

## Theory
1. Residual wait (non-preemptive): E[wait] ~ rho*E[S^2]/(2E[S]) = rho*(E[S]/2)(1+CV^2); slice size controls S.
2. Slice cost: launch overhead + barrier per slice. Best policy: largest slice that keeps fg within SLO.
3. Roofline/DVFS: decode is memory-bound (tok/s <~ BW / model bytes) so core downclock saves power cheaply; P ~ C*V^2*f.
4. Shared laptop budget (CPU+GPU watts and heat). 5. VRAM overflow -> WDDM paging; govern it as a resource.

## Sensors / actuators (each must be verified on this machine; see data/capability_audit.*)
Sensors: NVML, PresentMon, LibreHardwareMonitor/HWiNFO, PDH "GPU Engine", app TTFT/TPOT logs, Nsight Systems.
Actuators: slice size/pacing/batch, llama.cpp -ngl, nvidia-smi -lgc/-rgc/-lmc (admin), power limit, CPU priority/
affinity/EcoQoS/job-object caps, ryzenadj.

## Baselines and controllers
Greedy, static, PI on fg latency, best-static oracle; learned predictor (GBT then MLP) in constrained MPC or
contextual bandit with hard safety fallback. End-to-end RL = stretch.

## Prior art (UNVERIFIED until checked; verify before citing)
ConsumerBench arXiv 2506.17538; Tally arXiv 2410.07381; Orion (EuroSys 2024); REEF (OSDI 2022); zTT (MobiSys 2021);
GearDVFS (MobiCom 2023); G-Assist frame-rate drop (Windows Central).

## Plan (10 weeks)
W1 capability audit -> W2-3 characterisation (validate residual-wait model, decode downclock) -> W4-5 MVP
(telemetry daemon, controllable bg runtime, fg harness, greedy/static/PI) -> W6-8 learned controller ->
W9-10 real scenarios (game + LLM agent; captions/chatbot + image gen), ablations, dataset+harness release, report.
Foreground order: synthetic deadline frame loop -> AI foreground w/ SLO -> real game benchmark.
Experimental conditions: AC power, fixed fan mode, log ambient temp, warm-up. Run protocol: before every full run Arjun states the Armoury Crate mode (it can change the GPU memory clock: Turbo gave 8101 vs the locked 8001, journal 0021); it is passed as `--armoury-mode <mode>` and stored in meta.json. The mode must be the same across runs that are compared.
Run checklist (full runs; added 2026-10-22 after G, journal 0032): Administrator PowerShell; AC power; clean committed tree; Armoury Crate mode stated; Chrome closed; **quit background apps from the system tray (WhatsApp, Discord, any other tray app)**; no clicking in the console; **Armoury Crate mode and Chrome state are recorded in meta.json of every run (`armoury_mode`, `chrome_running`), and `run.py` refuses a full run without `--armoury-mode`** (added 2026-10-22, journal 0040). Run start logs every running process (name, instance count, CPU%) in meta.json `processes` (workloads/common/procsnap.py); experiments before 2026-10-22 have no such record and ran with WhatsApp and Discord idle in the background. From 2026-10-23: Armoury Crate Battery Health Charging is fixed at Balanced 80% for the rest of the study and recorded in meta.json (`battery_charge_mode`, with `boot_utc` and `uptime_s`); every W5b session starts from a FRESH RESTART (plan addendum M). W5a sessions 1-3 (2026-10-22) did not record the battery mode and had no restart procedure.

## Layout
telemetry/ actuators/ workloads/{background,foreground}/ controllers/ experiments/ analysis/ data/

## Decisions and verified findings (W1, Oct 2026)
- PresentMon is DEFERRED to the real-game phase (W9-10). The synthetic frame loop is our own code and logs its own
  frame timestamps (QueryPerformanceCounter / CUDA events). Do not install or depend on PresentMon before then.
- Toolchain: nvcc 13.1 does not officially support VS 18 (MSVC 14.50, the only VS installed). Build with
  workloads/background/build.bat (loads vcvars64, passes -arch=sm_89 -O3 -lineinfo -allow-unsupported-compiler).
  A trivial kernel built and ran; revisit if host-side STL code misbehaves.
- pip needs `--use-feature=truststore` on this machine (TLS interception breaks default cert verification).
- Capability audit (data/capability_audit.md, elevated run): NVML sensors work; clock lock -lgc/-rgc and -lmc work
  with admin (SM clock lockable 210-3105 MHz, step 15; memory clocks 405/810/6001/7001/8001); NVML power limit is NOT supported
  (no -pl knob); PDH GPU Engine does not attribute CUDA compute to the process; Energy Meter rapl_package0_pkg works
  (units unvalidated); LHM/HWiNFO/ryzenadj absent; EcoQoS, job-object CPU cap, priority, affinity work.
- Pre-registered experiment: experiments/w1_downclock.yaml (committed before any data).

## Review protocol (Claude Code <-> cloud reviewer)
- A separate Claude session reviews this repo read-only and leaves reviews in `reviews/YYYY-MM-DD_<topic>_review.md`.
- At the start of every session, check `reviews/` for review files that don't yet have a matching
  `*_response.md`. Address [BLOCKER] items before other work.
- Respond in `reviews/YYYY-MM-DD_<topic>_response.md`, one line per finding: fixed (commit hash) / disputed (why).
- Reviews are advice, not orders: Arjun decides on disagreements. Never edit a review file; write a response.

## Review follow-up findings (2026-10-20)
- Per-process GPU split cannot come from the OS: PDH "GPU Engine" does not attribute CUDA compute here. Use our own instrumentation
  (CUDA events in our background and foreground workloads) for any per-process GPU accounting.
- CPU Energy Meter (PDH `rapl_package0_pkg` Power) validated against HWiNFO CPU Package Power: load 56.8 W vs 59.7 W (ratio 0.95), idle 7.6 W vs 9.6 W (0.80),
  assuming mW. Good to roughly +-20%; fine for relative CPU-power comparisons, not for watt-accurate claims. Logs: data/energy_meter_validation_*.
  (Two collections exist: load 56.8/55.3 W, idle 7.6/9.9 W; HWiNFO values were a single spot reading.)
- NVML power signals (usage / average / instant) update every ~0.5 s and need ~1.5 s to follow a load step: use windows with >= 3 s of steady state.
- NVML total energy counter: reading it more often inflates it (~4.2 J per read on this machine) and it has a state-dependent offset vs sampled power.
  Read it exactly twice per measurement window; treat it as relative. See experiments/w1_downclock_addendum_2026-10-20.md.
- Throttle reasons: decode with telemetry/nvml_utils.py. `Reliability` (0x400) and `BoardLimit` (0x200) are real on this driver but absent from the CUDA 13.1 nvml.h;
  unlocked fma is Reliability-limited (~2475 MHz), not power-capped.
- Full experiment runs are refused on a dirty git tree (telemetry/provenance.py). Commit first. Tests: `python -m pytest tests -q`.

## Research record (mandatory)
The project must leave a complete, paper-ready trail of reasoning. See journal/README.md and decisions/README.md.
- After every working session that produces a result, a setback or a change of plan, add a journal entry
  (`journal/NNNN_YYYY-MM-DD_slug.md`) using the template. Include wrong beliefs and failures; cite commits/data paths.
- Every choice with real alternatives gets an ADR in `decisions/`. Supersede, never rewrite.
- Each experiment's trail: pre-registration (yaml) → addenda (if any, before data) → results file → journal entry
  with interpretation and implications.
- Journal and ADRs are append-only. Corrections are new entries that link back.

## Coordination and documentation rules (Arjun, 2026-10-21)
COORDINATION
- Every time I stop, overwrite `STATUS.md` with: phase; what I just did (commit hashes); what I am waiting for; decisions needed from Arjun
  (numbered, one line each, with my recommendation); whether a reviewer checkpoint is due (pre-registration before commit / results before
  interpretation / design change / surprise). Commit it so the tree stays clean.
- When Arjun says "check reviews", read `reviews/` for files without a matching `*_response.md` and respond.
- Keep chat replies short: point to STATUS.md and list only the decisions.
DOCUMENTATION
1. Every crash, failed build, aborted run or wrong turn gets a journal entry with its log path, however small.
2. Maintain `docs/TIMELINE.md`: one line per event (date · type [journal/ADR/review/prereg/result/incident] · summary · link). Backfilled from journal 0001.
3. Maintain `docs/CONCEPTS.md`: plain-language explanation of each concept when it first matters (residual wait, roofline, knee, slack reclamation,
   Holm, equivalence test, time-slicing, construct validity, ...), linked to the journal entry where it came up. Written for Arjun to study.
4. End of every session: `/export` to `docs/transcripts/YYYY-MM-DD_session-N.md` and commit.
5. At each phase end, add `docs/PAPER_MAP.md` entries: claim -> evidence (results file, journal, commit).
6. GitHub repo for governor; push after every session (Arjun sets up the remote; see STATUS.md).
