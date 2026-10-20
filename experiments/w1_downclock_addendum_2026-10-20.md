# Addendum to w1_downclock.yaml (written 2026-10-20, BEFORE any w1_downclock data exists)

The registered file `experiments/w1_downclock.yaml` is unchanged. This addendum records measurement-validity
findings from review finding 1 and one pre-specified sensitivity analysis. Evidence: `data/diagnostics/power_energy_20261020T191306Z.{csv,json,png}`
(produced by `telemetry/power_energy_diagnostic.py`).

## Findings
1. **NVML power signals lag.** `nvmlDeviceGetPowerUsage`, `POWER_AVERAGE` and `POWER_INSTANT` update every ~499 ms (p90 ~998 ms)
   and take 1.56 s (instant: 1.06 s) to reach 90% of a load step. Instant vs average field made no difference (ruled out as a cause).
   The smoke-run mismatch (e.g. 89.1 W vs 59.2 W) came from 0.5 s pre-roll + 1.0 s windows, in which the samples never reach steady state.
2. **At the registered pre-roll (1.5 s) and window (4.0 s)**, the sample mean is expected to read about 11% below the steady-state
   counter rate for a ~80 W fma load (diagnostic: -11.0%; -9.6% with a 3 s pre-roll). That sits just inside the registered 15% check.
   The check is therefore informative only for steady, long windows. It is NOT a reliable validity check for short windows, and may flag low-power cells.
3. **The energy counter is biased, in two ways** (`power_energy_*.json`):
   - every extra counter read adds phantom energy, ~4.2 J per read (fit over 1-81 reads/s). The harness reads it exactly twice per window; never add reads.
   - at two reads per window it sits above the sampled power by a state-dependent offset: idle without CUDA context 22-28 W vs 2.4 W; CUDA context idle 30-39 W vs 12.5-14 W;
     fma steady 82-86 W vs 77-80 W. The offset is not constant, so energy-per-work ratios across clock levels may be biased. Absolute joules are not physical.
4. **Unlocked clock limit.** Under fma load the throttle reason is `Reliability` (raw 0x400; confirmed with `nvidia-smi -q -d PERFORMANCE`), not the power cap, and the
   unlocked fma clock is ~2460-2475 MHz at ~78 W. The yaml's limitation "unlocked cell runs under a ~92 W power cap" is wrong for these kernels.
   The harness now logs the raw mask (`event_mask`) and decoded reasons per measurement.

## Pre-specified sensitivity analysis (implemented in analysis/w1_downclock_analysis.py)
H2 is re-tested with sample-based energy: `epw_s = mean(20 Hz power samples) * wall_s / work`, relative to the same block's unlocked cell, with the same Holm procedure.
- The registered decision rule still uses the energy counter.
- If counter-based and sample-based H2 disagree on "supported / not supported", H2 is reported as **inconclusive** (energy measurement not trustworthy to the needed accuracy).
- If they agree, report both.

## Harness changes made since the registration commit (none alter the design)
- `temp_start_c` is now the first sample inside the measured window (so `temp_max_c >= temp_start_c`); the pre-gate reading is `temp_pre_c`. (review finding 2)
- Throttle decoding moved to a tested module that never drops unknown bits; raw `event_mask` logged. (finding 3)
- `run.py` refuses a non-smoke run on a dirty git tree. (finding 4)

## Open decision for Arjun
A longer pre-roll (3 s) would make the sample check informative, but it changes the registered design (1.5 s). Not done; if wanted, register `w1_downclock_v2.yaml` before running.
