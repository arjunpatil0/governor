# W2 Experiment C: decode proxy clock knee

Source: `C:\Users\arjun\governor\data\raw\w2_C\20261021T085528Z` | run 20261021T085528Z | admin True | AC True | ambient 25.0 C | NVIDIA GeForce RTX 4070 Laptop GPU | driver 616.92 | yaml e1df18ccd6898bd9 | dll aa73f2b11a6ccb41 | git 15f8b40a
HAGS: DriverSupportState:Stable Enabled:True. Execution mode: CUDA native kernels via w2_kernels.dll (no CPU fallback).

## Per-block knees (graph launch mode; 10000 = unlocked)

 block  fp16  int4
     0  1050 10000
     1  1050 10000
     2  1050 10000
     3  1050 10000
     4  1050 10000
     5  1050 10000
     6  1050 10000
     7  1050 10000
     8  1050 10000
     9  1050 10000

**HC1 SUPPORTED** (nonzero int4 - fp16 knee differences in 10 blocks; p = 0.0009765625).

## Knee and energy optimum per configuration (medians over blocks)

variant  graph knee_mhz  energy_optimum  j_per_token_at_opt
   fp16  False     1050             900            0.538904
   fp16   True     1050             750            0.533786
   int4  False unlocked            1350            0.720738
   int4   True unlocked            1500            0.711735

## Main finding (fp16 proxy, CUDA graph) and the limits of the int4 result

- **Main C finding (fp16 proxy, 14 layers, CUDA graph):** at 1050 MHz the proxy keeps 0.96 of its unlocked throughput at 0.535 J/token against 0.861 J/token unlocked (38% lower; board-level energy counter, W1 addendum caveats apply).
- **Construct validity of the int4 proxy:** HC1 is supported statistically, but the int4 proxy lacks construct validity for Q4 decode: its dequantisation is scalar, and its throughput is close to proportional to the clock (relative throughput 0.743 at 1800 MHz against 1800/2460 = 0.732). Only the direction (more ALU work per byte raises the knee) is supported; the magnitude does not transfer. **Do not use the int4 knee in any governor claim.** A real engine is measured by the llama.cpp validation addendum.

## rel. throughput and J/token by level (medians)

variant  graph    level  rel_thr  j_per_token
   fp16  False      600 0.909639     0.544628
   fp16  False      750 0.930723     0.543523
   fp16  False      900 0.942771     0.538904
   fp16  False     1050 0.954819     0.541989
   fp16  False     1200 0.963855     0.557906
   fp16  False     1350 0.972892     0.579399
   fp16  False     1500 0.980422     0.600178
   fp16  False     1800 0.990964     0.657932
   fp16  False unlocked 1.000000     0.869176
   fp16   True      600 0.914201     0.540498
   fp16   True      750 0.934911     0.533786
   fp16   True      900 0.949704     0.533917
   fp16   True     1050 0.958641     0.534517
   fp16   True     1200 0.970414     0.547857
   fp16   True     1350 0.976331     0.561023
   fp16   True     1500 0.982249     0.589181
   fp16   True     1800 0.991124     0.651949
   fp16   True unlocked 1.000000     0.860770
   int4  False      600 0.261307     1.091207
   int4  False      750 0.324121     0.941531
   int4  False      900 0.384422     0.858212
   int4  False     1050 0.447236     0.785228
   int4  False     1200 0.510050     0.744096
   int4  False     1350 0.570352     0.720738
   int4  False     1500 0.629863     0.722634
   int4  False     1800 0.753769     0.743524
   int4  False unlocked 1.000000     0.899345
   int4   True      600 0.254197     1.062538
   int4   True      750 0.314149     0.931889
   int4   True      900 0.378897     0.836877
   int4   True     1050 0.438849     0.763060
   int4   True     1200 0.498801     0.738962
   int4   True     1350 0.561151     0.714795
   int4   True     1500 0.621103     0.711735
   int4   True     1800 0.743405     0.733810
   int4   True unlocked 1.000000     0.886681

## Flags (cells stay in the data): 0 of 360

none