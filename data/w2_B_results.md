# W2 Experiment B: device-wide clock lock vs foreground

Source: `C:\Users\arjun\governor\data\raw\w2_B\20261021T105205Z` | run 20261021T105205Z | admin True | AC True | ambient 25.0 C | NVIDIA GeForce RTX 4070 Laptop GPU | driver 616.92 | yaml e1df18ccd6898bd9 | dll aa73f2b11a6ccb41 | git fbabf621
HAGS: DriverSupportState:Stable Enabled:True. Execution mode: CUDA native kernels via w2_kernels.dll (no CPU fallback).

## HB1 (reference: locked 1800 MHz)

    frame kind  level  ratio_median    ci_lo    ci_hi     pred  tol    ok
fma_120hz  fma    900      1.998983 1.998983 1.999333 2.000000 0.10  True
fma_120hz  fma   1200      1.499746 1.499576 1.499966 1.500000 0.10  True
fma_120hz  fma   1500      1.203170 1.202916 1.203409 1.201970 0.10  True
 fma_60hz  fma    900      1.999704 1.999619 1.999831 2.000000 0.10  True
 fma_60hz  fma   1200      1.500085 1.499958 1.500381 1.500000 0.10  True
 fma_60hz  fma   1500      1.203122 1.202995 1.203334 1.201970 0.10  True
 mem_60hz  mem    900      1.010772 1.010723 1.010772 1.122610 0.05 False
 mem_60hz  mem   1200      1.005072 1.004928 1.005157 1.005035 0.05  True
 mem_60hz  mem   1500      1.001604 1.001519 1.001605 1.001003 0.05  True

**HB1 SUPPORTED** (all fma frames, all levels).

## HB2 (deadline misses vs 1800 MHz; overloaded levels: only miss fraction and service time are interpreted)

### fma_120hz, background nobg: must be significant at [900, 1200] -> **SUPPORTED**

 level        p  p_holm  significant
   900 0.000977 0.00293         True
  1200 0.000977 0.00293         True
  1500 1.000000 1.00000        False

### fma_60hz, background nobg: must be significant at [900, 1200] -> **SUPPORTED**

 level        p  p_holm  significant
   900 0.000977 0.00293         True
  1200 0.000977 0.00293         True
  1500 1.000000 1.00000        False

### fma_120hz, background membg: must be significant at [900, 1200] -> **NOT SUPPORTED**

 level   p  p_holm  significant
   900 1.0     1.0        False
  1200 1.0     1.0        False
  1500 1.0     1.0        False

### fma_60hz, background membg: must be significant at [900, 1200] -> **NOT SUPPORTED**

 level   p  p_holm  significant
   900 1.0     1.0        False
  1200 1.0     1.0        False
  1500 1.0     1.0        False

## Descriptive: 1050 MHz (B-levels addendum; outside HB1/HB2; the W1 value is a linear interpolation, not a measurement)

    frame  ratio_1050_vs_1800_median  interpolated_w1_prediction
fma_120hz                   1.713511                    1.714286
 fma_60hz                   1.714225                    1.714286
 mem_60hz                   1.009054                    1.060574

## Descriptive per cell (medians over blocks)

                 cell_id   lat_p50_ms   lat_p99_ms  fg_gpu_p50_ms  miss_frac  power_counter_w  sm_clock_med
    fma_120hz_membg_1050 10358.088817 11551.635084      10.352128        1.0        27.945388        1050.0
    fma_120hz_membg_1200  9056.467392  9491.479882       9.059328        1.0        29.736731        1200.0
    fma_120hz_membg_1500  6889.957367  7457.872986       7.264768        1.0        34.927506        1500.0
    fma_120hz_membg_1800  5150.185917  6178.067674       6.052864        1.0        43.320500        1800.0
     fma_120hz_membg_900 11921.387642 14130.115220      12.075008        1.0        26.584904         900.0
fma_120hz_membg_unlocked  2497.917900  3489.901839      10.754560        1.0        69.372160        2460.0
     fma_120hz_nobg_1050  1717.856117  2912.916624      10.351616        1.0        25.059933        1050.0
     fma_120hz_nobg_1200   629.670192  1063.723429       9.059328        1.0        27.964254        1200.0
     fma_120hz_nobg_1500     7.286567     7.398109       7.268352        0.0        33.565671        1500.0
     fma_120hz_nobg_1800     6.072108     6.734255       6.040576        0.0        41.320734        1800.0
      fma_120hz_nobg_900  3167.644092  5377.241174      12.076032        1.0        22.787590         900.0
 fma_120hz_nobg_unlocked     4.481858     5.072600       4.422656        0.0        61.887073        2460.0
     fma_60hz_membg_1050 10330.420258 11534.029147      20.745216        1.0        27.099516        1050.0
     fma_60hz_membg_1200  9014.531133  9456.723986      18.154495        1.0        29.001235        1200.0
     fma_60hz_membg_1500  6874.210517  7437.804006      14.557696        1.0        34.144808        1500.0
     fma_60hz_membg_1800  5062.409800  6082.029038      12.125952        1.0        42.246311        1800.0
      fma_60hz_membg_900 11956.845058 14172.948870      24.200191        1.0        25.922955         900.0
 fma_60hz_membg_unlocked  2501.200525  3499.922260      22.198527        1.0        65.630184        2460.0
      fma_60hz_nobg_1050  1738.869758  2940.626874      20.743168        1.0        23.936043        1050.0
      fma_60hz_nobg_1200   649.037558  1090.194256      18.152449        1.0        26.441119        1200.0
      fma_60hz_nobg_1500    14.593675    14.988098      14.559232        0.0        31.936978        1500.0
      fma_60hz_nobg_1800    12.164992    12.705947      12.101632        0.0        38.542638        1800.0
       fma_60hz_nobg_900  3192.091358  5408.372207      24.198656        1.0        21.840301         900.0
  fma_60hz_nobg_unlocked     8.923375     9.534392       8.859072        0.0        56.487796        2460.0
     mem_60hz_membg_1050  3880.303308  5217.453336      27.189247        1.0        31.490234        1050.0
     mem_60hz_membg_1200  3614.938508  4898.739432      26.145024        1.0        32.733756        1200.0
     mem_60hz_membg_1500  3279.620483  4487.717342      24.899073        1.0        36.561636        1500.0
     mem_60hz_membg_1800  3072.504967  4231.186070      24.199936        1.0        40.959866        1800.0
      mem_60hz_membg_900  4154.244608  5541.029399      28.057087        1.0        30.695910         900.0
 mem_60hz_membg_unlocked  3044.841275  4194.543455      24.117761        1.0        54.464624        2475.0
      mem_60hz_nobg_1050     9.088833     9.832200       9.016320        0.0        25.230952        1050.0
      mem_60hz_nobg_1200     9.051267     9.736222       8.980992        0.0        25.633873        1200.0
      mem_60hz_nobg_1500     9.018542     9.702987       8.949760        0.0        27.416745        1500.0
      mem_60hz_nobg_1800     9.001217     9.641651       8.935424        0.0        31.234257        1800.0
       mem_60hz_nobg_900     9.104975     9.936391       9.031680        0.0        24.910868         900.0
  mem_60hz_nobg_unlocked     8.994100     9.591141       8.928256        0.0        40.736294        2475.0

## Flags (cells stay in the data): 220 of 360

 block                  cell_id              flags
     0      mem_60hz_membg_1500 fg_incomplete:0.65
     0       fma_60hz_membg_900 fg_incomplete:0.09
     0        fma_60hz_nobg_900 fg_incomplete:0.69
     0 fma_120hz_membg_unlocked fg_incomplete:0.75
     0     fma_120hz_membg_1500 fg_incomplete:0.35
     0      fma_120hz_membg_900 fg_incomplete:0.09
     0      fma_60hz_membg_1200 fg_incomplete:0.22
     0  fma_60hz_membg_unlocked fg_incomplete:0.75
     0      fma_120hz_nobg_1050 fg_incomplete:0.84
     0      fma_60hz_membg_1500 fg_incomplete:0.35
     0     fma_120hz_membg_1800 fg_incomplete:0.48
     0       mem_60hz_membg_900 fg_incomplete:0.54
     0       fma_60hz_nobg_1050 fg_incomplete:0.84
     0     fma_120hz_membg_1200 fg_incomplete:0.22
     0      mem_60hz_membg_1800 fg_incomplete:0.67
     0      fma_60hz_membg_1050 fg_incomplete:0.15
     0      fma_60hz_membg_1800 fg_incomplete:0.49
     0  mem_60hz_membg_unlocked fg_incomplete:0.68
     0       fma_120hz_nobg_900 fg_incomplete:0.69
     0      mem_60hz_membg_1200 fg_incomplete:0.61
     0     fma_120hz_membg_1050 fg_incomplete:0.15
     0      mem_60hz_membg_1050 fg_incomplete:0.57
     1       fma_120hz_nobg_900 fg_incomplete:0.69
     1      mem_60hz_membg_1200 fg_incomplete:0.61
     1      fma_60hz_membg_1500 fg_incomplete:0.36
     1      fma_60hz_membg_1050 fg_incomplete:0.15
     1       fma_60hz_membg_900 fg_incomplete:0.09
     1     fma_120hz_membg_1500 fg_incomplete:0.35
     1 fma_120hz_membg_unlocked fg_incomplete:0.75
     1      fma_60hz_membg_1200 fg_incomplete:0.22
     1       mem_60hz_membg_900 fg_incomplete:0.55
     1  mem_60hz_membg_unlocked fg_incomplete:0.68
     1      mem_60hz_membg_1050 fg_incomplete:0.57
     1      mem_60hz_membg_1800 fg_incomplete:0.67
     1      fma_120hz_nobg_1050 fg_incomplete:0.84
     1     fma_120hz_membg_1200 fg_incomplete:0.22
     1      fma_120hz_membg_900 fg_incomplete:0.09
     1  fma_60hz_membg_unlocked fg_incomplete:0.75
     1      mem_60hz_membg_1500 fg_incomplete:0.65
     1     fma_120hz_membg_1050 fg_incomplete:0.15
     1      fma_60hz_membg_1800 fg_incomplete:0.49
     1     fma_120hz_membg_1800 fg_incomplete:0.48
     1       fma_60hz_nobg_1050 fg_incomplete:0.84
     1        fma_60hz_nobg_900 fg_incomplete:0.69
     2       fma_120hz_nobg_900 fg_incomplete:0.69
     2 fma_120hz_membg_unlocked fg_incomplete:0.75
     2     fma_120hz_membg_1800 fg_incomplete:0.48
     2  fma_60hz_membg_unlocked fg_incomplete:0.75
     2      fma_60hz_membg_1500 fg_incomplete:0.36
     2      fma_120hz_membg_900 fg_incomplete:0.09
     2      mem_60hz_membg_1800 fg_incomplete:0.67
     2      mem_60hz_membg_1050 fg_incomplete:0.57
     2      mem_60hz_membg_1500 fg_incomplete:0.65
     2       mem_60hz_membg_900 fg_incomplete:0.54
     2      mem_60hz_membg_1200 fg_incomplete:0.61
     2     fma_120hz_membg_1200 fg_incomplete:0.22
     2  mem_60hz_membg_unlocked fg_incomplete:0.68
     2      fma_120hz_nobg_1050 fg_incomplete:0.84
     2     fma_120hz_membg_1500 fg_incomplete:0.35
     2      fma_60hz_membg_1200 fg_incomplete:0.22
     2     fma_120hz_membg_1050 fg_incomplete:0.15
     2       fma_60hz_nobg_1050 fg_incomplete:0.84
     2      fma_60hz_membg_1800 fg_incomplete:0.49
     2        fma_60hz_nobg_900 fg_incomplete:0.69
     2      fma_60hz_membg_1050 fg_incomplete:0.15
     2       fma_60hz_membg_900 fg_incomplete:0.09
     3        fma_60hz_nobg_900 fg_incomplete:0.69
     3  mem_60hz_membg_unlocked fg_incomplete:0.68
     3     fma_120hz_membg_1800 fg_incomplete:0.48
     3     fma_120hz_membg_1050 fg_incomplete:0.15
     3      fma_60hz_membg_1800 fg_incomplete:0.49
     3       fma_60hz_nobg_1050 fg_incomplete:0.84
     3      fma_60hz_membg_1200 fg_incomplete:0.22
     3      fma_60hz_membg_1500 fg_incomplete:0.35
     3      fma_120hz_nobg_1050 fg_incomplete:0.84
     3      mem_60hz_membg_1500 fg_incomplete:0.65
     3       mem_60hz_membg_900 fg_incomplete:0.55
     3 fma_120hz_membg_unlocked fg_incomplete:0.75
     3      mem_60hz_membg_1200 fg_incomplete:0.61
     3       fma_120hz_nobg_900 fg_incomplete:0.69
     3     fma_120hz_membg_1500 fg_incomplete:0.35
     3  fma_60hz_membg_unlocked fg_incomplete:0.75
     3      mem_60hz_membg_1050 fg_incomplete:0.57
     3      mem_60hz_membg_1800 fg_incomplete:0.67
     3       fma_60hz_membg_900 fg_incomplete:0.09
     3      fma_60hz_membg_1050 fg_incomplete:0.15
     3     fma_120hz_membg_1200 fg_incomplete:0.22
     3      fma_120hz_membg_900 fg_incomplete:0.09
     4      fma_120hz_nobg_1050 fg_incomplete:0.84
     4 fma_120hz_membg_unlocked fg_incomplete:0.75
     4     fma_120hz_membg_1800 fg_incomplete:0.48
     4      fma_60hz_membg_1800 fg_incomplete:0.49
     4       fma_60hz_nobg_1050 fg_incomplete:0.84
     4     fma_120hz_membg_1050 fg_incomplete:0.15
     4       fma_60hz_membg_900 fg_incomplete:0.09
     4  fma_60hz_membg_unlocked fg_incomplete:0.75
     4  mem_60hz_membg_unlocked fg_incomplete:0.68
     4       fma_120hz_nobg_900 fg_incomplete:0.69
     4     fma_120hz_membg_1200 fg_incomplete:0.22
     4      mem_60hz_membg_1200 fg_incomplete:0.61
     4        fma_60hz_nobg_900 fg_incomplete:0.69
     4      fma_120hz_membg_900 fg_incomplete:0.09
     4      fma_60hz_membg_1200 fg_incomplete:0.22
     4      mem_60hz_membg_1500 fg_incomplete:0.65
     4     fma_120hz_membg_1500 fg_incomplete:0.35
     4       mem_60hz_membg_900 fg_incomplete:0.54
     4      fma_60hz_membg_1050 fg_incomplete:0.15
     4      fma_60hz_membg_1500 fg_incomplete:0.35
     4      mem_60hz_membg_1050 fg_incomplete:0.57
     4      mem_60hz_membg_1800 fg_incomplete:0.67
     5      fma_120hz_membg_900 fg_incomplete:0.09
     5     fma_120hz_membg_1200 fg_incomplete:0.22
     5      mem_60hz_membg_1800 fg_incomplete:0.67
     5       fma_60hz_membg_900 fg_incomplete:0.09
     5  mem_60hz_membg_unlocked fg_incomplete:0.68
     5      fma_60hz_membg_1200 fg_incomplete:0.22
     5 fma_120hz_membg_unlocked fg_incomplete:0.75
     5     fma_120hz_membg_1800 fg_incomplete:0.48
     5       mem_60hz_membg_900 fg_incomplete:0.54
     5      mem_60hz_membg_1050 fg_incomplete:0.57
     5        fma_60hz_nobg_900 fg_incomplete:0.69
     5      fma_60hz_membg_1800 fg_incomplete:0.49
     5      fma_120hz_nobg_1050 fg_incomplete:0.84
     5       fma_120hz_nobg_900 fg_incomplete:0.69
     5       fma_60hz_nobg_1050 fg_incomplete:0.84
     5      fma_60hz_membg_1050 fg_incomplete:0.15
     5      mem_60hz_membg_1500 fg_incomplete:0.65
     5     fma_120hz_membg_1050 fg_incomplete:0.15
     5     fma_120hz_membg_1500 fg_incomplete:0.35
     5  fma_60hz_membg_unlocked fg_incomplete:0.74
     5      mem_60hz_membg_1200 fg_incomplete:0.61
     5      fma_60hz_membg_1500 fg_incomplete:0.35
     6      fma_120hz_membg_900 fg_incomplete:0.09
     6      mem_60hz_membg_1500 fg_incomplete:0.65
     6        fma_60hz_nobg_900 fg_incomplete:0.69
     6       fma_120hz_nobg_900 fg_incomplete:0.69
     6      fma_60hz_membg_1500 fg_incomplete:0.35
     6 fma_120hz_membg_unlocked fg_incomplete:0.75
     6       fma_60hz_nobg_1050 fg_incomplete:0.84
     6  mem_60hz_membg_unlocked fg_incomplete:0.68
     6       fma_60hz_membg_900 fg_incomplete:0.09
     6      fma_120hz_nobg_1050 fg_incomplete:0.84
     6      mem_60hz_membg_1200 fg_incomplete:0.61
     6       mem_60hz_membg_900 fg_incomplete:0.53
     6     fma_120hz_membg_1500 fg_incomplete:0.35
     6     fma_120hz_membg_1200 fg_incomplete:0.22
     6  fma_60hz_membg_unlocked fg_incomplete:0.75
     6      mem_60hz_membg_1050 fg_incomplete:0.57
     6      fma_60hz_membg_1800 fg_incomplete:0.49
     6      mem_60hz_membg_1800 fg_incomplete:0.67
     6     fma_120hz_membg_1050 fg_incomplete:0.15
     6      fma_60hz_membg_1200 fg_incomplete:0.22
     6      fma_60hz_membg_1050 fg_incomplete:0.15
     6     fma_120hz_membg_1800 fg_incomplete:0.48
     7  mem_60hz_membg_unlocked fg_incomplete:0.68
     7      mem_60hz_membg_1800 fg_incomplete:0.68
     7       fma_60hz_membg_900 fg_incomplete:0.09
     7      fma_60hz_membg_1050 fg_incomplete:0.15
     7      mem_60hz_membg_1050 fg_incomplete:0.57
     7     fma_120hz_membg_1800 fg_incomplete:0.48
     7      fma_60hz_membg_1800 fg_incomplete:0.49
     7       fma_120hz_nobg_900 fg_incomplete:0.69
     7 fma_120hz_membg_unlocked fg_incomplete:0.75
     7      mem_60hz_membg_1200 fg_incomplete:0.61
     7        fma_60hz_nobg_900 fg_incomplete:0.69
     7       mem_60hz_membg_900 fg_incomplete:0.54
     7     fma_120hz_membg_1200 fg_incomplete:0.22
     7       fma_60hz_nobg_1050 fg_incomplete:0.84
     7      fma_120hz_nobg_1050 fg_incomplete:0.84
     7      fma_60hz_membg_1500 fg_incomplete:0.35
     7     fma_120hz_membg_1050 fg_incomplete:0.15
     7      mem_60hz_membg_1500 fg_incomplete:0.65
     7      fma_120hz_membg_900 fg_incomplete:0.09
     7  fma_60hz_membg_unlocked fg_incomplete:0.75
     7      fma_60hz_membg_1200 fg_incomplete:0.22
     7     fma_120hz_membg_1500 fg_incomplete:0.35
     8     fma_120hz_membg_1050 fg_incomplete:0.15
     8      fma_60hz_membg_1800 fg_incomplete:0.49
     8       fma_120hz_nobg_900 fg_incomplete:0.69
     8      fma_120hz_nobg_1050 fg_incomplete:0.84
     8       fma_60hz_nobg_1050 fg_incomplete:0.84
     8  fma_60hz_membg_unlocked fg_incomplete:0.75
     8      mem_60hz_membg_1500 fg_incomplete:0.65
     8      fma_60hz_membg_1050 fg_incomplete:0.15
     8     fma_120hz_membg_1800 fg_incomplete:0.48
     8     fma_120hz_membg_1200 fg_incomplete:0.22
     8      mem_60hz_membg_1800 fg_incomplete:0.67
     8       fma_60hz_membg_900 fg_incomplete:0.09
     8      mem_60hz_membg_1050 fg_incomplete:0.57
     8      fma_120hz_membg_900 fg_incomplete:0.09
     8      mem_60hz_membg_1200 fg_incomplete:0.61
     8     fma_120hz_membg_1500 fg_incomplete:0.35
     8      fma_60hz_membg_1200 fg_incomplete:0.22
     8 fma_120hz_membg_unlocked fg_incomplete:0.75
     8  mem_60hz_membg_unlocked fg_incomplete:0.68
     8        fma_60hz_nobg_900 fg_incomplete:0.69
     8      fma_60hz_membg_1500 fg_incomplete:0.35
     8       mem_60hz_membg_900 fg_incomplete:0.55
     9      fma_60hz_membg_1050 fg_incomplete:0.15
     9     fma_120hz_membg_1200 fg_incomplete:0.22
     9  mem_60hz_membg_unlocked fg_incomplete:0.68
     9      fma_60hz_membg_1800 fg_incomplete:0.49
     9      fma_120hz_nobg_1050 fg_incomplete:0.84
     9      mem_60hz_membg_1050 fg_incomplete:0.57
     9  fma_60hz_membg_unlocked fg_incomplete:0.75
     9        fma_60hz_nobg_900 fg_incomplete:0.69
     9       mem_60hz_membg_900 fg_incomplete:0.54
     9      mem_60hz_membg_1800 fg_incomplete:0.67
     9     fma_120hz_membg_1050 fg_incomplete:0.15
     9 fma_120hz_membg_unlocked fg_incomplete:0.75
     9      fma_120hz_membg_900 fg_incomplete:0.09
     9      fma_60hz_membg_1200 fg_incomplete:0.22
     9       fma_120hz_nobg_900 fg_incomplete:0.69
     9     fma_120hz_membg_1800 fg_incomplete:0.48
     9       fma_60hz_nobg_1050 fg_incomplete:0.84
     9       fma_60hz_membg_900 fg_incomplete:0.09
     9      mem_60hz_membg_1200 fg_incomplete:0.61
     9     fma_120hz_membg_1500 fg_incomplete:0.35
     9      mem_60hz_membg_1500 fg_incomplete:0.65
     9      fma_60hz_membg_1500 fg_incomplete:0.35