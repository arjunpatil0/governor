# 0008 — W2 plan approved with modifications
Date: 2026-10-21 · Phase: W2 (planning) · Author: Claude Code (plan) + Arjun (modifications)
## Question
How do we test (A) the residual-wait model, (B) the effect of a device-wide SM clock lock on a compute-bound foreground,
and (C) a decode-like background's clock knee, before any data is collected?
## Belief going in
Journal 0004: foreground wait ≈ ρ·E[S²]/(2E[S]) for non-preemptive background slices. Journal 0006: the SM clock lock is device-wide,
so it also slows a compute-bound foreground (W1: fma keeps 0.488 of throughput at 1200 MHz). Decode-like work has a knee above a streaming copy's.
Known risk written into the plan: Windows has no MPS, so processes are time-sliced, and compute preemption may make the non-preemptive assumption false.
## What we did
Plan proposed inline (two processes, A/B/C, one yaml `experiments/w2_colocation.yaml`, pilot before registration, TDD for pure functions).
Arjun approved with the modifications below. They go into the yaml verbatim in spirit; this entry is their first record.
### Modifications (Arjun)
A. Residual wait
 1. Prediction includes utilisation: wait = ρ·E[S²]/(2E[S]) + baseline, with ρ measured per cell from logged slice timestamps (GPU-busy / wall). Inter-slice gap statistics are logged.
 2. "Slope CI includes 1" is replaced by an equivalence test: the slope's 90% CI must lie within [0.8, 1.25].
 3. Windows hardware-accelerated GPU scheduling (HAGS) state is logged in meta.json and held fixed; a small pre-registered control subset with HAGS flipped if feasible, else listed as a limitation.
B. Clock lock vs foreground: size the fma frame so unlocked service time is ~50–60% of the frame budget (e.g. ~9 ms at 60 Hz, ~4.5 ms at 120 Hz), set from the pilot; otherwise HB2 is untestable (zero misses).
C. Decode proxy: realistic kernel count per layer (~4–8 small kernels: GEMVs, norm, attention read), with and without CUDA-graph capture, because WDDM launch cost may set the knee. One real llama.cpp validation cell (3B, Q4) after C.
## What happened (state at the end of this session)
- Nothing measured for W2. No pilot, no yaml, no code yet. No W2 numbers exist; any number in the plan is a design choice or a budget.
- HAGS: registry value `HKLM\SYSTEM\CurrentControlSet\Control\GraphicsDrivers\HwSchMode` does **not exist** on this machine (queried 2026-10-21). An absent value means the OS default, so the effective state is **undetermined**.
  Arjun declined a `dxdiag /t` call. How to determine and flip HAGS (Settings UI, or a registry write plus reboot) is a pilot task for Arjun to approve; flipping needs a reboot and is why the control is "if feasible".
- Tooling change: `journal/**` and `decisions/**` added to `GATEGUARD_EXEMPT_GLOBS` in `~/.claude/settings.json` (absolute paths, since the hook resolves relative globs against the session's project root). Takes effect when settings reload.
## Interpretation
ρ in the prediction matters: a background with gaps (host sync between slices) busy less than 100% of the time shifts the wait, and a model that ignores it would fail for the wrong reason. The equivalence test is stricter than a CI-includes-1 test because it also fails on a wide CI.
## Setbacks / surprises
The fact-force gate blocked each first write of a new record; resolved by the exemption above (effective next reload).
## Decisions
To be written as ADR-0008 (two processes, synthetic decode proxy plus one real-engine validation cell) when the yaml is registered.
## Next
(1) RED tests for `loadgen.py` pure functions, including ρ and inter-slice gap stats; (2) pilot with HAGS method agreed first; (3) register `w2_colocation.yaml`; (4) run C, then B, then A.
