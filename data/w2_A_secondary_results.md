# W2 Experiment A secondary: preemption characterisation (descriptive; motivated by the pilot, journal 0011) | REGISTERED ANALYSIS (all cells)

Source: `data\raw\w2_A2\20261021T175022Z` | run 20261021T175022Z | admin True | AC True | ambient 25.0 C | NVIDIA GeForce RTX 4070 Laptop GPU | driver 616.92 | yaml e1df18ccd6898bd9 | dll aa73f2b11a6ccb41 | git 7219e0fe
HAGS: DriverSupportState:Stable Enabled:True. Execution mode: CUDA native kernels via w2_kernels.dll (no CPU fallback).

## SA1 phase independence (slope of fg latency on arrival phase, ms/ms; -1 = waits out the slice, 0 = independent)

- pooled (m in 2, 4, 8): slope -0.007, 90% CI [-0.007, -0.006] -> **phase-independent**
- m = 2 ms: slope -0.051, CI [-0.055, -0.048] -> phase-independent
- m = 4 ms: slope -0.020, CI [-0.023, -0.018] -> phase-independent
- m = 8 ms: slope -0.009, CI [-0.010, -0.007] -> phase-independent

## SA2 slice stretch = s0 + k * fg service time

- s0 (constant switch cost) = 0.298 ms, 90% CI [0.295, 0.300]; k = 0.395, 90% CI [0.391, 0.399] (100 cell-blocks)

## SA3 priority control (fg HIGH minus NORMAL, observed wait, paired by block index across the two runs; no decision rule)

 m_ms  cv    median       min      max  count
    2 0.0 -0.005244 -0.013219 0.005079     10
    2 1.0  0.003937 -0.006517 0.017450     10
    8 0.0 -0.002845 -0.020261 0.012983     10
    8 1.0 -0.004874 -0.022118 0.006880     10

## SA4 foreground size and duty cycle (medians over blocks; slowdown = latency / the fg-alone latency of the same size)

       cell_id  fg_ms  m_ms  duty  lat_mean_ms  lat_p99_ms  frac_completed  fg_gpu_p50_ms   slowdown  overloaded
 sa4_fg1_alone    1.0     0  0.00     1.118491    2.031159        1.000000       0.989184   1.000000       False
    sa4_fg1_m2    1.0     2  1.00     2.966142    7.107279        1.000000       2.201088   2.651914       False
    sa4_fg1_m8    1.0     8  1.00     3.044974    7.294157        1.000000       2.211328   2.722394       False
 sa4_fg4_alone    4.0     0  0.00     4.482354    8.432687        1.000000       3.986432   1.000000       False
duty_fg4_d0.25    4.0     2  0.25     6.098348   12.157976        1.000000       4.562944   1.360524       False
 duty_fg4_d0.5    4.0     2  0.50     7.506263   15.346352        1.000000       6.705664   1.674625       False
duty_fg4_d0.75    4.0     2  0.75     9.540400   20.899464        1.000000       7.351808   2.128435       False
    sa4_fg4_m2    4.0     2  1.00    13.061728   33.656803        1.000000       9.678080   2.914033       False
    sa4_fg4_m8    4.0     8  1.00    13.826953   34.680762        1.000000      10.055424   3.084752       False
 sa4_fg9_alone    9.0     0  0.00    12.184387   12.706742        1.000000      12.101632   1.000000       False
duty_fg9_d0.25    9.0     2  0.25    14.238134   15.618118        1.000000      15.090432   1.168556       False
 duty_fg9_d0.5    9.0     2  0.50   358.022078  592.878191        1.000000      17.497856  29.383676        True
duty_fg9_d0.75    9.0     2  0.75  2221.450237 3278.459987        0.770000      21.939199 182.319409        True
    sa4_fg9_m2    9.0     2  1.00  4228.074992 5595.820332        0.537500      28.476417 347.007609        True
    sa4_fg9_m8    9.0     8  1.00  4689.709939 6079.143088        0.489167      12.119552 384.895025        True

Cells with frac_completed < 0.99 or slowdown > 10 are OVERLOADED (a backlog builds up; a completed fraction of 1.0 can still hide a long queue): their latency and slowdown are artefacts of the window length, not service times.
Reference for 4 and 9 ms foreground: equal sharing predicts slowdown ~ 1 + duty (rough; descriptive only).

## EXPLORATORY / POST-HOC: capped-wait model (addendum experiments/w2_colocation_addendum_capped_wait_2026-10-21.md; changes no decision rule)
Model: wait = offset + min(time-to-slice-end, tau). A's estimate from constant-slice medians: tau = 0.308 ms (least squares, six points, no CI).
CAVEAT: the registered SA1 cells below are A's own cells, the same data that suggested tau; this is a re-description of that data at request level, not an independent test. The A2 high-priority cells are a different condition (priority), shown for comparison only.

- A SA1 cells (normal priority; c=0, m in 2,4,8): n = 59985 requests; fitted tau = 0.260 ms, 90% block-bootstrap CI [0.260, 0.270]; offset = 0.041 ms
    - m = 2 ms: tau = 0.260 [0.250, 0.270], offset 0.043
    - m = 4 ms: tau = 0.270 [0.250, 0.280], offset 0.031
    - m = 8 ms: tau = 0.270 [0.260, 0.280], offset 0.030

  Binned curve (A SA1 cells (normal priority; c=0, m in 2,4,8)); lo/hi = time-to-slice-end bin in ms:

  lo   hi    n  mean_wait_ms
0.00 0.05  775      0.068396
0.05 0.10  797      0.122280
0.10 0.15  839      0.167806
0.15 0.20  779      0.207650
0.20 0.25  758      0.258501
0.25 0.30  740      0.293129
0.30 0.35  549      0.338332
0.35 0.40  185      0.437347
0.40 0.45   71      0.455905
0.45 0.50  125      0.288318
0.50 0.55  178      0.294491
0.55 0.60  327      0.192792
0.60 0.65  599      0.154102
0.65 0.70  817      0.163876
0.70 0.75  805      0.202829
0.75 0.80  830      0.264944
0.80 0.85  809      0.294092
0.85 0.90  870      0.322573
0.90 0.95  870      0.337262
0.95 1.00  800      0.353329
1.00 1.50 7607      0.276447
1.50 2.00 8175      0.284388
2.00 2.50 6908      0.328558
2.50 3.00 3933      0.318606
3.00 3.50 3470      0.300912
3.50 4.00 3575      0.296056
4.00 4.50 3109      0.321668
4.50 5.00 1700      0.339773
5.00 5.50 1249      0.314214
5.50 6.00 1247      0.300353
6.00 6.50 1221      0.318836
6.50 7.00 1152      0.306295
7.00 7.50 1175      0.333765
7.50 8.00 1161      0.303963
8.00 8.50 1051      0.323727
8.50 9.00  541      0.364339
9.00 9.50  167      0.426453

- A2 sa3_high cells (HIGH priority; c=0, m in 2,8): n = 39890 requests; fitted tau = 0.260 ms, 90% block-bootstrap CI [0.260, 0.270]; offset = 0.038 ms
    - m = 2 ms: tau = 0.260 [0.260, 0.270], offset 0.039
    - m = 8 ms: tau = 0.280 [0.260, 0.290], offset 0.018

  Binned curve (A2 sa3_high cells (HIGH priority; c=0, m in 2,8)); lo/hi = time-to-slice-end bin in ms:

  lo   hi    n  mean_wait_ms
0.00 0.05  550      0.068342
0.05 0.10  595      0.117204
0.10 0.15  573      0.154721
0.15 0.20  556      0.208696
0.20 0.25  558      0.239023
0.25 0.30  476      0.309598
0.30 0.35  507      0.338789
0.35 0.40  141      0.370786
0.40 0.45   44      0.475494
0.45 0.50  100      0.288710
0.50 0.55  144      0.302174
0.55 0.60  157      0.274697
0.60 0.65  406      0.163495
0.65 0.70  583      0.156878
0.70 0.75  593      0.207518
0.75 0.80  602      0.243249
0.80 0.85  605      0.291142
0.85 0.90  610      0.317781
0.90 0.95  601      0.307841
0.95 1.00  546      0.363334
1.00 1.50 5363      0.278663
1.50 2.00 5803      0.276933
2.00 2.50 4641      0.340018
2.50 3.00 1635      0.339531
3.00 3.50 1201      0.289302
3.50 4.00 1190      0.295064
4.00 4.50 1156      0.290471
4.50 5.00 1114      0.311657
5.00 5.50 1204      0.292553
5.50 6.00 1206      0.308776
6.00 6.50 1189      0.312944
6.50 7.00 1113      0.303857
7.00 7.50 1173      0.313941
7.50 8.00 1150      0.309405
8.00 8.50 1053      0.316864
8.50 9.00  564      0.354181
9.00 9.50  157      0.398098


## Stall check (journal 0023): first three cells after each console-QuickEdit stall vs the same cell in the other 9 blocks; rank 0 = below all 9 others

                   cell  after_stall  temp_pre_c  temp_pre_c_others_median  lat_mean_ms  lat_mean_ms_others_median  lat_mean_ms_rank_of_9  lat_p99_ms  lat_p99_ms_others_median  frac_completed  power_counter_w  power_counter_w_others_median  power_counter_w_rank_of_9  sm_clock_med  mem_clock_med
  b07_08_duty_fg9_d0.25            0          64                      64.0    14.241144                  14.235252                      6   15.771042                 15.615927        1.000000        40.995826                      44.077262                          0        1800.0         8001.0
      b07_09_sa4_fg4_m2            1          64                      58.0    12.830624                  13.132273                      2   33.535314                 33.778292        1.000000        48.832540                      52.107019                          1        1800.0         8001.0
  b07_10_duty_fg4_d0.25            2          64                      64.0     5.987772                   6.105797                      2   11.349437                 12.398845        1.000000        27.721767                      29.703744                          0        1800.0         8001.0
b08_16_sa3_high_m2_c1.0            0          64                      58.0     0.441409                   0.437834                      7    1.152203                  1.134207        1.000000        48.939588                      52.851203                          0        1800.0         8001.0
      b08_17_sa4_fg4_m2            1          64                      58.0    13.133077                  12.991183                      6   33.830095                 33.535314        1.000000        48.059332                      52.107019                          0        1800.0         8001.0
      b08_18_sa4_fg9_m2            2          64                      63.0  4239.650860                4225.202825                      6 5599.605411               5594.668829        0.536667        43.529649                      45.822871                          0        1800.0         8001.0


## Flags (cells stay in the data): 31 of 190

 block          cell_id                                         flags
     0   duty_fg9_d0.75                            fg_incomplete:0.77
     0       sa4_fg9_m8                            fg_incomplete:0.49
     0       sa4_fg9_m2                            fg_incomplete:0.54
     1       sa4_fg9_m8                            fg_incomplete:0.49
     1       sa4_fg9_m2                            fg_incomplete:0.53
     1   duty_fg9_d0.75                            fg_incomplete:0.77
     2       sa4_fg9_m2                            fg_incomplete:0.54
     2   duty_fg9_d0.75                            fg_incomplete:0.77
     2       sa4_fg9_m8                            fg_incomplete:0.49
     3       sa4_fg9_m2                            fg_incomplete:0.54
     3   duty_fg9_d0.75                            fg_incomplete:0.77
     3       sa4_fg9_m8                            fg_incomplete:0.49
     4       sa4_fg9_m8                            fg_incomplete:0.49
     4       sa4_fg9_m2 mem_clock_left_target:7001;fg_incomplete:0.54
     4   duty_fg9_d0.75                            fg_incomplete:0.77
     4 sa3_high_m2_c1.0                    mem_clock_left_target:7001
     5       sa4_fg9_m8                            fg_incomplete:0.48
     5       sa4_fg9_m2                            fg_incomplete:0.53
     5   duty_fg9_d0.75                            fg_incomplete:0.77
     6   duty_fg9_d0.75                            fg_incomplete:0.77
     6       sa4_fg9_m2                            fg_incomplete:0.54
     6       sa4_fg9_m8                            fg_incomplete:0.49
     7   duty_fg9_d0.75                            fg_incomplete:0.77
     7       sa4_fg9_m8                            fg_incomplete:0.49
     7       sa4_fg9_m2                            fg_incomplete:0.53
     8   duty_fg9_d0.75                            fg_incomplete:0.77
     8       sa4_fg9_m8                            fg_incomplete:0.49
     8       sa4_fg9_m2                            fg_incomplete:0.54
     9   duty_fg9_d0.75                            fg_incomplete:0.77
     9       sa4_fg9_m8                            fg_incomplete:0.49
     9       sa4_fg9_m2                            fg_incomplete:0.54

## Incident flags (sidecar incident_flags.csv; analysis/a2_incident_flags.py; journal 0023)

               cell_dir                        flag                                                     detail
   b04_14_sa4_fg1_alone user_activity_contamination span overlaps reported Chrome window 18:22:00-18:24:59 UTC
b04_15_sa3_high_m2_c0.0 user_activity_contamination span overlaps reported Chrome window 18:22:00-18:24:59 UTC
b04_16_sa3_high_m2_c1.0 user_activity_contamination span overlaps reported Chrome window 18:22:00-18:24:59 UTC
      b04_17_sa4_fg1_m8 user_activity_contamination span overlaps reported Chrome window 18:22:00-18:24:59 UTC
   b04_18_sa4_fg4_alone user_activity_contamination span overlaps reported Chrome window 18:22:00-18:24:59 UTC
      b05_00_sa4_fg1_m2 user_activity_contamination span overlaps reported Chrome window 18:22:00-18:24:59 UTC
      b05_01_sa4_fg9_m8 user_activity_contamination span overlaps reported Chrome window 18:22:00-18:24:59 UTC
      b05_02_sa4_fg9_m2 user_activity_contamination span overlaps reported Chrome window 18:22:00-18:24:59 UTC
   b05_03_sa4_fg1_alone user_activity_contamination span overlaps reported Chrome window 18:22:00-18:24:59 UTC
  b07_08_duty_fg9_d0.25       post_stall_first_cell                 idle gap 1381 s after b07_07_sa4_fg4_alone
b08_16_sa3_high_m2_c1.0       post_stall_first_cell                     idle gap 584 s after b08_15_sa4_fg1_m2

---

# W2 Experiment A secondary: preemption characterisation (descriptive; motivated by the pilot, journal 0011) | SENSITIVITY: excluding 9 cells flagged user_activity_contamination (registered rules unchanged)

Source: `data\raw\w2_A2\20261021T175022Z` | run 20261021T175022Z | admin True | AC True | ambient 25.0 C | NVIDIA GeForce RTX 4070 Laptop GPU | driver 616.92 | yaml e1df18ccd6898bd9 | dll aa73f2b11a6ccb41 | git 7219e0fe
HAGS: DriverSupportState:Stable Enabled:True. Execution mode: CUDA native kernels via w2_kernels.dll (no CPU fallback).

## SA1 phase independence (slope of fg latency on arrival phase, ms/ms; -1 = waits out the slice, 0 = independent)

- pooled (m in 2, 4, 8): slope -0.007, 90% CI [-0.007, -0.006] -> **phase-independent**
- m = 2 ms: slope -0.051, CI [-0.055, -0.048] -> phase-independent
- m = 4 ms: slope -0.020, CI [-0.023, -0.018] -> phase-independent
- m = 8 ms: slope -0.009, CI [-0.010, -0.007] -> phase-independent

## SA2 slice stretch = s0 + k * fg service time

- s0 (constant switch cost) = 0.291 ms, 90% CI [0.281, 0.299]; k = 0.395, 90% CI [0.391, 0.399] (98 cell-blocks)

## SA3 priority control (fg HIGH minus NORMAL, observed wait, paired by block index across the two runs; no decision rule)

 m_ms  cv    median       min      max  count
    2 0.0 -0.005480 -0.013219 0.003011      9
    2 1.0  0.003795 -0.006517 0.010581      9
    8 0.0 -0.002845 -0.020261 0.012983     10
    8 1.0 -0.004874 -0.022118 0.006880     10

## SA4 foreground size and duty cycle (medians over blocks; slowdown = latency / the fg-alone latency of the same size)

       cell_id  fg_ms  m_ms  duty  lat_mean_ms  lat_p99_ms  frac_completed  fg_gpu_p50_ms   slowdown  overloaded
 sa4_fg1_alone    1.0     0  0.00     1.113399    2.018448        1.000000       0.989184   1.000000       False
    sa4_fg1_m2    1.0     2  1.00     2.965520    7.037959        1.000000       2.201600   2.663485       False
    sa4_fg1_m8    1.0     8  1.00     3.039471    7.191732        1.000000       2.211840   2.729904       False
 sa4_fg4_alone    4.0     0  0.00     4.478846    8.659240        1.000000       3.986432   1.000000       False
duty_fg4_d0.25    4.0     2  0.25     6.098348   12.157976        1.000000       4.562944   1.361589       False
 duty_fg4_d0.5    4.0     2  0.50     7.506263   15.346352        1.000000       6.705664   1.675937       False
duty_fg4_d0.75    4.0     2  0.75     9.540400   20.899464        1.000000       7.351808   2.130102       False
    sa4_fg4_m2    4.0     2  1.00    13.061728   33.656803        1.000000       9.678080   2.916316       False
    sa4_fg4_m8    4.0     8  1.00    13.826953   34.680762        1.000000      10.055424   3.087169       False
 sa4_fg9_alone    9.0     0  0.00    12.184387   12.706742        1.000000      12.101632   1.000000       False
duty_fg9_d0.25    9.0     2  0.25    14.238134   15.618118        1.000000      15.090432   1.168556       False
 duty_fg9_d0.5    9.0     2  0.50   358.022078  592.878191        1.000000      17.497856  29.383676        True
duty_fg9_d0.75    9.0     2  0.75  2221.450237 3278.459987        0.770000      21.939199 182.319409        True
    sa4_fg9_m2    9.0     2  1.00  4225.202825 5594.668829        0.538333      28.473345 346.771883        True
    sa4_fg9_m8    9.0     8  1.00  4686.114828 6076.430810        0.490000      12.119552 384.599967        True

Cells with frac_completed < 0.99 or slowdown > 10 are OVERLOADED (a backlog builds up; a completed fraction of 1.0 can still hide a long queue): their latency and slowdown are artefacts of the window length, not service times.
Reference for 4 and 9 ms foreground: equal sharing predicts slowdown ~ 1 + duty (rough; descriptive only).

## EXPLORATORY / POST-HOC: capped-wait model (addendum experiments/w2_colocation_addendum_capped_wait_2026-10-21.md; changes no decision rule)
Model: wait = offset + min(time-to-slice-end, tau). A's estimate from constant-slice medians: tau = 0.308 ms (least squares, six points, no CI).
CAVEAT: the registered SA1 cells below are A's own cells, the same data that suggested tau; this is a re-description of that data at request level, not an independent test. The A2 high-priority cells are a different condition (priority), shown for comparison only.

- A SA1 cells (normal priority; c=0, m in 2,4,8): n = 59985 requests; fitted tau = 0.260 ms, 90% block-bootstrap CI [0.260, 0.270]; offset = 0.041 ms
    - m = 2 ms: tau = 0.260 [0.250, 0.270], offset 0.043
    - m = 4 ms: tau = 0.270 [0.250, 0.280], offset 0.031
    - m = 8 ms: tau = 0.270 [0.260, 0.280], offset 0.030

  Binned curve (A SA1 cells (normal priority; c=0, m in 2,4,8)); lo/hi = time-to-slice-end bin in ms:

  lo   hi    n  mean_wait_ms
0.00 0.05  775      0.068396
0.05 0.10  797      0.122280
0.10 0.15  839      0.167806
0.15 0.20  779      0.207650
0.20 0.25  758      0.258501
0.25 0.30  740      0.293129
0.30 0.35  549      0.338332
0.35 0.40  185      0.437347
0.40 0.45   71      0.455905
0.45 0.50  125      0.288318
0.50 0.55  178      0.294491
0.55 0.60  327      0.192792
0.60 0.65  599      0.154102
0.65 0.70  817      0.163876
0.70 0.75  805      0.202829
0.75 0.80  830      0.264944
0.80 0.85  809      0.294092
0.85 0.90  870      0.322573
0.90 0.95  870      0.337262
0.95 1.00  800      0.353329
1.00 1.50 7607      0.276447
1.50 2.00 8175      0.284388
2.00 2.50 6908      0.328558
2.50 3.00 3933      0.318606
3.00 3.50 3470      0.300912
3.50 4.00 3575      0.296056
4.00 4.50 3109      0.321668
4.50 5.00 1700      0.339773
5.00 5.50 1249      0.314214
5.50 6.00 1247      0.300353
6.00 6.50 1221      0.318836
6.50 7.00 1152      0.306295
7.00 7.50 1175      0.333765
7.50 8.00 1161      0.303963
8.00 8.50 1051      0.323727
8.50 9.00  541      0.364339
9.00 9.50  167      0.426453

- A2 sa3_high cells (HIGH priority; c=0, m in 2,8): n = 37895 requests; fitted tau = 0.270 ms, 90% block-bootstrap CI [0.260, 0.270]; offset = 0.028 ms
    - m = 2 ms: tau = 0.260 [0.260, 0.270], offset 0.036
    - m = 8 ms: tau = 0.280 [0.260, 0.290], offset 0.018

  Binned curve (A2 sa3_high cells (HIGH priority; c=0, m in 2,8)); lo/hi = time-to-slice-end bin in ms:

  lo   hi    n  mean_wait_ms
0.00 0.05  520      0.066696
0.05 0.10  545      0.113322
0.10 0.15  527      0.153602
0.15 0.20  502      0.203900
0.20 0.25  511      0.233816
0.25 0.30  430      0.307274
0.30 0.35  450      0.336778
0.35 0.40  131      0.368970
0.40 0.45   41      0.460173
0.45 0.50   97      0.282253
0.50 0.55  139      0.287703
0.55 0.60  152      0.259521
0.60 0.65  381      0.162091
0.65 0.70  543      0.157114
0.70 0.75  548      0.206755
0.75 0.80  549      0.240808
0.80 0.85  556      0.292370
0.85 0.90  565      0.313995
0.90 0.95  552      0.302997
0.95 1.00  494      0.358203
1.00 1.50 4945      0.276140
1.50 2.00 5327      0.274459
2.00 2.50 4306      0.337816
2.50 3.00 1584      0.334482
3.00 3.50 1200      0.289210
3.50 4.00 1190      0.295064
4.00 4.50 1156      0.290471
4.50 5.00 1114      0.311657
5.00 5.50 1204      0.292553
5.50 6.00 1206      0.308776
6.00 6.50 1189      0.312944
6.50 7.00 1113      0.303857
7.00 7.50 1173      0.313941
7.50 8.00 1150      0.309405
8.00 8.50 1053      0.316864
8.50 9.00  564      0.354181
9.00 9.50  157      0.398098


## Flags (cells stay in the data): 28 of 181

 block        cell_id                                         flags
     0 duty_fg9_d0.75                            fg_incomplete:0.77
     0     sa4_fg9_m8                            fg_incomplete:0.49
     0     sa4_fg9_m2                            fg_incomplete:0.54
     1     sa4_fg9_m8                            fg_incomplete:0.49
     1     sa4_fg9_m2                            fg_incomplete:0.53
     1 duty_fg9_d0.75                            fg_incomplete:0.77
     2     sa4_fg9_m2                            fg_incomplete:0.54
     2 duty_fg9_d0.75                            fg_incomplete:0.77
     2     sa4_fg9_m8                            fg_incomplete:0.49
     3     sa4_fg9_m2                            fg_incomplete:0.54
     3 duty_fg9_d0.75                            fg_incomplete:0.77
     3     sa4_fg9_m8                            fg_incomplete:0.49
     4     sa4_fg9_m8                            fg_incomplete:0.49
     4     sa4_fg9_m2 mem_clock_left_target:7001;fg_incomplete:0.54
     4 duty_fg9_d0.75                            fg_incomplete:0.77
     5 duty_fg9_d0.75                            fg_incomplete:0.77
     6 duty_fg9_d0.75                            fg_incomplete:0.77
     6     sa4_fg9_m2                            fg_incomplete:0.54
     6     sa4_fg9_m8                            fg_incomplete:0.49
     7 duty_fg9_d0.75                            fg_incomplete:0.77
     7     sa4_fg9_m8                            fg_incomplete:0.49
     7     sa4_fg9_m2                            fg_incomplete:0.53
     8 duty_fg9_d0.75                            fg_incomplete:0.77
     8     sa4_fg9_m8                            fg_incomplete:0.49
     8     sa4_fg9_m2                            fg_incomplete:0.54
     9 duty_fg9_d0.75                            fg_incomplete:0.77
     9     sa4_fg9_m8                            fg_incomplete:0.49
     9     sa4_fg9_m2                            fg_incomplete:0.54

## Incident flags (sidecar incident_flags.csv; analysis/a2_incident_flags.py; journal 0023)

               cell_dir                        flag                                                     detail
   b04_14_sa4_fg1_alone user_activity_contamination span overlaps reported Chrome window 18:22:00-18:24:59 UTC
b04_15_sa3_high_m2_c0.0 user_activity_contamination span overlaps reported Chrome window 18:22:00-18:24:59 UTC
b04_16_sa3_high_m2_c1.0 user_activity_contamination span overlaps reported Chrome window 18:22:00-18:24:59 UTC
      b04_17_sa4_fg1_m8 user_activity_contamination span overlaps reported Chrome window 18:22:00-18:24:59 UTC
   b04_18_sa4_fg4_alone user_activity_contamination span overlaps reported Chrome window 18:22:00-18:24:59 UTC
      b05_00_sa4_fg1_m2 user_activity_contamination span overlaps reported Chrome window 18:22:00-18:24:59 UTC
      b05_01_sa4_fg9_m8 user_activity_contamination span overlaps reported Chrome window 18:22:00-18:24:59 UTC
      b05_02_sa4_fg9_m2 user_activity_contamination span overlaps reported Chrome window 18:22:00-18:24:59 UTC
   b05_03_sa4_fg1_alone user_activity_contamination span overlaps reported Chrome window 18:22:00-18:24:59 UTC
  b07_08_duty_fg9_d0.25       post_stall_first_cell                 idle gap 1381 s after b07_07_sa4_fg4_alone
b08_16_sa3_high_m2_c1.0       post_stall_first_cell                     idle gap 584 s after b08_15_sa4_fg1_m2