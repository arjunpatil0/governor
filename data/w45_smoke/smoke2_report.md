# W4-5 hardware smoke 2: token durations and overrun (DIAGNOSTIC, not a registered result; journal 0041)

Source: data/w45_smoke/smoke2/overrun.json and overrun_raw_*.json. Long token = tok_ms > 15 ms. 'fit test would admit' = the driver's rule now + EWMA estimate + guard <= next arrival, evaluated at the logged token start with the estimate reconstructed from the logged durations (the driver's own 0.9/0.1 EWMA).

| run | cost ms | tokens | true tok/s (DONE line) | fg p50 / p99 ms | fg miss | long tokens | clean tok_ms p50 | long tok_ms p50 | start phase after arrival, clean p50 [p10, p90] | long p50 | fit test would admit | driver overlap flag | est EWMA / clean p50 (logged) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| bg_alone_unaligned_d1 | S0 (7) | 1534 | 100.2 | - | 0.000 | 0% | 10.03 | nan | - | - | - | - | - |
| aligned_g0_d1 | S0 (7) | 1510 | 59.8 | 6.78 / 13.55 | 0.000 | 30% | 10.12 | 20.71 | 6.01 [5.20, 7.16] | 15.67 | 0.3% | - | - |
| aligned_g0.5_d1 | S0 (7) | 1507 | 60.0 | 6.69 / 13.61 | 0.000 | 28% | 10.13 | 20.77 | 5.98 [5.21, 7.19] | 15.67 | 0.0% | - | - |
| aligned_g1_d1 | S0 (7) | 1498 | 59.7 | 6.87 / 13.73 | 0.000 | 27% | 10.20 | 20.92 | 6.07 [5.22, 7.36] | 15.67 | 0.2% | - | - |
| aligned_g2_d1 | S0 (7) | 1502 | 59.9 | 6.82 / 13.71 | 0.000 | 27% | 10.21 | 20.95 | 6.14 [5.22, 7.42] | 15.67 | 0.1% | - | - |
| aligned_g0_d0.5 | S0 (7) | 508 | 20.2 | 6.69 / 13.47 | 0.000 | 99% | 9.90 | 20.23 | 5.54 [5.23, 5.79] | 15.67 | 0.0% | - | - |
| unaligned_d1 | S0 (7) | 1241 | 49.5 | 13.12 / 13.51 | 0.000 | 100% | nan | 20.45 | - | 10.40 | n/a (unaligned) | - | - |

Reading: see journal 0041. The table is produced by analysis/smoke2_report.py from the files above; nothing in it is estimated.
