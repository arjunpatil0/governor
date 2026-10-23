# W5a model-selection protocol — DRAFT for review (written 2026-10-23, BEFORE any candidate model is fitted to W5a data)
Status: not yet a registered addendum. After reviewer sign-off it is committed unchanged as plan addendum L; nothing is fitted before that. Plan section B (docs/W45_PLAN.md) and yaml `W5a_model_selection` fix the candidates, LOWO, the selection rule and the latency/calibration bounds. This draft only fills what those leave open, because the W5a data have a shape the plan did not anticipate.

## 1. What the data are (facts, from data/w5a/verification.json and cell_list.json)
- 280 cells = 3 sessions (94/93/93), all present, 0 incidents, 0 manifest problems, same Armoury mode / exe sha256 / git head in all sessions.
- One row per cell (35 s: 5 s warm-up + 30 s window). Per-cell outputs: miss fraction, fg p50/p99, bg tok/s, token-time p50/p99, mean power (energy counter over the window), SM clock median. Per-frame latencies and per-token ends are in frames.npz; power exists only as ONE number per cell (two counter reads).
- 18 strata (3 workloads x 6 conditions), each holds only 15-16 of the 70 clock x pacing combinations: the design is a sparse fraction, so every model must generalise across clock and pacing, not interpolate inside a full grid.
- 80 of 280 cells are OVERLOADED (the frame loop abandoned frames; frames + abandoned = 1800 in all 80; miss incl. abandoned >= 0.5 in all 80). 103 of the 200 non-overloaded cells produced zero tokens in the window (aligned pacing with no slack, low duty, low clock). Both are real behaviours of the plant, not data errors, and the protocol must say how they are scored.

## 2. Proposed targets and scoring (decision-relevant, fixed before fitting)
1. `miss` = miss fraction INCLUDING abandoned frames (cell.json `miss_frac_incl_abandoned`; the plain `miss_frac` ignores abandoned frames and is not used). Scored as MAE and as a classification at the SLO: predicted vs observed (miss <= 0.01).
2. `tok_s` (bg tokens per second in the window). Scored as MAE in tok/s and relative error on cells with observed tok_s > 0; the zero-token cells are scored by classification (zero vs non-zero).
3. `power_w`. Scored as absolute error in W and as a classification at the 60 W budget (the primary budget).
4. `p99` fg latency, only on non-overloaded cells (abandoned = 0); overloaded cells are covered by target 1. The plan's "p99 absolute error of the fg latency prediction" is taken on these cells and reported next to the count excluded.
5. Interval coverage: each model gives a 95% interval for targets 2-4; coverage is computed per target on the held-out cells and must lie in 90-98% (plan rule). Coverage for `miss` is not used (bounded, mass at 0 and 1).
6. Latency: predict + decide p99 < 1 ms on this CPU, measured on the 70 (clock, pacing) candidates for one state, exactly as the controller does it.
The 10%-of-best rule of the plan is applied to the p99 absolute error of target 4 AND must not be worse than 10% of best on the tok_s and power MAE (a model that is simple but wrong on power under a power budget would not be selected).

## 3. LOWO and the "10 s of adaptation" — the one real deviation from plan B
Plan B says: fit on the other workloads, adapt online for 10 s on the held-out workload, then score. W5a cannot supply a 10 s adaptation window for power (one energy reading per 30 s cell). Proposal: adaptation unit = whole cells. For each held-out workload W (llama32_1b, llama32_3b, phi35_mini): the adaptation set is the first K = 3 cells of W in the frozen list order (session, order); the other cells of W are the test set. Fixed now, before any fit. The 10 s version is tested later on hardware in the W5b tuning blocks (T3), where it can be measured end to end, and is not claimed from W5a. K = 3 is a choice; the alternative K = 1 is also reported as a sensitivity run (reported, not used for selection).
Leave-one-scene-out (the plan also asks for it): leave out one CONDITION (c5, c7, c9, c11, c14, var9) with all workloads in training; no adaptation cells (scene change is meant to be handled by the model's cost input). Reported, not part of the selection rule unless the reviewer wants it.
The 8B held-out workload never appears.

## 4. Candidates and what is open
1. Grey-box + RLS: the structure already in controllers/model.py and sim/plant.py (clock law, token time, power, interference), steady-state per cell, with its scalars re-estimated by RLS from the adaptation cells. OPEN: the code predicts inside a simulation loop; a cell-level steady-state predict function has to be written (test-first) before this candidate exists. It must use only the plant parameters of the frozen W1/W2 anchors plus the adaptation cells (no W5a-trained constants beyond the RLS scalars).
2. LightGBM + online residual: `lightgbm` is NOT installed here. Installing it is a package install into your environment (pip --use-feature=truststore install lightgbm); I will not do it without your go. If you decline, candidate 2 is replaced by scikit-learn's HistGradientBoosting (availability still to be checked) and the report says so.
3. Sparse GP and 4. MLP ensemble (<= 2 x 32, 5 members): scikit-learn / numpy only; availability to be confirmed before the protocol is registered.
All candidates see the same inputs: clock, pacing mode, guard, duty, condition nominal cost (ms) and its variation flag, the workload's cost descriptors measurable online (token time at the reference clock from the adaptation cells), and the grey-box prediction as a feature / mean function (plan B). Seeds fixed; deterministic.
Selection rule exactly as plan B; if grey-box + RLS meets it, the report says the learned part is only the online calibration.

## 5. What this protocol does NOT do
- It does not use W5a to tune d'B constants (guard growth, thresholds): that is T3 hardware data only.
- It does not claim anything about the 10 s adaptation, the 35 W budget or the held-out 8B.
- Simulator results are not used.

## 6. Decisions I need before registering (reviewer + Arjun)
(a) Accept whole-cell adaptation with K = 3 (section 3) as the W5a version of the plan's "10 s".
(b) Accept the target set and the extra "not worse than 10% of best on tok_s and power MAE" condition (section 2).
(c) OK to `pip install --use-feature=truststore lightgbm` (candidate 2), or substitute sklearn HistGradientBoosting.
