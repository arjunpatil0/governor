# Experiment G: POST-HOC mechanism analysis (exploratory; NOT registered)

Source `C:\Users\arjun\governor\data\raw\w2_G\20261022T062433Z` (witness blocks, recorded-interval fg launches). Review: reviews/2026-10-22_G_results_review.md findings 1(a-d) and 2. Registered verdicts in data/w2_G_results.md are unchanged (P6 DID NOT HOLD; the 3-bpsm control overlaps, so the registered rule reports it as a finding). Everything below was chosen AFTER seeing the registered results and is labelled post-hoc.
Comparison scales from the registered analysis: s = 0.148 ms (median gap between runs of different contexts), q = 0.374 ms (median complete run).

## 1a. Overlap duration (every fg/bg on-interval pair intersecting by more than 10 us)

```
      cell  fg_launches  pairs  same_sm  p10_us  p50_us  p90_us  p99_us  max_us
      g_T1         9996 167195     4644   176.1   286.7   402.4   406.5   408.6
      g_T4         3980 423439    11762    55.3   364.5   405.5   408.6   519.2
g_T4_3bpsm         3959  94345     2621   373.8   388.1   390.1   403.5   406.5
```

- scale: s = 148 us, q = 374 us

## 1b. Position of overlaps relative to the nearest run boundary (fg or bg merged-run start/end)

```
      cell      n  p10_us  p50_us  p90_us  p99_us  max_us  frac_within_s  uniform_ref_within_s
      g_T1 167195  88.576 143.360 201.216 203.264 204.288          0.640                 0.779
      g_T4 423439  28.160 183.296 202.752 204.288 261.120          0.235                 0.767
g_T4_3bpsm  94345 192.000 194.560 195.584 201.728 203.264          0.001                 0.829
```

- `frac_within_s`: share of overlaps whose midpoint lies within s of a boundary; `uniform_ref_within_s`: the same share for points placed uniformly inside the fg launch spans. Overlaps concentrated at boundaries give frac_within_s well above the reference; overlaps spread through runs give about the reference.

## 1c. Per-switch stagger across SMs (switches seen on >= 30 of 36 SMs)

```
      cell direction  switches  out_end_spread_us_p50  out_end_spread_us_p90  in_start_spread_us_p50  in_start_spread_us_p90  cluster_overlap_us_p50  cluster_overlap_us_p90  per_sm_gap_us_p50  per_sm_gap_min_us_p1  sm_with_same_sm_overlap  sm_switches
      g_T1    fg->bg     11530                    2.0                    3.1                     1.0                     2.0                  -297.0                  -107.5              298.0                 101.4                        0       414718
      g_T1    bg->fg     11626                    1.0                    4.1                     1.0                     2.0                  -132.1                  -101.4              133.1                  99.3                        0       417533
      g_T4    fg->bg     17196                    1.0                    5.1                     1.0                     2.0                  -147.5                  -105.5              148.5                  99.3                        0       617710
      g_T4    bg->fg     16757                    1.0                    4.1                     1.0                     2.0                  -158.7                  -123.9              160.8                 100.4                        0       601275
g_T4_3bpsm    fg->bg     43279                    1.0                    1.0                     1.0                     2.0                  -102.4                   -92.2              103.4                  81.9                        0      1558004
g_T4_3bpsm    bg->fg     43231                    1.0                    2.0                     1.0                     2.0                  -102.4                   -92.2              103.4                  81.9                        0      1556038
```

- `cluster_overlap` = latest outgoing end minus earliest incoming start over the 36 SMs (positive = some SM starts the incoming context before another SM has finished the outgoing one). `per_sm_gap` = incoming start minus outgoing end on the SAME SM (negative = same-SM overlap). A staggered switch has cluster_overlap > 0 with per-SM gaps >= 0.

## 1d. Same-SM overlaps (two contexts' blocks on one SM at once): edge test and hand-inspection sample

```
      cell  same_sm_pairs  edge_within_30us  edge_share
      g_T1           4644              4644         1.0
      g_T4          11762             11762         1.0
g_T4_3bpsm           2621              2621         1.0
```

- edge = the intersection starts or ends within 30 us of the start/end of either block's on-interval (a block-boundary artefact would sit there).

### g_T4_3bpsm: 20 randomly sampled same-SM overlaps (4 per block, seeded by block)

```
 block  sm  fg_tag  bg_tag  fg_blk_rec  bg_blk_rec  ov_us  fg_pos_us  fg_tail_us  bg_pos_us  bg_tail_us  fg_block_us  bg_block_us  fg_nreads  bg_nreads  fg_ngaps  bg_ngaps  at_edge
     0  22     284    2517       22055      192323  390.1        0.0         0.0      499.7       103.4       6906.9       3829.8       1892        942         7         2     True
     0  18     284    2517       22050      192321  389.1        0.0         0.0      501.8       103.4       4943.9       3829.8       1892        942         5         2     True
     0  29     233    2046       16592      141476  390.1        0.0         0.0      499.7       104.4       6907.9       3827.7       1892        942         7         2     True
     0   9     254    2186       18850      156586  390.1        0.0         0.0      498.7       103.4       6908.9       3826.7       1892        942         7         2     True
     1  10     447    4195       39646      366953  390.1        0.0         0.0      499.7       104.4       4936.7       3829.8       1892        942         5         2     True
     1  24     229    2042       16116      134436  391.2        0.0         0.0      498.7       105.5       4942.8       3836.9       1892        942         5         2     True
     1  23     376    3570       32033      299477  389.1        0.0         0.0      498.7       102.4       6899.7       3826.7       1892        942         7         2     True
     1  12     447    4195       39648      366954  390.1        0.0         0.0      499.7       103.4       4936.7       3828.7       1892        942         5         2     True
     2  18     425    3322       37279      278829  387.1        0.0         0.0      502.8       103.4       6901.8       3826.7       1892        942         7         2     True
     2   6     123    1102        4719       39063  385.0        0.0         0.0      503.8       103.4       9330.7       3824.6       1892        942        10         2     True
     2   1     421    3283       36882      274626  387.1        0.0         0.0      501.8       104.4       6904.8       3832.8       1892        942         7         2     True
     2   1     127    1121        5166       41130  373.8        0.0         0.0      502.8       114.7       9328.6       3825.7       1892        942        10         2     True
     3  28     130    1173        5429       46742  389.1        0.0         0.0      500.7       104.4       6915.1       3832.8       1892        942         7         2     True
     3  31     199    1838       12903      118581  389.1        0.0         0.0      500.7       104.4       4940.8       3827.7       1892        942         5         2     True
     3  10     199    1838       12929      118553  379.9        0.0         0.0      500.7       113.7       9339.9       3828.7       1892        942        10         2     True
     3  12     422    4182       36948      371706  388.1        0.0         0.0      497.7       103.4       4936.7       3824.6       1892        942         5         2     True
     4  23     433    3775       38225      331445  377.9        0.0         0.0      510.0       103.4       9330.7       3825.7       1892        942        10         2     True
     4   0     405    3510       35101      302796  388.1        0.0         0.0      499.7       103.4       6895.6       3824.6       1892        942         7         2     True
     4   6     261    2117       19554      152355  389.1        0.0         0.0      499.7       101.4       4933.6       3824.6       1892        942         5         2     True
     4   8     315    2588       25388      203224  390.1        0.0         0.0      498.7       103.4       4936.7       3825.7       1892        942         5         2     True
```

### g_T4: 20 randomly sampled same-SM overlaps (4 per block, seeded by block)

```
 block  sm  fg_tag  bg_tag  fg_blk_rec  bg_blk_rec  ov_us  fg_pos_us  fg_tail_us  bg_pos_us  bg_tail_us  fg_block_us  bg_block_us  fg_nreads  bg_nreads  fg_ngaps  bg_ngaps  at_edge
     0  34     176    1519       10421       84184   67.6        0.0         0.0      514.0       435.2       5917.7       2112.5        954        475         6         1     True
     0  33     163    1356        9066       66630  401.4      493.6       181.2        0.0         0.0       2806.8       1276.9        954        475         2         1     True
     0  33     206    1814       13710      116096  403.5        0.0         0.0      490.5       162.8       2766.8       2903.0        954        475         3         2     True
     0  18     474    4539       42579      410320  407.6      487.4       176.1        0.0         0.0       2810.9       2136.1        954        475         2         2     True
     1   0     335    3228       27540      267626  403.5        0.0         0.0      488.4       159.7       2772.0       2889.7        954        475         3         2     True
     1  26     393    3745       33843      323499  405.5      490.5       181.2        0.0         0.0       2806.8       1281.0        954        475         2         1     True
     1  13     335    3228       27614      267698  394.2        0.0         0.0      488.4       169.0       5942.3       2888.7        954        475         6         2     True
     1   5     304    2781       24254      219409   72.7        0.0         0.0      512.0       434.2       5943.3       2103.3        954        475         6         1     True
     2  18     265    1960       20007      128224  403.5      488.4       172.0        0.0         0.0       2796.5       2130.9        954        475         2         2     True
     2  32     279    2048       21541      137749  357.4        0.0         0.0      519.2       158.7       4212.7       2148.4        954        475         4         1     True
     2   5     235    1810       16802      112057   88.1        0.0         0.0      517.1       420.9       6005.8       2114.6        954        475         6         1     True
     2  34     277    2007       21329      133325  357.4        0.0         0.0      518.1       156.7       5934.1       2926.6        954        475         6         2     True
     3  34     170    1592        9772       95848  365.6        0.0         0.0      514.0       151.6       4220.9       2141.2        954        475         4         1     True
     3   2     418    3887       36509      343660   50.2        0.0         0.0      510.0       453.6       5852.2       2095.1        954        475         6         1     True
     3  31     298    2601       23643      204868  364.5        0.0         0.0      520.2       155.6       3177.5       2150.4        954        475         3         1     True
     3  34     242    2250       17547      166913  372.7        0.0         0.0      520.2       142.3       3121.2       2886.7        954        475         3         2     True
     4  14     370    3480       31343      293675  365.6        0.0         0.0      515.1       145.4       5897.2       2895.9        954        475         6         2     True
     4  16     434    3959       38256      345409  401.4      494.6       175.1        0.0         0.0       2803.7       2118.7        954        475         2         2     True
     4   4     342    3178       28304      261043   59.4        0.0         0.0      512.0       441.3       5941.2       2086.9        954        475         6         1     True
     4  10     340    3168       28095      259972  405.5      488.4       173.1        0.0         0.0       3120.1       2116.6        954        475         2         2     True
```

## 1e. Which interval of its block is overlapping? (first = starts at the block start, last = ends at the block end, only = both, interior = neither)

```
      cell           set      n  share_involving_a_first_last_or_only_interval  share_both_interior  fg_interior  bg_interior
      g_T1     all pairs 167195                                            1.0                  0.0       0.0003       0.0009
      g_T1 same-SM pairs   4644                                            1.0                  0.0       0.0002       0.0009
      g_T4     all pairs 423439                                            1.0                  0.0       0.4355       0.0039
      g_T4 same-SM pairs  11762                                            1.0                  0.0       0.4354       0.0041
g_T4_3bpsm     all pairs  94345                                            1.0                  0.0       0.9512       0.0000
g_T4_3bpsm same-SM pairs   2621                                            1.0                  0.0       0.9512       0.0000
```

- Gaps are logged from thread 0 only. Stalls of a block's other warps before thread 0 starts or after it finishes are invisible, so an overlap made of a first/last/only interval can be a measurement artefact; an overlap between two INTERIOR intervals cannot.

## 2. tau refit on a fine grid (sensitivity; the registered fit and verdict are unchanged)

- registered fit: tau = 0.260 ms on a 0.01 ms grid, bootstrap CI [0.260, 0.260] (degenerate)
- fine grid (0.2 us step), same model, n = 80064 requests, 1000 block-cluster bootstrap resamples: tau = 0.2580 ms, 90% CI [0.2564, 0.2602], offset 0.0365 ms
