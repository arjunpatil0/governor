# Addendum to w2_colocation.yaml: capped-wait model for A2 (EXPLORATORY, POST-HOC; Arjun's reviewer's hypothesis, requested 2026-10-21)
Date: 2026-10-21 · Written BEFORE any A2 data exists (the only A2 run so far crashed after 3 cells, journal 0021, and is discarded) · Motivated by Experiment A results (journal 0020, commit ea8546a)

## Status
POST-HOC and EXPLORATORY. The hypothesis was formed after seeing A's data and is therefore not a confirmatory test. It changes NO registered decision rule: HA1, HA2, HA1_failure_classification, SA1-SA4 and the globaltimer trigger stand as registered. Whatever A2 shows about it is reported as exploratory, with the post-hoc label, whatever the outcome.

## What A found (journal 0020)
HA1 not supported (classified preempted_or_concurrent). Observed added wait (c = 0 cell medians over blocks) rises only from 0.153 to 0.298 ms over slice length m = 0.25 to 8 ms, against a residual-wait prediction rising 0.13 to 4.2 ms.

## Capped-wait model
fg wait = min(time remaining in the current bg slice, tau), plus a small constant switch cost (absorbed in the fit; tau is the cap, e.g. a scheduler time quantum; NO mechanism is claimed). For constant slices of length m and arrivals uniformly distributed over the slice: E[wait] = tau - tau^2/(2m) for m >= tau; m/2 for m < tau.
With tau = 0.3 ms: predicted 0.125, 0.210, 0.255, 0.278, 0.289, 0.294 ms at m = 0.25, 0.5, 1, 2, 4, 8. A's observed c = 0 medians: 0.153, 0.226, 0.255, 0.287, 0.297, 0.298 ms. (The reviewer's quoted A medians for m = 4 and 8 differ in the third decimal; the numbers above are recomputed from data/raw/w2_A/20261021T153524Z/results.csv.) A least-squares fit of tau to these six medians gives 0.308 ms (exploratory, six points, no uncertainty); the model undershoots at m = 0.25 (0.125 vs 0.153 ms). tau ~ 0.3 ms is therefore A's estimate, with this caveat.

## A2 exploratory test (SA1 cells: A cells with c = 0, m in {2, 4, 8}, as registered)
For each fg request landing inside a bg slice, compute time-to-slice-end = (slice end - arrival). Bin fg wait (latency minus the same block's no-bg baseline latency, as in A) by time-to-slice-end (bin width 0.05 ms below 1 ms, 0.5 ms above; bins with < 30 requests dropped). The capped-wait model predicts a flat plateau at about tau for time-to-end > tau, then slope -1 over the last tau ms. Report: (i) the binned curve per m and pooled; (ii) a fitted tau (piecewise fit: plateau tau, slope -1 below tau, plus constant offset) with a 90% block-cluster-bootstrap CI (10 blocks) and its comparison with A's estimate 0.308 ms. No pass/fail threshold and no multiplicity claim; the outcome is described, not decided. The phase-regression of SA1 (registered) is reported unchanged beside it.

## Analysis code
Written after A2 data exists, but its definition above is fixed now; if the code deviates (e.g. bin edges), the deviation is recorded.
