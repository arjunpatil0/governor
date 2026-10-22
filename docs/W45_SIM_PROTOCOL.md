# W4-5 simulator study protocol (written 2026-10-22, BEFORE any controller was run against the plant)
Simulation only. Nothing here is a hardware result. Plant: sim/plant.py with parameters from committed results (sim/params.py), share divisor fitted to the A2 SA4 anchors (data/sim_calibration.json: S = 2.5, RMSE of log mean latency 0.030; the G-derived 2.79 is the sensitivity setting). The anchor tests are CALIBRATION checks (the same data fitted), not validation; validation is the hardware smoke and W5.

## Foreground (synthetic, frame-paced, per approved change 3)
60 Hz periodic, deadline = period = 16.667 ms, base cost c0 = 7.0 ms (alone at 1800 MHz), lognormal frame jitter sigma 0.03 (ASSUMPTION, not measured).
Reason for 7.0: in the plant, an always-on bg at unlocked clock makes the fg miss when the fg cost exceeds about 9 ms at 1800 MHz (exploration on 20 s runs, c = 4..11); with the +/-30% variability the heavy phase (9.1 ms) is infeasible for no-governor while the light phase is easy, so adaptation matters.
Feasibility gate (checked on TUNING seeds before the study; if it fails the fg cost is changed once, in a dated addendum, and the study is rerun): scenario S1 under (a) misses > 5%; best static (b, either pacing) misses <= 1%.

## Background
llama.cpp Q4_K_M decode token: time 1/tok_s(clock) (L, bg alone), power from L. Pacing modes: unaligned duty (gap = measured token time x (1/d - 1)); aligned (slack-filling, guard in ms).

## Scenarios (60 s each, 5 s warm-up excluded)
- S0 steady: cost factor 1.0.
- S1 variability (approved change 2): cost factor steps 1.0 / 0.7 / 1.3 / 0.7 / 1.0 / 1.3, 10 s each (+/-30%).
- S1d drift: cost factor ramps linearly 0.7 -> 1.3 over the 60 s.
- S2 fg idle/active: fg active 0-20 s, idle 20-30 s, active 30-50 s, idle 50-60 s (cost factor 1.0).
- S3 thermal cap: effective clock capped at 1500 MHz from 30 s (cost factor 1.0).
- S4 interaction mismatch: S1 with the co-run share divisor multiplied by (1 + 0.5 x (1800/f - 1)), i.e. lower clocks hurt more under contention. The controllers do not know it.
Not simulated in this round (stated, not hidden): bg model swap (needs a second token-rate curve; only a proxy exists), CPU-side EcoQoS effects.

## Controllers (pacing-mode factor per approved change 1)
a none (unlocked, unaligned, duty 1); b best static, unaligned; b' best static, aligned; c PI duty + deadline-aware clock rule; c' PI guard (aligned) + clock rule that keeps a token fitting; d model-based, unaligned; d' model-based, aligned.
Decision cadence: pacing every 100 ms tick; clock every 1 s (plant: 443 ms actuation latency, <= 1 change/s).

## Tuning / evaluation split
Tuning seeds 100-109; held-out evaluation seeds 200-229. Best-static grids, PI gains, clock margin and model constants are chosen on tuning seeds only. Controller parameters are frozen (committed as data/sim_tuned.json) before the evaluation runs.

## Metrics and objective
Per run (after warm-up): fg miss fraction (latency > deadline; unfinished frames past their deadline count as misses), bg tok/s, mean GPU power, J/token, clock changes. Scalar objective for choosing among feasible settings: tok/s - 0.5 x power_W (lambda = 0.5 tok/s per W, fixed now). Pareto (tok/s, W) points are reported too.
Feasible = miss fraction <= 1% in the run.

## Decision rules (fixed now)
1. A controller "holds the SLO" in a scenario if its miss fraction is <= 1% in at least 90% of the evaluation seeds and its mean over seeds is <= 1%.
2. (c) and (c') must hold the SLO in S0-S3 or the failure is reported with the cause; no retuning on evaluation seeds.
3. (d) vs (c) and (d') vs (c'): compare the objective (tok/s - 0.5 W), tok/s and power over seeds that hold the SLO for both; paired by seed, bootstrap 90% CI of the median difference over the 30 seeds. (d) "earns its place" only if the CI of the objective difference excludes 0 in its favour in at least S1 and S4 and it does not lose beyond the CI in S0, S2, S3. Otherwise the report says it does not, and (c) stays the MVP controller.
4. Aligned vs unaligned: the same comparison for c' vs c, d' vs d, b' vs b.
5. All results are labelled simulation. The hardware smoke is a separate stage and needs Arjun's go.
