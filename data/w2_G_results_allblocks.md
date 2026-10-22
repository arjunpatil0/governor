# Experiment G report

Source `C:\Users\arjun\governor\data\raw\w2_G\20261022T062433Z` | admin True | AC True | ambient 25.0 C | Armoury Performance | NVIDIA GeForce RTX 4070 Laptop GPU driver 616.92 | yaml e1df18ccd6898bd9 | dll 7768289069367275 | git 7cea2e69 | blocks 10 | cells 170
Addenda: experiments/w2_colocation_addendum_globaltimer_2026-10-22.md and ..._prerun_2026-10-22.md (and _witness_ if registered). Each prediction: held / did not hold, with the numbers.
Block set for gap, run, overlap and preemption analyses: ALL blocks (secondary view; blocks beyond three per SM show intra-SM arbitration gaps even with no other context).

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

- all-blocks view: the witness gate does not apply (secondary view, arbitration artefact present)
- gate (i): PASS; gate (ii) placement is reported per cell below (nominal / fallback / excluded launches)

## Timeline cells: coverage, trust and results per block (recorded-interval rule, addendum 2 section C)

Coverage and trust (fg_share = share of the cell's measured fg requests wholly inside the recorded interval; untrusted = blocks with gap-log overflow; gap_lost = gaps lost to a full global list):

```
 block   cell  n_fg_in_interval  n_bg_launches  interval_s  fg_share  bg_launches_dropped  n_untrusted_fg  n_untrusted_bg  gap_lost  fg_w_nominal  fg_w_fallback  fg_w_excluded  bg_w_nominal  bg_w_fallback  bg_w_excluded
     0   g_R2              1990           5116      10.978     1.000                    0               0               0         0             0              0              0             0              0              0
     0   g_R8              2000           1269      10.894     0.997                    0               0               0         0             0              0              0             0              0              0
     0   g_T1               997           4522      10.853     1.000                    0               0               0         0             0              0              0             0              0              0
     0   g_T4               399           4366      11.563     1.000                    0               0               0         0             0              0              0             0              0              0
     0 g_R0.5               812           7407       3.948     0.404                13265               0               0         0             0              0              0             0              0              0
     0   g_R1              1558           7407       7.905     0.783                 3046               0               0         0             0              0              0             0              0              0
     1   g_R1              1604           7407       7.921     0.795                 2868               0               0         0             0              0              0             0              0              0
     1   g_R2              2000           5342      11.402     0.995                    0               0               0         0             0              0              0             0              0              0
     1   g_R8              1998           1241      10.660     1.000                    0               0               0         0             0              0              0             0              0              0
     1   g_T4               400           4362      11.566     1.000                    0               0               0         0             0              0              0             0              0              0
     1 g_R0.5               781           7407       3.937     0.390                13368               0               0         0             0              0              0             0              0              0
     1   g_T1              1000           4498      10.858     0.973                    0               0               0         0             0              0              0             0              0              0
     2   g_R8              2000           1312      11.242     0.991                    0               0               0         0             0              0              0             0              0              0
     2   g_T1              1000           4692      11.218     0.983                    0               0               0         0             0              0              0             0              0              0
     2 g_R0.5               798           7407       3.942     0.406                13162               0               0         0             0              0              0             0              0              0
     2   g_T4               400           3230       9.315     0.980                    0               0               0         0             0              0              0             0              0              0
     2   g_R2              1979           5029      10.763     1.000                    0               0               0         0             0              0              0             0              0              0
     2   g_R1              1573           7407       7.907     0.803                 2836               0               0         0             0              0              0             0              0              0
     3   g_R2              1993           4874      10.447     1.000                    0               0               0         0             0              0              0             0              0              0
     3 g_R0.5               743           7407       3.927     0.372                13728               0               0         0             0              0              0             0              0              0
     3   g_T1              1000           4556      10.916     0.999                    0               0               0         0             0              0              0             0              0              0
     3   g_R1              1610           7407       7.921     0.801                 2600               0               0         0             0              0              0             0              0              0
     3   g_R8              1966           1246      10.692     1.000                    0               0               0         0             0              0              0             0              0              0
     3   g_T4               388           4181      11.089     1.000                    0               0               0         0             0              0              0             0              0              0
     4   g_R2              2000           5156      11.024     1.000                    0               0               0         0             0              0              0             0              0              0
     4 g_R0.5               760           7407       3.943     0.372                13945               0               0         0             0              0              0             0              0              0
     4   g_T1              1000           4676      11.198     0.983                    0               0               0         0             0              0              0             0              0              0
     4   g_R8              2000           1328      11.382     0.975                    0               0               0         0             0              0              0             0              0              0
     4   g_R1              1551           7407       7.902     0.776                 3024               0               0         0             0              0              0             0              0              0
     4   g_T4               400           4143      11.119     0.988                    0               0               0         0             0              0              0             0              0              0
     5   g_T1              1000           4823      11.498     0.983                    0               0               0         0             0              0              0             0              0              0
     5 g_R0.5               761           7407       3.932     0.379                14180               0               0         0             0              0              0             0              0              0
     5   g_T4               400           4053      10.924     0.993                    0               0               0         0             0              0              0             0              0              0
     5   g_R8              1986           1259      10.811     1.000                    0               0               0         0             0              0              0             0              0              0
     5   g_R1              1554           7407       7.904     0.788                 2985               0               0         0             0              0              0             0              0              0
     5   g_R2              2000           5175      11.067     0.990                    0               0               0         0             0              0              0             0              0              0
     6   g_T4               398           4051      10.890     1.000                    0               0               0         0             0              0              0             0              0              0
     6   g_R2              1958           5108      10.912     0.999                    0               0               0         0             0              0              0             0              0              0
     6   g_R1              1619           7407       7.918     0.812                 2783               0               0         0             0              0              0             0              0              0
     6   g_T1               999           4736      11.283     1.000                    0               0               0         0             0              0              0             0              0              0
     6 g_R0.5               819           7407       3.948     0.414                13015               0               0         0             0              0              0             0              0              0
     6   g_R8              1991           1302      11.155     0.999                    0               0               0         0             0              0              0             0              0              0
     7 g_R0.5               814           7407       3.948     0.406                12961               0               0         0             0              0              0             0              0              0
     7   g_T1              1000           4419      10.666     0.992                    0               0               0         0             0              0              0             0              0              0
     7   g_R8              1996           1309      11.213     1.000                    0               0               0         0             0              0              0             0              0              0
     7   g_R1              1659           7407       7.928     0.840                 2437               0               0         0             0              0              0             0              0              0
     7   g_R2              2000           5175      11.064     0.993                    0               0               0         0             0              0              0             0              0              0
     7   g_T4               400           3897      10.653     0.985                    0               0               0         0             0              0              0             0              0              0
     8   g_R1              1627           7407       7.924     0.812                 2726               0               0         0             0              0              0             0              0              0
     8   g_R2              1967           5099      10.900     1.000                    0               0               0         0             0              0              0             0              0              0
     8   g_T1              1000           4443      10.694     0.996                    0               0               0         0             0              0              0             0              0              0
     8 g_R0.5               781           7407       3.936     0.397                13266               0               0         0             0              0              0             0              0              0
     8   g_R8              1985           1290      11.056     1.000                    0               0               0         0             0              0              0             0              0              0
     8   g_T4               395           4366      11.534     1.000                    0               0               0         0             0              0              0             0              0              0
     9   g_R2              2000           5164      11.042     0.994                    0               0               0         0             0              0              0             0              0              0
     9   g_R1              1594           7407       7.930     0.784                 2815               0               0         0             0              0              0             0              0              0
     9   g_T4               400           4101      11.084     0.980                    0               0               0         0             0              0              0             0              0              0
     9 g_R0.5               773           7407       3.937     0.387                14089               0               0         0             0              0              0             0              0              0
     9   g_T1              1000           4352      10.518     0.989                    0               0               0         0             0              0              0             0              0              0
     9   g_R8              1990           1242      10.666     0.999                    0               0               0         0             0              0              0             0              0              0
```

Per block results:

```
 block   cell  alone_span_ms  n_sliced  q_pooled_ms  q_fg_ms  q_bg_ms   s_ms  n_neg_s  n_overlap  n_overlap_same_sm  n_overlap_diff_sm  n_ties  n_fg_blocks  g_thr_us  preempt_frac  preempt_frac_with_fg  p8_delay_p99_ms
     0   g_R2         0.0819         0          NaN      NaN      NaN    NaN        0          0                  0                  0       0       429840   55.6194        0.5535                0.1687           1.0303
     0   g_R8         0.0819         0          NaN      NaN      NaN    NaN        0        216                 18                216       0       432000   55.6194        0.7201                0.5634           1.0101
     0   g_T1         0.9943       997       0.3850    0.385   0.3860 0.1137      155      15840               3114              15764       8       215352   55.6194        0.5690                0.1665           5.0706
     0   g_T4         4.0325       399       0.3809    0.382   0.3799 0.1208      181      14791               3076              14713      45        86184   55.6194        0.5881                0.1827          32.1811
     0 g_R0.5         0.0819         0          NaN      NaN      NaN    NaN        0          0                  0                  0       0       175392   55.6194        0.5000                0.0270           0.6679
     0   g_R1         0.0819         0          NaN      NaN      NaN    NaN        0          0                  0                  0       0       336528   55.6194        0.5130                0.0756           0.8686
     1   g_R1         0.0819         0          NaN      NaN      NaN    NaN        0          0                  0                  0       0       346464   55.6409        0.5139                0.0795           0.9118
     1   g_R2         0.0819         0          NaN      NaN      NaN    NaN        0        648                162                642       0       432000   55.6409        0.5504                0.1614           0.9752
     1   g_R8         0.0819         0          NaN      NaN      NaN    NaN        0          0                  0                  0       0       431568   55.6409        0.7125                0.5450           0.9855
     1   g_T4         4.0325       400       0.3809    0.382   0.3809 0.1198      190      16879               3380              16761      20        86400   55.6409        0.5889                0.1825          25.6981
     1 g_R0.5         0.0819         0          NaN      NaN      NaN    NaN        0          0                  0                  0       0       168696   55.6409        0.5000                0.0258           0.6275
     1   g_T1         0.9933      1000       0.3820    0.382   0.3830 0.1178      236      20808               4548              20720       0       216000   55.6409        0.5706                0.1649           4.8418
     2   g_R8         0.0819         0          NaN      NaN      NaN    NaN        0          0                  0                  0       0       432000   55.4038        0.7069                0.5365           0.9985
     2   g_T1         0.9943      1000       0.3850    0.385   0.3850 0.1147      162      16812               3434              16742      29       216000   55.4038        0.5687                0.1626           4.7449
     2 g_R0.5         0.0819         0          NaN      NaN      NaN    NaN        0          0                  0                  0       0       172368   55.4038        0.5000                0.0272           0.6866
     2   g_T4         4.0325       400       0.3809    0.382   0.3799 0.1208      166      13569               2778              13500       5        86400   55.4038        0.6219                0.2466          24.1333
     2   g_R2         0.0819         0          NaN      NaN      NaN    NaN        0          0                  0                  0       0       427464   55.4038        0.5530                0.1740           0.9953
     2   g_R1         0.0819         0          NaN      NaN      NaN    NaN        0          0                  0                  0       0       339768   55.4038        0.5135                0.0770           0.8703
     3   g_R2         0.0819         0          NaN      NaN      NaN    NaN        0        432                 72                432       0       430488   55.6409        0.5517                0.1716           1.0932
     3 g_R0.5         0.0819         0          NaN      NaN      NaN    NaN        0          0                  0                  0       0       160488   55.6409        0.5000                0.0250           0.6540
     3   g_T1         0.9933      1000       0.3850    0.385   0.3860 0.1137      173      17860               2926              17726      11       216000   55.6409        0.5686                0.1622           4.6470
     3   g_R1         0.0819         0          NaN      NaN      NaN    NaN        0          0                  0                  0       0       347760   55.6409        0.5138                0.0790           0.8516
     3   g_R8         0.0819         0          NaN      NaN      NaN    NaN        0        648                102                636       0       424656   55.6409        0.7199                0.5548           1.0271
     3   g_T4         4.0325       388       0.3840    0.384   0.3840 0.1178      304      23883               4282              23741       0        83808   55.6409        0.5909                0.1870          26.0062
     4   g_R2         0.0819         0          NaN      NaN      NaN    NaN        0          0                  0                  0       0       432000   55.6194        0.5522                0.1677           1.0033
     4 g_R0.5         0.0819         0          NaN      NaN      NaN    NaN        0          0                  0                  0       0       164160   55.6194        0.5000                0.0262           0.6471
     4   g_T1         0.9943      1000       0.3830    0.383   0.3830 0.1167      207      17676               3344              17576       0       216000   55.6194        0.5704                0.1659           5.4105
     4   g_R8         0.0819         0          NaN      NaN      NaN    NaN        0        216                102                216       0       432000   55.6194        0.6985                0.5146           1.0351
     4   g_R1         0.0819         0          NaN      NaN      NaN    NaN        0          0                  0                  0       0       335016   55.6194        0.5121                0.0740           0.9473
     4   g_T4         4.0325       400       0.3840    0.385   0.3830 0.1178      275      22338               4849              22250      10        86400   55.6194        0.5950                0.1926          35.7830
     5   g_T1         0.9933      1000       0.3830    0.383   0.3820 0.1178      142      12960               2024              12876       0       216000   55.6194        0.5675                0.1603           4.8849
     5 g_R0.5         0.0819         0          NaN      NaN      NaN    NaN        0          0                  0                  0       0       164376   55.6194        0.5000                0.0251           0.6614
     5   g_T4         4.0315       400       0.3850    0.385   0.3840 0.1178      294      23863               4641              23732       2        86400   55.6194        0.5961                0.1963          22.2907
     5   g_R8         0.0819         0          NaN      NaN      NaN    NaN        0        216                 36                216       0       428976   55.6194        0.7125                0.5451           1.0411
     5   g_R1         0.0819         0          NaN      NaN      NaN    NaN        0          0                  0                  0       0       335664   55.6194        0.5129                0.0760           0.8229
     5   g_R2         0.0819         0          NaN      NaN      NaN    NaN        0        432                 72                432       0       432000   55.6194        0.5509                0.1651           0.9956
     6   g_T4         4.0315       398       0.3850    0.385   0.3850 0.1172      368      29511               6145              29381       0        85968   55.6194        0.5964                0.1979          30.8915
     6   g_R2         0.0819         0          NaN      NaN      NaN    NaN        0          0                  0                  0       0       422928   55.6194        0.5517                0.1687           0.9415
     6   g_R1         0.0819         0          NaN      NaN      NaN    NaN        0          0                  0                  0       0       349704   55.6194        0.5135                0.0783           0.8789
     6   g_T1         0.9933       999       0.3840    0.384   0.3840 0.1157      174      17569               3448              17461       5       215784   55.6194        0.5661                0.1598           4.0679
     6 g_R0.5         0.0819         0          NaN      NaN      NaN    NaN        0          0                  0                  0       0       176904   55.6194        0.5000                0.0284           0.6691
     6   g_R8         0.0819         0          NaN      NaN      NaN    NaN        0          0                  0                  0       0       430056   55.6194        0.7110                0.5467           1.0233
     7 g_R0.5         0.0819         0          NaN      NaN      NaN    NaN        0          0                  0                  0       0       175824   55.6194        0.5000                0.0275           0.6304
     7   g_T1         0.9943      1000       0.3820    0.382   0.3830 0.1167      197      16488               2894              16404       7       216000   55.6194        0.5708                0.1680           4.2117
     7   g_R8         0.0819         0          NaN      NaN      NaN    NaN        0        216                 72                216       0       431136   55.6194        0.7153                0.5357           1.0063
     7   g_R1         0.0819         0          NaN      NaN      NaN    NaN        0          0                  0                  0       0       358344   55.6194        0.5135                0.0789           0.8689
     7   g_R2         0.0819         0          NaN      NaN      NaN    NaN        0          0                  0                  0       0       432000   55.6194        0.5526                0.1661           1.0266
     7   g_T4         4.0315       400       0.3809    0.382   0.3799 0.1198      183      16219               3196              16132      33        86400   55.6194        0.6007                0.2042          27.2253
     8   g_R1         0.0819         0          NaN      NaN      NaN    NaN        0          0                  0                  0       0       351432   55.6194        0.5141                0.0814           0.9243
     8   g_R2         0.0819         0          NaN      NaN      NaN    NaN        0        432                108                432       0       424872   55.6194        0.5526                0.1685           0.9926
     8   g_T1         0.9943      1000       0.3850    0.385   0.3850 0.1147      161      17573               3496              17503      34       216000   55.6194        0.5728                0.1706           4.7261
     8 g_R0.5         0.0819         0          NaN      NaN      NaN    NaN        0          0                  0                  0       0       168696   55.6194        0.5000                0.0259           0.6566
     8   g_R8         0.0819         0          NaN      NaN      NaN    NaN        0          0                  0                  0       0       428760   55.6194        0.7155                0.5552           1.0025
     8   g_T4         4.0325       395       0.3809    0.382   0.3799 0.1198      161      14706               2724              14617       0        85320   55.6194        0.5884                0.1803          28.9567
     9   g_R2         0.0819         0          NaN      NaN      NaN    NaN        0        216                 48                216       0       432000   55.6194        0.5507                0.1634           0.9874
     9   g_R1         0.0819         0          NaN      NaN      NaN    NaN        0          0                  0                  0       0       344304   55.6194        0.5140                0.0789           0.8245
     9   g_T4         4.0325       400       0.3809    0.382   0.3799 0.1208      159      13415               2781              13360      31        86400   55.6194        0.5967                0.1942          24.7306
     9 g_R0.5         0.0819         0          NaN      NaN      NaN    NaN        0          0                  0                  0       0       166968   55.6194        0.5000                0.0258           0.6584
     9   g_T1         0.9943      1000       0.3850    0.385   0.3850 0.1147      203      20304               3784              20198      44       216000   55.6194        0.5735                0.1705           5.7931
     9   g_R8         0.0819         0          NaN      NaN      NaN    NaN        0        216                  6                210       0       429840   55.6194        0.7122                0.5440           1.1110
```

### P4 quantum q (pooled complete runs of both contexts inside sliced fg spans)

```
  cell  n_runs  q_pooled_ms  q_fg_ms  q_bg_ms   n_s   s_ms
g_R0.5       0          NaN      NaN      NaN     0    NaN
  g_R1       0          NaN      NaN      NaN     0    NaN
  g_R2       0          NaN      NaN      NaN     0    NaN
  g_R8       0          NaN      NaN      NaN     0    NaN
  g_T1   20496        0.384    0.384    0.384 37138 0.1157
  g_T4   59814        0.382    0.383    0.382 72565 0.1188
```

- pooled over all cells: q = 0.383 ms from 80310 complete runs; registered range 0.5-0.9 ms; P4 DID NOT HOLD

### P5 switch gap s

- pooled s = 0.118 ms from 109703 transitions; registered range 0.2-0.3 ms; P5 DID NOT HOLD; negative-s transitions (runs overlapping in time): 4091

### P6 no concurrency

```
  cell  n_overlap  n_overlap_same_sm  n_overlap_diff_sm  n_ties  n_fg_blocks  n_untrusted_fg
g_R0.5          0                  0                  0       0      1693872               0
  g_R1          0                  0                  0       0      3444984               0
  g_R2       2160                462               2154       0      4295592               0
  g_R8       1728                336               1710       0      4300992               0
  g_T1     173890              33012             172970     138      2159136               0
  g_T4     189174              37852             188187     146       859680               0
```

- fg blocks overlapping a bg block by more than 10 us: 366952 of 16754256 trusted blocks (untrusted excluded: 0); ties (<= 10 us): 284; P6 DID NOT HOLD

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
g_R0.5        0.5000                0.0264
  g_R1        0.5134                0.0778
  g_R2        0.5519                0.1675
  g_R8        0.7124                0.5441
  g_T1        0.5698                0.1651
  g_T4        0.5963                0.1964
```

- g_T4: 59.63% of recorded bg blocks preempted (registered: >= 1%); P7 HELD

### P8 arrival -> on-GPU start delay of the 0.1 ms fg (p99, ms)

```
  cell  p99_ms
  g_R2  1.0056
  g_R8  1.0252
g_R0.5  0.6590
  g_R1  0.8802
```

- registered: p99 <= 0.4 ms for every m; P8 DID NOT HOLD

## g_bgalone: gaps with no foreground (other GPU contexts, reported baseline preemption rate; not a prediction)

```
 block            cell  g_thr_us  bg_blocks  blocks_with_gap_ge_gthr  fraction  gaps_logged  gaps_ge_gthr  gap_len_median_us  gap_len_max_us  novf_blocks
     0       g_bgalone   55.6194     531576                   265788       0.5       678774        621742            345.088         474.112            0
     0 g_bgalone_3bpsm   32.3723     263304                        0       0.0           81             0                NaN          20.480            0
     1       g_bgalone   55.6409     533088                   266544       0.5       680899        623533            345.088         474.112            0
     1 g_bgalone_3bpsm   32.3723     263412                        0       0.0           73             0                NaN          20.480            0
     2 g_bgalone_3bpsm   32.3723     263304                        0       0.0           69             0                NaN          20.480            0
     2       g_bgalone   55.4038     533304                   266652       0.5       680873        623763            345.088         474.112            0
     3 g_bgalone_3bpsm   32.3723     263304                        0       0.0           80             0                NaN          20.480            0
     3       g_bgalone   55.6409     533088                   266544       0.5       680818        623469            345.088         474.112            0
     4 g_bgalone_3bpsm   32.3723     263304                        0       0.0           73             0                NaN          20.480            0
     4       g_bgalone   55.6194     533304                   266652       0.5       680910        623685            345.088         474.112            0
     5 g_bgalone_3bpsm   32.3723     263304                        0       0.0           68             0                NaN          20.480            0
     5       g_bgalone   55.6194     533304                   266652       0.5       681380        623803            345.088         474.112            0
     6       g_bgalone   55.6194     533304                   266652       0.5       681012        623750            345.088         474.112            0
     6 g_bgalone_3bpsm   32.3723     263304                        0       0.0           80             0                NaN          20.480            0
     7 g_bgalone_3bpsm   32.3723     263304                        0       0.0           69             0                NaN          20.480            0
     7       g_bgalone   55.6194     533088                   266544       0.5       680690        623462            345.088         474.112            0
     8 g_bgalone_3bpsm   32.3723     263304                        0       0.0           65             0                NaN          20.480            0
     8       g_bgalone   55.6194     533304                   266652       0.5       681011        623669            345.088         474.112            0
     9 g_bgalone_3bpsm   32.3723     263304                        0       0.0          124             0                NaN          20.480            0
     9       g_bgalone   55.6194     533304                   266652       0.5       681058        623831            345.088         474.112            0
```
