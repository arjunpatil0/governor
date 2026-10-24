# 0005 — W1 capability audit and measurement validity
Date: 2026-10-20 · Phase: W1 · Author: Claude Code (summarised by reviewer)
## Question
Which sensors and actuators actually work on this machine (RTX 4070 Laptop, 36 SMs, 8 GB; Ryzen 9 7940HS; Windows 11)?
## What happened (data/capability_audit.md, commits 875c9bb..20ae44a)
- Works: NVML sensors; SM clock lock (-lgc, 210–3105 MHz) and memory clock lock (-lmc) with admin; CPU priority,
  affinity, EcoQoS, job-object caps; Windows Energy Meter (CPU, validated vs HWiNFO to ~±20%).
- Does not work: NVML power limit (no -pl); PDH does not attribute CUDA compute to the process.
- Measurement surprises: NVML power updates every ~0.5 s and lags a load step by ~1.5 s; the NVML energy counter
  adds ~4.2 J per extra read and has a state-dependent offset; unlocked fma is limited by "Reliability" (0x400), not the power cap.
## Setbacks / surprises
- Smoke runs showed 20–50% disagreement between energy sources (lag + short windows). Diagnosed, not hidden;
  addendum experiments/w1_downclock_addendum_2026-10-20.md written before data.
- A placeholder in a command (`<room temp>`) broke PowerShell: trivial but recorded.
## Decisions
ADR-0004, ADR-0005, ADR-0006, ADR-0007.

**NOTE appended 2026-10-24 (journal 0056; the text above is unchanged):** the "about 4.2 J per extra read" of the measurement-surprises line is the figure of THAT GPU state. The W5b diagnostic of 2026-10-24 (10.02 energy reads/s from the Governor loop) implies 7.5 J per read in the g'B static state and 2.7 J per read in the c'B state: the phantom energy per read is STATE-DEPENDENT, not a constant (addendum O-5, data/w5b/diag).
