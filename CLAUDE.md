# CLAUDE.md - SLO-aware resource governor (governor/)

Owner: Arjun, final-year B.Tech AI/ML, targeting NVIDIA graduate roles. Predecessor: `../variance_gpu_project`
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
Experimental conditions: AC power, fixed fan mode, log ambient temp, warm-up.

## Layout
telemetry/ actuators/ workloads/{background,foreground}/ controllers/ experiments/ analysis/ data/
