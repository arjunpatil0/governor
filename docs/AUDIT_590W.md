# Audit: the 590 W NVML power glitch (read-only, 2026-11-07)

## Summary

1. Verdict: no reading above 150 W exists in any stored record, and no headline number moves. The registered power figures (`power_w`, the feasibility check, `eval_descriptive.md`) come from the energy counter, not from the glitching call. Nothing was changed.
2. The glitch is real and is not ours: today `nvidia-smi` itself printed 588 to 590 W on an idle GPU, and 133 of 200 direct NVML reads did the same. Each glitch lasts about one NVML update (0.5 s). A glitch of that length would have left a bin above 300 W in the W5b traces; the largest stored bin is 103.9 W.
3. What cannot be excluded: a glitch shorter than one update inside the W5b cells (raw samples were never stored there). Its effect would be about 0.03 W on a 60 s cell mean per sample.

## Method

All of `data/` was scanned for NVML power records, read-only. Nothing was edited and no experiment was run. The only live queries were a few `nvidia-smi` calls and about 500 direct `nvmlDeviceGetPowerUsage` reads, to characterise the glitch as it is today.

Stored power records, by what they contain:

| Source | Records | Granularity | Collected with |
|---|---|---|---|
| W2 `samples.csv` (1501 files) | 240,133 readings | raw samples | `nvmlDeviceGetPowerUsage`, sampler in `experiments/w2_colocation/run.py` |
| W5b trace bins (463 cells) | 60,190 bins | mean of 0.5 s (about 125 samples at 250 Hz, the rate the report uses) | `trace_bins` in `experiments/w5b/executors.py` |
| W5b Governor log, power column (327 cells) | 212,877 ticks | mean of 0.1 s (about 25 samples) | `recent_mean`, the Governor's input in sampled-source cells |
| W5b cell records, `power_sampled_w` (425 evaluation cells) | 425 | 60 s window mean | raw sampler mean |
| Diagnostic `power_energy_*.csv` | 1,825 rows, three NVML fields | raw | direct NVML reads |
| W1 `results.csv` | 132 cells | window means | sampled mean |
| W4/5 smoke `daemon.csv` | 201 readings | raw | `nvmlDeviceGetPowerUsage` |

Excluded: `energy_meter_validation_*.csv` (CPU energy meter, not NVML). The older W5b cells (142) have a 5-column Governor log without power; 242 cells (static, arm a) have no Governor log. Raw per-sample data exists only for W2 and the small diagnostics; W5b kept only binned means.

Steps: (1) every record above 150 W; (2) a spike detector on the W5b records (a bin or tick more than 3 W above both neighbours, 3 W being roughly one 590 W sample in a 125-sample bin at about 90 W); (3) a deliberately aggressive stress test: replace each such bin in the 60 s window with the mean of its neighbours and recompute `power_sampled_w`, J/token (sampled mean power divided by tok/s) and the arm medians; (4) comparison with the registered figures; (5) a live characterisation of the glitch. The scan scripts were scratch files and are not committed.

## Findings table

| Check | Result |
|---|---|
| Readings above 150 W, all sources | 0 (W2 raw max 100.24 W; smoke daemon max 96.2 W; diagnostics max 78.4 W; W1 window max 78.5 W; cell `power_sampled_w` max 91.67 W) |
| W5b bins above 110 W | 0; maximum 103.9 W |
| W5b Governor ticks above 150 W | 0; highest 128.0 W (see below) |
| Single-tick spikes more than 8 W above both neighbours (212,223 ticks tested) | 0 |
| Cells with at least one reading above 150 W | 0 of 711 W5b cells with frame files, and 0 of the 1501 W2 sample files |
| Bins more than 3 W above both neighbours | 525 of 59,264 (0.9%); by arm: c'B-T3b 181, d'B 117, c'B-T3c 91, eB 65, g'B 56, a 15 |

The two highest ticks are below the 150 W line but worth recording. ev15_S5_cBc_35 reads 128.0, 128.0, 128.0, 93.1, 42.9 W over its first five ticks (t = 0.1 to 0.5 s of the 5 s warm-up, clock 2460 MHz), and ev13_S5_cBb_60 reads 112.5 W for four ticks, then 55.8, 50.2 W. Both are before the measured window. The 0.5 s bin of the same moment reads 95.3 and 94.7 W, so the 128 and 112.5 W ticks are a start-of-cell transient, not a 590 W value. The card's maximum power limit is 140 W (`nvidia-smi`), above those values.

Of the 525 candidate bins, 454 are in governed cells. In 124 of those a clock change falls within one bin, and at tick level the excess over the neighbouring bins has a median of 1.7 W, so most look like real, sustained governor-driven power changes. In arm a (steady load) there are 15 candidates of 6,912 bins, the largest 10.2 W. None can be told apart from a short glitch without raw samples.

## Impact on results

Registered numbers: unchanged. Feasibility is defined on the energy counter (`docs/W5B_RESULTS.md`, line 50; `analysis/w5_analysis.py`), and `eval_descriptive.md` reports `med_power_w` from `power_w`, which is the counter delta. I recomputed the medians from `data/w5b/eval/results.csv` and 12 spot-checked rows match the table (S0 and S1, 60 W: 90.5, 58.4, 23.8, 58.8, 30.5, 30.2 and 89.9, 38.9, 25.2, 55.8, 40.8, 40.9). No number in either file moves, and the power-cap compliance check cannot change, because no reading was replaced and the counter is not the glitching call.

Where the glitching call does matter: the sampled-source Governor loop (c'B and d'B cells) steers on the 0.1 s sampled mean. Its logged ticks show no value above 128 W and no single-tick spike, so no decision in the stored cells was driven by a glitch.

Stress test (not a finding of glitches: no reading above 150 W exists, so this replaces real transients as well and overstates any effect), applied to `power_sampled_w` only:

| Quantity | Change |
|---|---|
| Cells with at least one candidate bin in the window | 187 of 425 (366 bins) |
| Per-cell sampled mean power | largest change -0.79 W (ev12_S5_dB_60, 57.80 to 57.01 W); 6 cells move more than 0.5 W, 13 more than 1% |
| J/token (365 cells with tok/s above 0) | largest change 0.76 J (2.1%) |
| Arm medians, 55 arm x scene x budget groups | largest change 0.55 W (2.1%, 35 W, S5, c'B-T3b); 1 group above 0.5 W, 2 above 1% |
| Cap compliance judged on sampled power | 2 cells would flip. For comparison, 10 cells already differ between the counter and the sampled mean (largest single-cell gap 2.67 W) |

These figures are not used by any registered test, table or conclusion, so they exceed the 0.5 W / 1% limit only in a diagnostic column that nothing reads. No headline number moves.

## Hypothesis

Observed today, with the same driver as in October (616.92): at idle (0% utilisation, P3 or P4, average power field 1.00 W), `nvidia-smi` printed an instantaneous draw of 588.21 W in 7 of 10 reads. Direct NVML reads at 20 Hz gave 133 of 200 values above 150 W (588.2 to 590.0 W), and 171 of 300 in a second run. The glitches come in runs of 23 to 25 consecutive reads, about one 0.5 s NVML update, plus isolated single reads. They occurred in all three performance states seen (P0, P3, P4). Neither `nvidia-smi` nor the poller reads the energy counter, calls the clock helper or starts a cell, so energy-counter reads, helper calls and cell boundaries are not needed to produce the glitch. That is what the data show.

Hypotheses, not shown by the data:
1. The instantaneous-power field returns a bad value while the GPU is idle or lightly loaded (the average field was 1.00 W at the same moment), and under sustained load the field is valid. This would explain why the loaded W2 and W5b records contain none. Its weak point: the W2 files contain readings down to 15.5 W (the minimum over the first 300 files) and still no glitch.
2. The glitch frequency depends on the machine state of the day (Chrome, power mode, current limit 55 W today against 91.69 W in the October notes), not on the driver.

Not tested: whether the glitch appears under load today (no hardware run was allowed), and any dependence on the sampling interval (50 ms live against 4 ms in the experiments).

## Recommended guard

1. Reject at collection time any reading above 1.5 times the device's maximum power limit, read once from NVML at start (140 W gives a 210 W cut-off; a fixed 250 W, as the dashboard and bench use, also catches 590 W). Count rejected readings and store the count in the cell record.
2. Store a per-bin maximum next to the 0.5 s bin mean, so a single bad sample is visible in later audits. The raw sample series (about 15,000 samples per 60 s cell) is the better fix if storage allows.
3. Do not replace rejected samples silently. Carry the previous good value, as the Governor loop already does for an empty span, and log it.
4. In the sampled-source Governor loop, apply the guard before `recent_mean`, so one glitch cannot steer a decision. Any such change is a code change to be made deliberately and recorded; this audit changed none.
