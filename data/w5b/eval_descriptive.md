# W5b evaluation: DESCRIPTIVE tables (POST HOC, not registered tests)

Source: results.csv, 425 cells. Feasible = miss <= 1% and counter power <= budget (the registered cell definition). tok/s is the background rate in the measured window; a feasible cell scores its tok/s, an infeasible one 0. final_pacing_mode: governed = the controller's final mode, static = its setting's mode, arm a = unaligned.

## 60 W (PRIMARY family)

scene controller  n  miss_ok  power_ok  feasible  med_tok_s  med_miss_pct  med_power_w      final_pacing_mode
   S0          a 10       10         0         0      48.14          0.00         90.5           unaligned 10
   S0        g'B 10       10        10        10       0.00          0.00         30.2             aligned 10
   S0         eB 10       10        10        10       0.00          0.00         30.5             aligned 10
   S0    c'B-T3b 10        9         9         8      18.11          0.00         58.4 aligned 9, unaligned 1
   S0    c'B-T3c 10        0        10         0       0.70          1.85         23.8           unaligned 10
   S0        d'B 10       10        10        10      17.52          0.00         58.8           unaligned 10
   S1          a 10        0         0         0      47.69         34.10         89.9           unaligned 10
   S1        g'B 10       10        10        10      19.97          0.00         40.9             aligned 10
   S1         eB 10       10        10        10      19.97          0.00         40.8             aligned 10
   S1    c'B-T3b 10        0        10         0      13.75          6.28         38.9           unaligned 10
   S1    c'B-T3c 10        0        10         0       0.74          5.64         25.2           unaligned 10
   S1        d'B 10        0        10         0      19.38          1.72         55.8           unaligned 10
  S1d          a 10        0         0         0      48.27          5.42         90.1           unaligned 10
  S1d        g'B 10       10        10        10      16.56          0.00         38.9             aligned 10
  S1d         eB 10       10        10        10      16.74          0.00         39.9             aligned 10
  S1d    c'B-T3b 10        0        10         0      12.84          2.54         33.8           unaligned 10
  S1d    c'B-T3c 10        0        10         0       0.69          2.03         24.3           unaligned 10
  S1d        d'B 10       10        10        10      17.85          0.25         59.0           unaligned 10
   S2          a 10       10         0         0      64.22          0.00         91.6           unaligned 10
   S2        g'B 10       10        10        10      31.98          0.04         42.7             aligned 10
   S2         eB 10       10        10        10      31.38          0.04         39.5             aligned 10
   S2    c'B-T3b 10        0        10         0      31.50          1.88         45.3           unaligned 10
   S2    c'B-T3c 10        0        10         0      28.33          1.83         33.6           unaligned 10
   S2        d'B 10       10        10        10      41.26          0.04         58.2           unaligned 10
   S5          a 10        0         0         0      22.95         34.65         90.5           unaligned 10
   S5        g'B 10       10        10        10       0.00          0.00         30.3             aligned 10
   S5         eB 10       10        10        10       0.00          0.00         30.5             aligned 10
   S5    c'B-T3b 10        0        10         0       0.82         11.07         25.6           unaligned 10
   S5    c'B-T3c 10        0        10         0       0.29          6.50         25.0           unaligned 10
   S5        d'B 10        0        10         0       7.83          4.72         58.1           unaligned 10

## 35 W (EXPLORATORY family)

scene controller  n  miss_ok  power_ok  feasible  med_tok_s  med_miss_pct  med_power_w      final_pacing_mode
   S0        g'B  5        5         5         5       0.00          0.00         25.5              aligned 5
   S0         eB  5        5         5         5       0.00          0.00         25.7              aligned 5
   S0    c'B-T3b  5        4         1         0       4.65          0.00         38.2 aligned 4, unaligned 1
   S0    c'B-T3c  5        0         5         0       0.72          1.89         23.5            unaligned 5
   S0        d'B  5        0         5         0       6.18          4.28         33.3            unaligned 5
   S1        g'B  5        5         5         5      18.95          0.00         34.0              aligned 5
   S1         eB  5        5         4         4      18.75          0.00         34.5              aligned 5
   S1    c'B-T3b  5        0         5         0       3.83          1.72         31.9            unaligned 5
   S1    c'B-T3c  5        0         5         0       0.72          5.72         25.1            unaligned 5
   S1        d'B  5        0         0         0       6.32          2.28         37.7            unaligned 5
  S1d        g'B  5        5         5         5       4.43          0.00         27.8              aligned 5
  S1d         eB  5        5         5         5       4.23          0.00         27.3              aligned 5
  S1d    c'B-T3b  5        2         5         2       3.72          2.08         30.1            unaligned 5
  S1d    c'B-T3c  5        0         5         0       0.70          2.03         24.1            unaligned 5
  S1d        d'B  5        0         4         0       6.70          2.39         34.7            unaligned 5
   S2        g'B  5        5         1         1      31.28          0.04         36.4              aligned 5
   S2         eB  5        5         1         1      31.50          0.04         36.0              aligned 5
   S2    c'B-T3b  5        0         2         0      21.63          1.79         35.4            unaligned 5
   S2    c'B-T3c  5        0         5         0      29.55          1.79         34.2            unaligned 5
   S2        d'B  5        0         0         0      33.40          4.50         40.9            unaligned 5
   S5        g'B  5        5         5         5       0.00          0.00         25.2              aligned 5
   S5         eB  5        5         5         5       0.00          0.00         25.4              aligned 5
   S5    c'B-T3b  5        0         5         0       0.90         12.33         26.0            unaligned 5
   S5    c'B-T3c  5        0         5         0       0.30          6.39         24.9            unaligned 5
   S5        d'B  5        0         0         0       2.87          5.67         37.3            unaligned 5

## d'B by final pacing mode (descriptive)

                                   n  med_tok_s  min_tok_s  max_tok_s  med_miss
budget_w scene final_pacing_mode                                               
35.0     S0    unaligned           5      6.183      5.133      6.817     0.043
         S1    unaligned           5      6.317      6.000      6.817     0.023
         S1d   unaligned           5      6.700      6.400      7.767     0.024
         S2    unaligned           5     33.400     33.183     33.933     0.045
         S5    unaligned           5      2.867      2.867      2.967     0.057
60.0     S0    unaligned          10     17.517     16.417     18.867     0.000
         S1    unaligned          10     19.375     18.433     20.867     0.017
         S1d   unaligned          10     17.850     16.067     19.333     0.002
         S2    unaligned          10     41.258     40.750     42.300     0.000
         S5    unaligned          10      7.833      7.333      8.117     0.047
