# W2 llama.cpp validation (part L): decode clock knee of a real engine

Source: `data\raw\w2_L\20261021T205034Z` | run 20261021T205034Z | admin True | AC True | ambient 25.0 C | NVIDIA GeForce RTX 4070 Laptop GPU | driver 616.92 | yaml e1df18ccd6898bd9 | dll aa73f2b11a6ccb41 | git 55851e1e
HAGS: DriverSupportState:Stable Enabled:True. Execution mode: llama.cpp CUDA build, all layers offloaded (checked per cell from the driver log; a cell with any CPU layer aborts the run).

Engine: llama.cpp pinned commit 620d2225cc436ab0b001e3200e590e3b286ef9ab (v0.7.0), CUDA sm_89, Llama-3.2-3B-Instruct Q4_K_M, batch 1, greedy, context ~512 + decode. One engine, one model, one quantisation.

## HL1 knee (lowest level with median relative throughput >= 0.95; 90% block-bootstrap CI)

- knee 1500 MHz, 90% CI [1500, 1500] -> **intermediate** (fp16 proxy knee 1050 MHz; int4 proxy: unlocked)

## HL2 energy optimum and retained throughput

- energy optimum (lowest median J/token): 1050 MHz at 0.5263 J/token; unlocked: 0.9152 J/token
- relative throughput at 1050 MHz (the C fp16 knee): 0.884; at 1800 MHz: 0.980

## HL3 correctness: identical greedy token ids within every block (over the common prefix)

- blocks compared: 10; blocks with differing sequences: none; blocks where a cell shares fewer than 64 tokens (check does not count): none
- shared-prefix length per cell (min / median / max): 345 / 521 / 562

## Relative throughput and J/token by level (medians over blocks)

   level  rel_thr  j_per_token
     600 0.613300     0.650501
     750 0.733910     0.584760
     900 0.829204     0.547761
    1050 0.883806     0.526346
    1200 0.923645     0.535062
    1350 0.943293     0.552644
    1500 0.959462     0.578532
    1800 0.980296     0.663832
unlocked 1.000000     0.915159

## Flags (cells stay in the data): 0 of 90

none