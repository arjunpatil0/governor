# W5a model selection RE-RUN — POST HOC (plan addendum N, the only re-run; run 1 = data/w5a/selection.md)

**Selected: None**

Fallback (fixed in addendum N): no candidate passes G1-G3: d'B in W5b uses the grey-box ModelController (option B) with the safety shield unchanged; model selection did not discriminate (addendum N section 6)

## Gates (K = 3, pooled LOWO)

- G: G1a false-feasible cells 22.5% > 5%; G1b false-feasible picks 40.0% > 5%
- HGB: G2 coverage mu 88.2% outside 90-98%
- GP: G1a false-feasible cells 17.2% > 5%; G1b false-feasible picks 33.3% > 5%; G2 coverage mu 89.0% outside 90-98%
- MLP: G1a false-feasible cells 14.1% > 5%; G1b false-feasible picks 25.0% > 5%

## Pooled LOWO, K = 3

| cand | false-feasible cells at tau 0.8 (95% CI) | false-infeasible | false-feasible picks / picks (95% CI) | strata with feasible | regret_rel | ln-tok MAE | median rel tok err | power MAE W | cov ln-tok | cov power | latency 1 thr ms | latency default ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| G | 0.225 (0.165-0.295; 39 false-feasible cells) | 0.000 | 4 / 10 (0.12-0.74) | 8 of 18 | 0.46 | 0.10 | 0.08 | 6.4 | 0.91 | 0.94 | 0.29 | 0.23 |
| HGB | 0.008 (0.000-0.046; 1 false-feasible cells) | 0.127 | 0 / 8 (0.00-0.37) | 8 of 18 | 0.18 | 0.13 | 0.07 | 2.4 | 0.88 | 0.97 | 7.97 | 13.04 |
| GP | 0.172 (0.115-0.244; 25 false-feasible cells) | 0.104 | 3 / 9 (0.07-0.70) | 8 of 18 | 0.62 | 0.10 | 0.07 | 3.7 | 0.89 | 0.95 | 3.86 | 10.18 |
| MLP | 0.141 (0.073-0.238; 11 false-feasible cells) | 0.500 | 2 / 8 (0.03-0.65) | 8 of 18 | 0.71 | 0.11 | 0.08 | 3.7 | 0.93 | 0.92 | 2.55 | 3.01 |

Latency against the old 1 ms bound: G passes; HGB fails; GP fails; MLP fails. New bound (10 ms p99, 1 thread): G passes; HGB passes; GP passes; MLP passes.

## Per fold (K = 3): coverage ln-tok / power, false-feasible cell rate, picks (false-feasible), conformal q (ln units / W)

- G / held out llama32_1b: 0.81 / 0.85, 0.22, 5 (1), q 0.22 / 15.0
- G / held out llama32_3b: 1.00 / 1.00, 0.05, 1 (0), q 0.38 / 21.8
- G / held out phi35_mini: 1.00 / 0.96, 0.35, 4 (3), q 0.36 / 19.3
- HGB / held out llama32_1b: 0.78 / 0.96, 0.00, 5 (0), q 0.23 / 9.7
- HGB / held out llama32_3b: 1.00 / 0.98, 0.00, 1 (0), q 0.46 / 8.1
- HGB / held out phi35_mini: 0.94 / 0.99, 0.02, 2 (0), q 0.36 / 10.9
- GP / held out llama32_1b: 0.78 / 0.84, 0.22, 5 (1), q 0.19 / 13.4
- GP / held out llama32_3b: 0.97 / 1.00, 0.00, 1 (0), q 0.34 / 16.8
- GP / held out phi35_mini: 1.00 / 1.00, 0.20, 3 (2), q 0.37 / 18.7
- MLP / held out llama32_1b: 0.86 / 0.83, 0.20, 3 (0), q 0.23 / 9.6
- MLP / held out llama32_3b: 1.00 / 0.95, 0.00, 1 (0), q 0.42 / 9.5
- MLP / held out phi35_mini: 1.00 / 0.99, 0.17, 4 (2), q 0.28 / 12.2

## K = 1 sensitivity (not used): false-feasible cell rate, picks (ff), coverage ln-tok / power, regret_rel

- G: 0.222, 10 (3), 0.73 / 0.93, 0.21
- HGB: 0.009, 6 (1), 0.67 / 0.96, 0.54
- GP: 0.240, 8 (3), 0.70 / 0.95, 0.50
- MLP: 0.149, 7 (2), 0.75 / 0.97, 0.66

## Leave-one-condition-out (reported only), K = 3: pooled false-feasible cell rate, picks (ff); c14 alone: false-feasible cell rate, picks

- G: 0.237, 9 (4); c14: 0.643, 0 (0)
- HGB: 0.045, 7 (0); c14: 0.375, 0 (0)
- GP: 0.126, 6 (1); c14: 0.583, 0 (0)
- MLP: 0.086, 7 (1); c14: 0.500, 0 (0)

## Secondary (reported only): in-range p99 MAE (ms)

- G: 3.3 (n = 167)
- HGB: 2.7 (n = 167)
- GP: 2.6 (n = 167)
- MLP: 2.9 (n = 167)
