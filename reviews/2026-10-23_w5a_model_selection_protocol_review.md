# Review: W5a model-selection protocol draft (docs/W5A_MODEL_SELECTION_PROTOCOL.md) + W5a verification
Reviewer: Claude (cloud session). Status key: [CHANGE] before registering · [ANSWER] · [NOTE]

## Overall
W5a is clean: 280/280 cells, identical configuration across sessions, no clock/offload/ring flags, max 77 °C. Writing the protocol
before fitting anything, and naming exactly where the data don't match the plan, is the right move. Three changes make the selection
measure what the governor actually needs.

## Findings
1. [CHANGE] Choose the adaptation cells by DESIGN, not by list position. The "first 3 cells of W in list order" are random
   (clock, pacing) points; with 103/200 zero-token and 80 overloaded cells, some of them will teach the model almost nothing (a
   zero-token cell gives no token time). Fix a design-based rule now, using only design fields, never outcomes: e.g. the first 3
   cells of W in list order that are UNALIGNED with duty >= 0.5, at 3 distinct clocks (if fewer exist, take the next design-qualifying
   cells). That mirrors what a real governor does on a new workload: probe a few informative settings. Keep K = 1 (same rule) as the
   reported sensitivity.
2. [CHANGE] Add a decision-focused metric, because the governor uses the model to CHOOSE a setting, not to report numbers. For each
   held-out stratum (workload x condition), let the model pick the setting it predicts best among that stratum's observed candidates
   (max predicted tok/s s.t. predicted miss <= 1% and predicted power <= 60 W, using its uncertainty margin as the controller will), then
   score: (i) REGRET = observed tok/s of the best observed feasible candidate minus observed tok/s of the model's pick, counted as the full
   best value if the pick is observed infeasible; (ii) FALSE-FEASIBLE rate = share of picks that observed-violate the SLO or the budget.
   Make (ii) a hard gate (e.g. false-feasible <= 5% of picks) and (i) part of the 10%-of-best rule alongside the p99/tok_s/power errors.
   A model can have a small MAE and still pick unsafe settings; the regret and false-feasible scores catch that, and they are the numbers
   W5b will ultimately be judged on.
3. [CHANGE] Make the safety asymmetry explicit in target 1. Report miss classification as false-feasible (predicted <= 1%, observed
   > 1%) and false-infeasible rates separately; the false-feasible rate matters more.
4. [ANSWER] (a) Whole-cell adaptation as the W5a stand-in for "10 s": accepted, with finding 1's design-based rule. The 10 s version
   is tested on hardware in the W5b tuning blocks, as proposed. (b) Targets and the extra "within 10% of best on tok_s and power error"
   condition: accepted, plus findings 2–3. (c) Use scikit-learn HistGradientBoosting instead of installing LightGBM. A pip install now
   could upgrade shared dependencies (numpy/scipy) mid-study and change the environment W5a/W5b ran in; HGB is the same model family.
   Record the substitution in the protocol.
5. [NOTE] With only three workloads, LOWO has three folds. Report per-fold results, not only the mean, so one easy or hard workload
   can't dominate the choice silently.
6. [NOTE] Leave-one-condition-out: keep it reported-only, but include c14 (beyond the c0 search range) explicitly. It's the
   extrapolation case the S1 heavy phase can reach.
7. [NOTE] The overloaded and zero-token counts are real plant behaviour, and the protocol already says to use
   miss_frac_incl_abandoned. Good.
8. [NOTE] The helper Ctrl+C fix is untested elevated. Check it at the start of the first W5b tuning session: one Ctrl+C, prompt back
   within ~2 s, "clock reset done" printed.

## Decision
Register the protocol as plan addendum L after applying 1–3 and the HGB substitution; then write the grey-box cell-level predict
function test-first and run the selection exactly as registered.
