# 0004 — Re-evaluating the governor brief and pivoting
Date: 2026-10-19 · Phase: planning · Author: reviewer + Arjun
## Question
Is the original "personal device resource governor" novel, feasible and logically consistent?
## What we found
- "Almost untouched" was false: zTT (MobiSys'21, RL CPU+GPU DVFS), GearDVFS (MobiCom'23), Intel Thread Director,
  Windows EcoQoS, AMD SmartShift, NVIDIA Dynamic Boost, sched_ext/scx_lavd; datacenter GPU sharing: Orion, REEF, Tally.
- psutil-level knobs have little effect; the objective was undefined; "learned model" had no justification over a
  feedback controller.
- Real gap: ConsumerBench (arXiv 2506.17538) shows foreground GenAI starved on a shared GPU (decode ~30× slower)
  and lists SLO-aware scheduling as open; its testbed had no laptop power sharing and no game foreground. NVIDIA G-Assist
  reportedly dropped framerates sharply (Windows Central).
## Theory that ties the old work to the new problem
Foreground wait ≈ ρ·E[S²]/(2E[S]) for non-preemptive background kernels, so background slice size (the v2 executor)
controls foreground latency, and slice count controls barrier cost (0003). Decode is memory-bound, so a lower core clock
should save power cheaply.
## Decisions
ADR-0001, ADR-0002, ADR-0003.
