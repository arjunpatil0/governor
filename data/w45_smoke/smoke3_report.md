# W4-5 hardware smoke 2: token durations and overrun (DIAGNOSTIC, not a registered result; journal 0041)

Source: data/w45_smoke/smoke3/overrun.json and overrun_raw_*.json. Long token = tok_ms > 15 ms. 'fit test would admit' = the driver's rule now + EWMA estimate + guard <= next arrival, evaluated at the logged token start with the estimate reconstructed from the logged durations (the driver's own 0.9/0.1 EWMA).

| run | cost ms | tokens | tok/s in the measured window (bg_tok_s) | tok/s DONE line (whole driver life) | fg p50 / p99 ms | fg miss | long tokens | clean tok_ms p50 | long tok_ms p50 | start phase after arrival, clean p50 [p10, p90] | long p50 | fit test would admit | driver overlap flag | est EWMA / clean p50 (logged) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| aligned_g0_d1_cost4 | 4.0 | 1510 | 60.0 | 60.2 | 3.00 / 3.29 | 0.000 | 0% | 10.15 | nan | 3.01 [2.99, 3.07] | - | 94.4% (logged estimate) | 0% | 10.14 / 10.11 |
| aligned_g1_d1_cost4 | 4.0 | 1506 | 60.0 | 60.1 | 3.01 / 3.14 | 0.000 | 0% | 10.15 | nan | 3.03 [3.01, 3.08] | - | 94.8% (logged estimate) | 0% | 10.16 / 10.10 |
| aligned_g0_d1_cost7 | 7.0 | 1525 | 59.9 | 60.4 | 5.20 / 5.38 | 0.000 | 0% | 10.10 | nan | 5.21 [5.20, 5.29] | - | 95.4% (logged estimate) | 1% | 10.12 / 10.04 |
| aligned_g1_d1_cost7 | 7.0 | 1386 | 53.9 | 54.9 | 5.21 / 5.47 | 0.000 | 0% | 10.08 | nan | 5.22 [5.20, 5.33] | - | 95.0% (logged estimate) | 1% | 10.04 / 10.01 |
| aligned_g1_d1_cost9 | 9.0 | 23 | 0.0 | 0.9 | 6.70 / 6.96 | 0.000 | nan% | nan | nan | - | - | - | 9% | 12.21 / 9.79 |
| unaligned_d1_cost9 | 9.0 | 950 | 37.0 | 36.9 | 308.61 / 548.32 | 1.000 | 100% | nan | 27.69 | - | 8.49 | n/a (unaligned) | 97% | 27.48 / 9.64 |

Reading: see journal 0041. The table is produced by analysis/smoke2_report.py from the files above; nothing in it is estimated.
