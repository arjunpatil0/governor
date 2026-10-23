# W5a model selection result (analysis/w5a_select.py, protocol = plan addendum L)

**Selected: None**  (no candidate passes G1-G3)

## Gates (K = 3, pooled LOWO)

- G: G1 false-feasible 50.0% > 5%; G2 coverage tok_s 72.3% outside 90-98%
- HGB: G2 coverage tok_s 74.5% outside 90-98%; G3 latency p99 15.64 ms >= 1 ms
- GP: G2 coverage tok_s 73.1% outside 90-98%; G3 latency p99 5.69 ms >= 1 ms
- MLP: G2 coverage tok_s 77.1% outside 90-98%; G2 coverage p99 85.9% outside 90-98%; G3 latency p99 1.87 ms >= 1 ms

## Pooled LOWO, K = 3

| cand | false-feasible picks | picks | regret_rel | tok MAE | power MAE W | p99 err ms (p99 of abs err) | cov tok | cov power | cov p99 | latency ms |
|---|---|---|---|---|---|---|---|---|---|---|
| G | 5 | 10 | 0.48 | 4.4 | 6.4 | 2425 | 0.72 | 0.92 | 0.94 | 0.25 |
| HGB | 0 | 8 | 0.51 | 5.4 | 2.4 | 1750 | 0.75 | 0.96 | 0.92 | 15.64 |
| GP | 0 | 1 | 0.99 | 4.4 | 3.7 | 2410 | 0.73 | 0.94 | 0.94 | 5.69 |
| MLP | 0 | 8 | 0.71 | 5.4 | 3.7 | 2561 | 0.77 | 0.91 | 0.86 | 1.87 |

## Per fold (K = 3): tok MAE / power MAE / picks (false-feasible) / regret_rel / coverage tok, power, p99

- G / held out llama32_1b: 12.4 / 8.2 / 6 (2) / 0.42 / 0.16, 0.84, 0.96
- G / held out llama32_3b: 0.8 / 3.3 / 0 (0) / 1.00 / 1.00, 1.00, 0.92
- G / held out phi35_mini: 0.3 / 7.6 / 4 (3) / 0.48 / 1.00, 0.92, 0.94
- HGB / held out llama32_1b: 12.0 / 2.9 / 4 (0) / 0.42 / 0.22, 0.93, 0.99
- HGB / held out llama32_3b: 2.3 / 2.2 / 4 (0) / 1.00 / 1.00, 0.98, 0.80
- HGB / held out phi35_mini: 2.0 / 2.1 / 0 (0) / 1.00 / 1.00, 0.98, 0.97
- GP / held out llama32_1b: 11.9 / 7.2 / 0 (0) / 1.00 / 0.18, 0.83, 0.99
- GP / held out llama32_3b: 0.8 / 1.8 / 1 (0) / 0.86 / 1.00, 1.00, 0.88
- GP / held out phi35_mini: 0.7 / 2.3 / 0 (0) / 1.00 / 1.00, 1.00, 0.97
- MLP / held out llama32_1b: 11.6 / 5.4 / 3 (0) / 0.73 / 0.30, 0.81, 0.75
- MLP / held out llama32_3b: 2.6 / 2.6 / 2 (0) / 0.68 / 1.00, 0.95, 0.85
- MLP / held out phi35_mini: 2.2 / 3.1 / 3 (0) / 0.48 / 1.00, 0.98, 0.98

## Miss classification at the SLO (pooled LOWO K = 3): false-feasible / false-infeasible, share of all test cells

- G: 0.137 / 0.148  (false-feasible among predicted-feasible 0.282; n = 271)
- HGB: 0.000 / 0.258  (false-feasible among predicted-feasible 0.000; n = 271)
- GP: 0.000 / 0.399  (false-feasible among predicted-feasible 0.000; n = 271)
- MLP: 0.011 / 0.351  (false-feasible among predicted-feasible 0.071; n = 271)

## Sensitivity K = 1 (not used for selection): false-feasible picks / picks, regret_rel, tok MAE, power MAE

- G: 4 / 11, 0.21, 4.0, 6.2
- HGB: 1 / 10, 0.82, 6.3, 2.9
- GP: 2 / 10, 0.74, 8.2, 4.7
- MLP: 1 / 9, 0.21, 6.0, 4.4

## Leave-one-condition-out (reported only), K = 3: pooled tok MAE / power MAE / p99 err / picks (ff); c14 alone

- G: 4.6 / 6.0 / 2861 / 11 (5); c14: tok 2.0, power 3.4, p99 err 707, picks 1 (1)
- HGB: 4.4 / 2.3 / 2324 / 7 (0); c14: tok 1.4, power 1.2, p99 err 861, picks 0 (0)
- GP: 3.8 / 2.5 / 2303 / 6 (3); c14: tok 0.8, power 1.6, p99 err 629, picks 0 (0)
- MLP: 3.5 / 1.7 / 2745 / 8 (2); c14: tok 2.2, power 1.3, p99 err 1549, picks 1 (1)

## Implementation notes

- Where G predicts an overloaded cell its p99 is undefined (nan); for residuals, features and scoring it is replaced by the 16.667 ms period (the lowest latency an overloaded frame can have).
- The online residual bias of the learned candidates is the mean (n/(n+1) shrunk) of (y - G - g) over the workload's adaptation cells, per target; targets without a defined value in a cell skip that cell.
- sigma_hat of every candidate is the RMS of its out-of-fold residuals (inner leave-one-workload-out among the training workloads, with the same calibration and bias) per target; GP std and ensemble spread are not used.
- Residual models are fit on all training cells (adaptation cells included); p99 residual models only on non-overloaded cells.
- Latency is measured on one fitted model per candidate (the fold that holds out llama32_3b, K = 3): grey-box + features + 4 residual predictions + bias + intervals + decision for the 70 settings of condition c9.
