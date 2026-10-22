# Experiment G report

Source `C:\Users\arjun\governor\data\raw\w2_G\20261022T062433Z` | admin True | AC True | ambient 25.0 C | Armoury Performance | NVIDIA GeForce RTX 4070 Laptop GPU driver 616.92 | yaml e1df18ccd6898bd9 | dll 7768289069367275 | git 7cea2e69 | blocks 10 | cells 170
Addenda: experiments/w2_colocation_addendum_globaltimer_2026-10-22.md and ..._prerun_2026-10-22.md (and _witness_ if registered). Each prediction: held / did not hold, with the numbers.
Block set for gap, run, overlap and preemption analyses: WITNESS blocks only (blockIdx < 108, the first three blocks per SM).

## Pre-check (iii): instrumentation overhead (registered acceptance; if it fails the timeline is NOT interpreted)

```
 block  base_on_p50  base_off_p50  wait_on  wait_off  slice_on_ms  slice_off_ms  gpu_on_ms  gpu_off_ms
     0       0.1467        0.1290   0.2995    0.3048       2.1484        2.1144      0.087       0.085
     1       0.1422        0.1416   0.3024    0.2896       2.1372        2.1062      0.087       0.085
     2       0.1438        0.1411   0.2950    0.2885       2.1437        2.1121      0.087       0.085
     3       0.1403        0.1401   0.3126    0.2979       2.1474        2.1080      0.087       0.085
     4       0.1418        0.1388   0.2915    0.2946       2.1413        2.1039      0.087       0.085
     5       0.1421        0.1342   0.2965    0.3020       2.1419        2.1102      0.087       0.085
     6       0.1259        0.1206   0.2898    0.3009       2.1395        2.1095      0.087       0.085
     7       0.1418        0.1412   0.3063    0.2917       2.1413        2.1057      0.087       0.085
     8       0.1405        0.1406   0.3029    0.2867       2.1410        2.1055      0.087       0.085
     9       0.1418        0.1402   0.3037    0.2948       2.1416        2.1130      0.087       0.085
```

- median fg-alone latency, instrumented vs not: relative difference 1.2% (limit 5%)
- observed wait of R_2, instrumented 0.3010 ms vs uninstrumented 0.2947 ms: difference 0.0063 ms (limit 0.03)
- bg mean slice 2.1415 vs 2.1087 ms; fg gpu p50 0.0870 vs 0.0850 ms
- **pre-check (iii): PASS**

## P1-P3 on the uninstrumented R_m_off cells (fresh seeds; the block baseline is g_baseline_off)

### P1: cell-median observed wait within +/-0.03 ms of A

```
 m_ms  n_blocks  obs_wait_ms  a_wait_ms  diff_ms  within_tol
  0.5        10       0.2264      0.226   0.0004        True
  1.0        10       0.2617      0.255   0.0067        True
  2.0        10       0.2947      0.287   0.0077        True
  8.0        10       0.3042      0.298   0.0062        True
```

- P1 HELD

### P2: capped-wait fit on the observed slice-end axis (n = 80064 requests, all four m pooled)

- tau = 0.260 ms, 90% block-bootstrap CI [0.260, 0.260], offset 0.035 ms; registered range 0.22-0.31 ms (A: 0.260)
- P2 HELD

### P3: ripple on the unstretched axis (binned means, A's bins)

```
  lo   hi    n  mean_wait_ms
0.00 0.05 3423        0.0986
0.05 0.10 3462        0.1335
0.10 0.15 3457        0.1453
0.15 0.20 3544        0.1753
0.20 0.25 3387        0.2024
0.25 0.30 3394        0.2511
0.30 0.35 3563        0.2951
0.35 0.40 3410        0.3026
0.40 0.45 3346        0.3497
0.45 0.50 3245        0.3680
0.50 0.55 1565        0.3585
0.55 0.60 1571        0.3374
0.60 0.65 1567        0.2163
0.65 0.70 1519        0.2596
0.70 0.75 1475        0.3041
0.75 0.80 1589        0.2680
0.80 0.85 1484        0.2863
0.85 0.90 1555        0.3381
0.90 0.95 1555        0.3615
0.95 1.00 1469        0.3701
1.00 1.50 6018        0.3155
1.50 2.00 5916        0.3280
2.00 2.50 1149        0.3079
2.50 3.00 1204        0.3071
3.00 3.50 1218        0.3082
3.50 4.00 1143        0.2989
4.00 4.50 1191        0.3153
4.50 5.00 1228        0.3146
5.00 5.50 1180        0.3159
5.50 6.00 1208        0.2980
6.00 6.50 1193        0.3095
6.50 7.00 1148        0.3108
7.00 7.50 1229        0.3329
7.50 8.00 1179        0.3305
```

- local minimum 0.35-0.40: False (drop -0.008 ms below the preceding maximum); local minimum 0.80-0.85: False (drop 0.082 ms); required drop >= 0.04 ms (A: 0.300->0.214, 0.364->0.232)
- P3 DID NOT HOLD

## Witness validity gate (addendum 3 section A)

- g_bgalone: witness preempted fraction 0.000% over 2665332 blocks -> PASS (limit 1%)
- g_bgalone_3bpsm: witness preempted fraction 0.000% over 2633148 blocks -> PASS (limit 1%)
- gate (i): PASS; gate (ii) placement is reported per cell below (nominal / fallback / excluded launches)

## Timeline cells: coverage, trust and results per block (recorded-interval rule, addendum 2 section C)

Coverage and trust (fg_share = share of the cell's measured fg requests wholly inside the recorded interval; untrusted = blocks with gap-log overflow; gap_lost = gaps lost to a full global list):

```
 block   cell  n_fg_in_interval  n_bg_launches  interval_s  fg_share  bg_launches_dropped  n_untrusted_fg  n_untrusted_bg  gap_lost  fg_w_nominal  fg_w_fallback  fg_w_excluded  bg_w_nominal  bg_w_fallback  bg_w_excluded
     0   g_R2              1990           5116      10.977     1.000                    0               0               0         0          2000              0              0          5116              0              0
     0   g_R8              2000           1269      10.890     0.997                    0               0               0         0          2000              0              0          1269              0              0
     0   g_T1               997           4522      10.852     1.000                    0               0               0         0          1000              0              0          4522              0              0
     0   g_T4               399           4366      11.562     1.000                    0               0               0         0           400              0              0          4366              0              0
     0 g_R0.5               812           7407       3.948     0.404                13265               0               0         0          2000              0              0          7407              0              0
     0   g_R1              1558           7407       7.904     0.783                 3046               0               0         0          2000              0              0          7407              0              0
     1   g_R1              1604           7407       7.921     0.795                 2868               0               0         0          2000              0              0          7407              0              0
     1   g_R2              2000           5342      11.401     0.995                    0               0               0         0          2000              0              0          5342              0              0
     1   g_R8              1998           1241      10.657     1.000                    0               0               0         0          2000              0              0          1241              0              0
     1   g_T4               400           4362      11.566     1.000                    0               0               0         0           400              0              0          4362              0              0
     1 g_R0.5               781           7407       3.937     0.390                13368               0               0         0          2000              0              0          7407              0              0
     1   g_T1              1000           4498      10.858     0.973                    0               0               0         0          1000              0              0          4498              0              0
     2   g_R8              2000           1312      11.239     0.991                    0               0               0         0          2000              0              0          1312              0              0
     2   g_T1              1000           4692      11.217     0.983                    0               0               0         0          1000              0              0          4692              0              0
     2 g_R0.5               798           7407       3.941     0.406                13162               0               0         0          2000              0              0          7407              0              0
     2   g_T4               400           3230       9.314     0.980                    0               0               0         0           400              0              0          3230              0              0
     2   g_R2              1979           5029      10.762     1.000                    0               0               0         0          2000              0              0          5029              0              0
     2   g_R1              1573           7407       7.906     0.803                 2836               0               0         0          2000              0              0          7407              0              0
     3   g_R2              1993           4874      10.446     1.000                    0               0               0         0          2000              0              0          4874              0              0
     3 g_R0.5               743           7407       3.927     0.372                13728               0               0         0          2000              0              0          7407              0              0
     3   g_T1              1000           4556      10.915     0.999                    0               0               0         0          1000              0              0          4556              0              0
     3   g_R1              1609           7407       7.920     0.800                 2600               0               0         0          2000              0              0          7407              0              0
     3   g_R8              1966           1246      10.689     1.000                    0               0               0         0          2000              0              0          1246              0              0
     3   g_T4               388           4181      11.088     1.000                    0               0               0         0           400              0              0          4181              0              0
     4   g_R2              2000           5156      11.023     1.000                    0               0               0         0          2000              0              0          5156              0              0
     4 g_R0.5               759           7407       3.942     0.372                13945               0               0         0          2000              0              0          7407              0              0
     4   g_T1              1000           4676      11.198     0.983                    0               0               0         0          1000              0              0          4676              0              0
     4   g_R8              2000           1328      11.378     0.975                    0               0               0         0          2000              0              0          1328              0              0
     4   g_R1              1551           7407       7.901     0.776                 3024               0               0         0          2000              0              0          7407              0              0
     4   g_T4               400           4143      11.118     0.988                    0               0               0         0           400              0              0          4143              0              0
     5   g_T1              1000           4823      11.497     0.983                    0               0               0         0          1000              0              0          4823              0              0
     5 g_R0.5               761           7407       3.932     0.379                14180               0               0         0          2000              0              0          7407              0              0
     5   g_T4               400           4053      10.923     0.993                    0               0               0         0           400              0              0          4053              0              0
     5   g_R8              1986           1259      10.808     1.000                    0               0               0         0          2000              0              0          1259              0              0
     5   g_R1              1554           7407       7.904     0.788                 2985               0               0         0          2000              0              0          7407              0              0
     5   g_R2              2000           5175      11.067     0.990                    0               0               0         0          2000              0              0          5175              0              0
     6   g_T4               398           4051      10.889     1.000                    0               0               0         0           400              0              0          4051              0              0
     6   g_R2              1958           5108      10.911     0.999                    0               0               0         0          2000              0              0          5108              0              0
     6   g_R1              1619           7407       7.918     0.812                 2783               0               0         0          2000              0              0          7407              0              0
     6   g_T1               999           4736      11.283     1.000                    0               0               0         0          1000              0              0          4736              0              0
     6 g_R0.5               819           7407       3.948     0.414                13015               0               0         0          2000              0              0          7407              0              0
     6   g_R8              1991           1302      11.152     0.999                    0               0               0         0          2000              0              0          1302              0              0
     7 g_R0.5               814           7407       3.948     0.406                12961               0               0         0          2000              0              0          7407              0              0
     7   g_T1              1000           4419      10.665     0.992                    0               0               0         0          1000              0              0          4419              0              0
     7   g_R8              1996           1309      11.210     1.000                    0               0               0         0          2000              0              0          1309              0              0
     7   g_R1              1659           7407       7.928     0.840                 2437               0               0         0          2000              0              0          7407              0              0
     7   g_R2              2000           5175      11.063     0.993                    0               0               0         0          2000              0              0          5175              0              0
     7   g_T4               400           3897      10.652     0.985                    0               0               0         0           400              0              0          3897              0              0
     8   g_R1              1627           7407       7.924     0.812                 2726               0               0         0          2000              0              0          7407              0              0
     8   g_R2              1967           5099      10.899     1.000                    0               0               0         0          2000              0              0          5099              0              0
     8   g_T1              1000           4443      10.693     0.996                    0               0               0         0          1000              0              0          4443              0              0
     8 g_R0.5               781           7407       3.936     0.397                13266               0               0         0          2000              0              0          7407              0              0
     8   g_R8              1985           1290      11.053     1.000                    0               0               0         0          2000              0              0          1290              0              0
     8   g_T4               395           4366      11.533     1.000                    0               0               0         0           400              0              0          4366              0              0
     9   g_R2              2000           5164      11.041     0.994                    0               0               0         0          2000              0              0          5164              0              0
     9   g_R1              1594           7407       7.930     0.784                 2815               0               0         0          2000              0              0          7407              0              0
     9   g_T4               400           4101      11.083     0.980                    0               0               0         0           400              0              0          4101              0              0
     9 g_R0.5               773           7407       3.936     0.387                14089               0               0         0          2000              0              0          7407              0              0
     9   g_T1              1000           4352      10.517     0.989                    0               0               0         0          1000              0              0          4352              0              0
     9   g_R8              1990           1242      10.663     0.999                    0               0               0         0          2000              0              0          1242              0              0
```

Per block results:

```
 block   cell  alone_span_ms  n_sliced  q_pooled_ms  q_fg_ms  q_bg_ms   s_ms  n_neg_s  n_overlap  n_overlap_same_sm  n_overlap_diff_sm  n_ties  n_fg_blocks  g_thr_us  preempt_frac  preempt_frac_with_fg  p8_delay_p99_ms
     0   g_R2         0.0492         0          NaN      NaN      NaN    NaN        0          0                  0                  0       0       214920    32.768        0.1070                0.1004           1.0303
     0   g_R8         0.0492         0          NaN      NaN      NaN    NaN        0          0                  0                  0       0       216000    32.768        0.4402                0.4305           1.0101
     0   g_T1         0.5827       899       0.3738      NaN   0.3738 0.1352       38       2664                562               2653       0       107676    32.768        0.1379                0.0870           5.0706
     0   g_T4         2.3572       399       0.3717   0.3748   0.3666 0.1526       49       3295                649               3275       0        43092    32.768        0.1761                0.1148          32.1811
     0 g_R0.5         0.0492         0          NaN      NaN      NaN    NaN        0          0                  0                  0       0        87696    32.768        0.0000                0.0000           0.6679
     0   g_R1         0.0492         0          NaN      NaN      NaN    NaN        0          0                  0                  0       0       168264    32.768        0.0259                0.0259           0.8686
     1   g_R1         0.0492         0          NaN      NaN      NaN    NaN        0          0                  0                  0       0       173232    32.768        0.0278                0.0276           0.9118
     1   g_R2         0.0492         0          NaN      NaN      NaN    NaN        0          0                  0                  0       0       216000    32.768        0.1008                0.0943           0.9752
     1   g_R8         0.0492         0          NaN      NaN      NaN    NaN        0          0                  0                  0       0       215784    32.768        0.4249                0.4161           0.9855
     1   g_T4         2.3572       400       0.3717   0.3748   0.3666 0.1536       68       4422                803               4386       0        43200    32.768        0.1778                0.1153          25.6981
     1 g_R0.5         0.0492         0          NaN      NaN      NaN    NaN        0          0                  0                  0       0        84348    32.768        0.0000                0.0000           0.6275
     1   g_T1         0.5816       921       0.3707      NaN   0.3707 0.1393       38       2124                370               2110       0       108000    32.768        0.1412                0.0896           4.8418
     2   g_R8         0.0492         0          NaN      NaN      NaN    NaN        0          0                  0                  0       0       216000    32.768        0.4139                0.4032           0.9985
     2   g_T1         0.5827       941       0.3738      NaN   0.3738 0.1352       31       3060                565               3046       0       108000    32.768        0.1373                0.0874           4.7449
     2 g_R0.5         0.0492         0          NaN      NaN      NaN    NaN        0          0                  0                  0       0        86184    32.768        0.0000                0.0000           0.6866
     2   g_T4         2.3572       400       0.3717   0.3758   0.3656 0.1516       45       3080                556               3060       0        43200    32.768        0.2439                0.1538          24.1333
     2   g_R2         0.0492         0          NaN      NaN      NaN    NaN        0          0                  0                  0       0       213732    32.768        0.1060                0.0994           0.9953
     2   g_R1         0.0492         0          NaN      NaN      NaN    NaN        0          0                  0                  0       0       169884    32.768        0.0271                0.0271           0.8703
     3   g_R2         0.0492         0          NaN      NaN      NaN    NaN        0          0                  0                  0       0       215244    32.768        0.1035                0.0967           1.0932
     3 g_R0.5         0.0492         0          NaN      NaN      NaN    NaN        0          0                  0                  0       0        80244    32.768        0.0000                0.0000           0.6540
     3   g_T1         0.5827       929       0.3738      NaN   0.3738 0.1331       28       2844                422               2823       0       108000    32.768        0.1372                0.0953           4.6470
     3   g_R1         0.0492         0          NaN      NaN      NaN    NaN        0          0                  0                  0       0       173772    32.768        0.0276                0.0274           0.8516
     3   g_R8         0.0492         0          NaN      NaN      NaN    NaN        0          0                  0                  0       0       212328    32.768        0.4398                0.4323           1.0271
     3   g_T4         2.3572       388       0.3768   0.3779   0.3727 0.1475      125       7193               1320               7140       0        41904    32.768        0.1818                0.1122          26.0062
     4   g_R2         0.0492         0          NaN      NaN      NaN    NaN        0          0                  0                  0       0       216000    32.768        0.1045                0.0980           1.0033
     4 g_R0.5         0.0492         0          NaN      NaN      NaN    NaN        0          0                  0                  0       0        81972    32.768        0.0000                0.0000           0.6471
     4   g_T1         0.5827       915       0.3707      NaN   0.3707 0.1403       28       1548                257               1535       0       108000    32.768        0.1409                0.0841           5.4105
     4   g_R8         0.0492         0          NaN      NaN      NaN    NaN        0          0                  0                  0       0       216000    32.768        0.3971                0.3798           1.0351
     4   g_R1         0.0492         0          NaN      NaN      NaN    NaN        0          0                  0                  0       0       167508    32.768        0.0242                0.0242           0.9473
     4   g_T4         2.3572       400       0.3758   0.3768   0.3707 0.1464      118       5900               1412               5886      10        43200    32.768        0.1900                0.1198          35.7830
     5   g_T1         0.5816       938       0.3697      NaN   0.3697 0.1393       30       1512                309               1502       0       108000    32.768        0.1350                0.0853           4.8849
     5 g_R0.5         0.0492         0          NaN      NaN      NaN    NaN        0          0                  0                  0       0        82188    32.768        0.0000                0.0000           0.6614
     5   g_T4         2.3562       400       0.3758   0.3779   0.3707 0.1464       99       6425               1120               6381       0        43200    32.768        0.1923                0.1202          22.2907
     5   g_R8         0.0492         0          NaN      NaN      NaN    NaN        0          0                  0                  0       0       214488    32.768        0.4249                0.4165           1.0411
     5   g_R1         0.0492         0          NaN      NaN      NaN    NaN        0          0                  0                  0       0       167832    32.768        0.0257                0.0257           0.8229
     5   g_R2         0.0492         0          NaN      NaN      NaN    NaN        0          0                  0                  0       0       216000    32.768        0.1017                0.0944           0.9956
     6   g_T4         2.3562       398       0.3768   0.3779   0.3727 0.1485      148      10005               2148               9967       0        42984    32.768        0.1927                0.1252          30.8915
     6   g_R2         0.0492         0          NaN      NaN      NaN    NaN        0          0                  0                  0       0       211464    32.768        0.1035                0.0969           0.9415
     6   g_R1         0.0492         0          NaN      NaN      NaN    NaN        0          0                  0                  0       0       174852    32.768        0.0270                0.0269           0.8789
     6   g_T1         0.5816       926       0.3717      NaN   0.3717 0.1372       38       3096                581               3072       0       107892    32.768        0.1322                0.0869           4.0679
     6 g_R0.5         0.0492         0          NaN      NaN      NaN    NaN        0          0                  0                  0       0        88452    32.768        0.0000                0.0000           0.6691
     6   g_R8         0.0492         0          NaN      NaN      NaN    NaN        0          0                  0                  0       0       215028    32.768        0.4219                0.4135           1.0233
     7 g_R0.5         0.0492         0          NaN      NaN      NaN    NaN        0          0                  0                  0       0        87912    32.768        0.0000                0.0000           0.6304
     7   g_T1         0.5827       919       0.3707      NaN   0.3707 0.1393       22       1332                198               1325       0       108000    32.768        0.1417                0.0913           4.2117
     7   g_R8         0.0492         0          NaN      NaN      NaN    NaN        0          0                  0                  0       0       215568    32.768        0.4306                0.4225           1.0063
     7   g_R1         0.0492         0          NaN      NaN      NaN    NaN        0          0                  0                  0       0       179172    32.768        0.0269                0.0269           0.8689
     7   g_R2         0.0492         0          NaN      NaN      NaN    NaN        0          0                  0                  0       0       216000    32.768        0.1052                0.0983           1.0266
     7   g_T4         2.3562       400       0.3717   0.3748   0.3656 0.1536       56       4076                694               4053       0        43200    32.768        0.2014                0.1311          27.2253
     8   g_R1         0.0492         0          NaN      NaN      NaN    NaN        0          0                  0                  0       0       175716    32.768        0.0282                0.0282           0.9243
     8   g_R2         0.0492         0          NaN      NaN      NaN    NaN        0          0                  0                  0       0       212436    32.768        0.1052                0.0986           0.9926
     8   g_T1         0.5827       926       0.3748      NaN   0.3748 0.1331       27       3316                678               3303       0       108000    32.768        0.1457                0.1001           4.7261
     8 g_R0.5         0.0492         0          NaN      NaN      NaN    NaN        0          0                  0                  0       0        84348    32.768        0.0000                0.0000           0.6566
     8   g_R8         0.0492         0          NaN      NaN      NaN    NaN        0          0                  0                  0       0       214380    32.768        0.4310                0.4225           1.0025
     8   g_T4         2.3572       395       0.3707   0.3748   0.3656 0.1556       50       3543                598               3514       0        42660    32.768        0.1768                0.1117          28.9567
     9   g_R2         0.0492         0          NaN      NaN      NaN    NaN        0          0                  0                  0       0       216000    32.768        0.1013                0.0942           0.9874
     9   g_R1         0.0492         0          NaN      NaN      NaN    NaN        0          0                  0                  0       0       172152    32.768        0.0280                0.0274           0.8245
     9   g_T4         2.3572       400       0.3717   0.3748   0.3656 0.1546       47       3152                674               3140       0        43200    32.768        0.1934                0.1215          24.7306
     9 g_R0.5         0.0492         0          NaN      NaN      NaN    NaN        0          0                  0                  0       0        83484    32.768        0.0000                0.0000           0.6584
     9   g_T1         0.5827       911       0.3738      NaN   0.3738 0.1352       43       3384                693               3368       0       108000    32.768        0.1470                0.0983           5.7931
     9   g_R8         0.0492         0          NaN      NaN      NaN    NaN        0          0                  0                  0       0       214920    32.768        0.4243                0.4163           1.1110
```

### P4 quantum q (pooled complete runs of both contexts inside sliced fg spans)

```
  cell  n_runs  q_pooled_ms  q_fg_ms  q_bg_ms   n_s   s_ms
g_R0.5       0          NaN      NaN      NaN     0    NaN
  g_R1       0          NaN      NaN      NaN     0    NaN
  g_R2       0          NaN      NaN      NaN     0    NaN
  g_R8       0          NaN      NaN      NaN     0    NaN
  g_T1    2170       0.3727      NaN   0.3727 11066 0.1382
  g_T4   26290       0.3738   0.3768   0.3676 27988 0.1516
```

- pooled over all cells: q = 0.374 ms from 28460 complete runs; registered range 0.5-0.9 ms; P4 DID NOT HOLD

### P5 switch gap s

- pooled s = 0.148 ms from 39054 transitions; registered range 0.2-0.3 ms; P5 DID NOT HOLD; negative-s transitions (runs overlapping in time): 1128

### P6 no concurrency

```
  cell  n_overlap  n_overlap_same_sm  n_overlap_diff_sm  n_ties  n_fg_blocks  n_untrusted_fg
g_R0.5          0                  0                  0       0       846828               0
  g_R1          0                  0                  0       0      1722384               0
  g_R2          0                  0                  0       0      2147796               0
  g_R8          0                  0                  0       0      2150496               0
  g_T1      24880               4635              24737       0      1079568               0
  g_T4      51091               9974              50802      10       429840               0
```

- fg blocks overlapping a bg block by more than 10 us: 75971 of 8376912 trusted blocks (untrusted excluded: 0); ties (<= 10 us): 10; P6 DID NOT HOLD

#### Concurrency rule (addendum 3 section B): the 3-blocks-per-SM control g_T4_3bpsm

```
 block  n_overlap  n_overlap_same_sm  n_overlap_diff_sm  n_ties  n_fg_blocks  n_untrusted_fg  preempt_frac  interval_s
     0       1404                288               1398       0        42444               0         0.219      10.299
     1       1080                135               1068       0        43200               0         0.211      11.158
     2       1080                153               1074       0        42660               0         0.224      10.163
     3       1620                231               1614       0        42660               0         0.187      11.836
     4       2052                348               2043       0        41580               0         0.214      10.427
     5       1944                327               1929       0        42552               0         0.199      11.218
     6        864                195                855       0        43200               0         0.204      11.242
     7       1729                355               1717       0        43200               0         0.211      10.972
     8       1944                327               1932       0        42876               0         0.207      10.972
     9       2268                258               2241       0        43200               0         0.229      10.362
```

- P6 failed in the main cells AND the control overlaps (15985 fg blocks; same-SM 2617, different-SM 15871): concurrency is REPORTED AS A FINDING.

### P7 mid-kernel preemption of bg blocks (block has a gap >= G_thr; mean over blocks)

```
  cell  preempt_frac  preempt_frac_with_fg
g_R0.5        0.0000                0.0000
  g_R1        0.0268                0.0267
  g_R2        0.1039                0.0971
  g_R8        0.4249                0.4153
  g_T1        0.1396                0.0905
  g_T4        0.1926                0.1226
```

- g_T4: 19.26% of recorded bg blocks preempted (registered: >= 1%); P7 HELD

### P8 arrival -> on-GPU start delay of the 0.1 ms fg (ms; the registered test is the p99; p50 and p90 added for context, review 2026-10-22 finding 5)

```
  cell  p50_ms  p90_ms  p99_ms
  g_R2  0.2712  0.4677  1.0056
  g_R8  0.2683  0.4833  1.0252
g_R0.5  0.2071  0.4093  0.6590
  g_R1  0.2104  0.4284  0.8802
```

- registered: p99 <= 0.4 ms for every m; P8 DID NOT HOLD

## g_bgalone: gaps with no foreground (other GPU contexts, reported baseline preemption rate; not a prediction)

```
 block            cell  g_thr_us  bg_blocks  blocks_with_gap_ge_gthr  fraction  gaps_logged  gaps_ge_gthr  gap_len_median_us  gap_len_max_us  novf_blocks
     0       g_bgalone   32.7680     265788                        0       0.0          302             0                NaN          21.504            0
     0 g_bgalone_3bpsm   32.3723     263304                        0       0.0           81             0                NaN          20.480            0
     1       g_bgalone   32.7680     266544                        0       0.0          326             0                NaN          21.504            0
     1 g_bgalone_3bpsm   32.3723     263412                        0       0.0           73             0                NaN          20.480            0
     2 g_bgalone_3bpsm   32.3723     263304                        0       0.0           69             0                NaN          20.480            0
     2       g_bgalone   32.7680     266652                        0       0.0          315             0                NaN          21.504            0
     3 g_bgalone_3bpsm   32.3723     263304                        0       0.0           80             0                NaN          20.480            0
     3       g_bgalone   32.7680     266544                        0       0.0          325             0                NaN          21.504            0
     4 g_bgalone_3bpsm   32.3723     263304                        0       0.0           73             0                NaN          20.480            0
     4       g_bgalone   32.7680     266652                        0       0.0          330             0                NaN          23.552            0
     5 g_bgalone_3bpsm   32.3723     263304                        0       0.0           68             0                NaN          20.480            0
     5       g_bgalone   32.7680     266652                        0       0.0          327             0                NaN          21.504            0
     6       g_bgalone   32.7680     266652                        0       0.0          334             0                NaN          21.504            0
     6 g_bgalone_3bpsm   32.3723     263304                        0       0.0           80             0                NaN          20.480            0
     7 g_bgalone_3bpsm   32.3723     263304                        0       0.0           69             0                NaN          20.480            0
     7       g_bgalone   32.7680     266544                        0       0.0          352             0                NaN          22.528            0
     8 g_bgalone_3bpsm   32.3723     263304                        0       0.0           65             0                NaN          20.480            0
     8       g_bgalone   32.7680     266652                        0       0.0          318             0                NaN          21.504            0
     9 g_bgalone_3bpsm   32.3723     263304                        0       0.0          124             0                NaN          20.480            0
     9       g_bgalone   32.7680     266652                        0       0.0          386             0                NaN          22.528            0
```
