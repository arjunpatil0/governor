# 0014 — W2 Experiment C: the decode proxy's clock knee
Date: 2026-10-21 · Phase: W2 (Experiment C) · Author: Claude Code (run by Arjun)
## Question
Where is the SM-clock knee of a decode-like background, measured and not assumed to be 1200 MHz (journal 0006 item 3)? Registered in experiments/w2_colocation.yaml (b86d36e), HC1 and HC2.
## Belief going in
0006: real decode has more compute per byte than a streaming copy, so its knee is above the copy's. HC1: the int4 proxy's knee is higher than the fp16 proxy's because dequantisation adds ALU work per byte.
## What we did
`python experiments\w2_colocation\run.py --part C --ambient-c 25` from an Administrator shell on AC (Arjun), clean tree at 15f8b40, yaml sha e1df18ccd6898bd9, dll aa73f2b11a6ccb41, HAGS `Enabled:True`.
360 cells (2 variants × 2 launch modes × 9 SM levels × 10 blocks), memory clock locked at 8001 MHz, 1.5 s pre-roll, 4 s window. Analysis: `python analysis\w2_analysis.py --part C` → data/w2_C_results.md. Committed with the raw run as f6f61ec (data/raw/w2_C/20261021T085528Z).
## What happened (data/w2_C_results.md; 0 of 360 cells flagged)
- **Knee** (lowest level with median relative throughput ≥ 0.95; per-block knees identical in all 10 blocks):
  | config | knee | energy optimum (J/token) | J/token unlocked | rel. throughput at optimum |
  |---|---|---|---|---|
  | fp16, 14 layers, CUDA graph | 1050 MHz | 750 MHz: 0.534 | 0.861 | 0.935 |
  | fp16, 14 layers, stream launches | 1050 MHz | 900 MHz: 0.539 | 0.869 | 0.943 |
  | int4, 28 layers, CUDA graph | unlocked | 1500 MHz: 0.712 | 0.887 | 0.621 |
  | int4, 28 layers, stream launches | unlocked | 1350 MHz: 0.721 | 0.899 | 0.570 |
- **HC1 supported** (int4 knee above fp16 knee in 10 of 10 blocks; Wilcoxon p = 0.00098, the minimum possible with 10 blocks). The comparison is between "unlocked" and 1050 MHz.
- **fp16 proxy is memory-bound** over the whole range: 91% of unlocked throughput at 600 MHz, 99% at 1800 MHz; 240 GB/s effective at unlocked (the W1 streaming copy reached ~232 GB/s). Locking 1050 MHz keeps 0.955–0.959 of throughput at 43 W against 73 W unlocked (median power from the energy counter).
- **int4 proxy is clock-limited at every locked level:** relative throughput 0.261 / 0.324 / 0.384 / 0.447 / 0.510 / 0.570 / 0.630 / 0.754 at 600…1800 MHz (stream launches), close to proportional to the clock (1800/2460 = 0.73). Effective bandwidth is only ~146–153 GB/s at unlocked.
- **CUDA graph effect** is small: +1.8% tokens/s (fp16) and +4.8% (int4) at unlocked (84.5 vs 83.0; 104.3 vs 99.5 tok/s), and it did not move any knee. Launch cost is not what sets the knee.
- Median window power from the energy counter: fp16 graph 72.8 W unlocked, 54.6 W at 1800, 43.4 W at 1050; int4 graph 92.4 / 56.9 / 34.9 W. Clock event reasons seen: GpuIdle (320 cells, brief idle at token boundaries), Reliability (39), Reliability|SwPowerCap (1); max GPU temperature in a window 73 °C.
## Interpretation
1. For the **memory-bound proxy** the answer to "what clock should a bandwidth-bound background run at" is about 1050 MHz here, not 1200: it keeps ≥95% of throughput and saves ~38% of joules per token (0.861 → 0.534 at the energy optimum, board-level counter with the W1 caveats).
2. The **int4 result is probably a property of my kernel, not of Q4 decode.** The dequantisation in `gemv_q4` is scalar (nibble unpack, int→float, fma), with no dp4a/int8 paths, so it is ALU-bound and runs at ~64% of the bandwidth fp16 reaches. Real Q4 engines use integer dot-product instructions and would sit between the two proxies. HC1 therefore says "a dequantisation-heavy kernel has a higher knee", which is true but not a statement about llama.cpp.
   This is the reason the registration defers the llama.cpp validation cell; do not carry the int4 knee into governor claims before that cell runs.
3. The fp16 proxy has half the layers (14 of 28) because 28 do not fit next to the OS; the knee is a property of bytes per FLOP, not layer count, but this is unverified.
4. For fp16 the energy curve is flat between 750 and 1050 MHz (graph mode 0.534 J/token at 750 MHz vs 0.535 at 1050 MHz) while relative throughput rises from 0.935 to 0.959, so the knee and the energy optimum differ by under 1% in energy; the 1050 MHz knee is the better operating point because it keeps the throughput.
## Setbacks / surprises
- A window power note: the unlocked cells run at ~2460–2475 MHz (Reliability-limited, 0.86 J/token for fp16), far from the efficient region, consistent with W1.
- The registered rule "append the C knee (int4 proxy, graph) to B's levels" is vacuous because that knee is `unlocked` (already a B level); see the addendum draft.
## Decisions
None taken here. A B-levels addendum is drafted (experiments/w2_colocation_addendum_B_levels_2026-10-21.md, uncommitted) for Arjun's decision.
## Next
Arjun decides the B-levels addendum; then Experiment B (admin, AC); the llama.cpp validation cell design is still to be registered (dated addendum) before it runs.
