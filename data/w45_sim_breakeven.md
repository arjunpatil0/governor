# Break-even lambda (tok/s per W) between e and the dynamic aligned controllers (SIMULATION ONLY; medians over SLO-holding seeds)

x beats e on tok/s - lambda W iff lambda > lambda*. Source: data/w45_sim_followup.csv.

| jitter | scenario | x | tok/s e | W e | tok/s x | W x | lambda* |
|---|---|---|---|---|---|---|---|
| False | S1 | c' | 53.85 | 74.36 | 28.25 | 45.23 | 0.879 |
| False | S1 | d' | 53.85 | 74.36 | 34.21 | 48.59 | 0.762 |
| False | S1d | c' | 59.31 | 79.60 | 51.05 | 70.07 | 0.865 |
| False | S1d | d' | 59.31 | 79.60 | 43.95 | 61.48 | 0.848 |
| False | S4 | c' | 53.85 | 74.36 | 28.25 | 45.23 | 0.879 |
| False | S4 | d' | 53.85 | 74.36 | 34.21 | 48.59 | 0.762 |
| True | S1 | c' | 52.99 | 73.62 | 28.24 | 45.24 | 0.872 |
| True | S1 | d' | 52.99 | 73.62 | 34.18 | 48.57 | 0.751 |
| True | S1d | c' | 58.98 | 79.33 | 50.88 | 69.92 | 0.861 |
| True | S1d | d' | 58.98 | 79.33 | 43.03 | 60.84 | 0.863 |
| True | S4 | c' | 53.15 | 73.74 | 28.22 | 45.22 | 0.874 |
| True | S4 | d' | 53.15 | 73.74 | 34.18 | 48.57 | 0.754 |