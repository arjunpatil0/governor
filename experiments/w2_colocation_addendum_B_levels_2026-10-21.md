# Addendum to w2_colocation.yaml: Experiment B levels after Experiment C (DRAFT for review, not committed)
Date: 2026-10-21 · Written BEFORE any Experiment B data exists · Registration: b86d36e · C results: f6f61ec (data/w2_C_results.md), journal 0014

## What the registration says
experiment_B.clocks: "SM level in [900, 1200, 1500, 1800, unlocked]. The knee level found in Experiment C (int4 proxy, graph) is appended by an addendum dated before B's first run if it is not already in the list."

## What Experiment C found
| proxy (graph mode) | knee (>= 95% of unlocked throughput) | energy optimum |
|---|---|---|
| int4, 28 layers | unlocked | 1500 MHz |
| fp16, 14 layers | 1050 MHz | 750 MHz (flat between 750 and 1050: 0.534 vs 0.535 J/token) |

## Applying the registered rule literally
The int4 proxy's knee is "unlocked", which is already a B level. Nothing is appended. B stays at 5 levels, 30 cells per block.

## Proposal (needs Arjun's decision)
Add **1050 MHz** to B as a descriptive level: the lowest clock at which the memory-bound proxy keeps >= 95% of its throughput, i.e. the clock a governor would choose for a bandwidth-bound background. B's question (what a device-wide lock does to a compute-bound foreground) is then answered at the decision-relevant clock and not only at neighbouring grid points.
- Not part of any test family: HB1 and HB2 stay on {900, 1200, 1500} against the 1800 MHz reference, Holm families unchanged (so no change in power or in the registered decision rules).
- Reported descriptively with the same measures (service time ratio to 1800, deadline-miss fraction, latency percentiles marked non-stationary under overload, power saved). For the ratio, the W1 prediction is interpolated between its 900 and 1200 MHz levels (0.366, 0.488), i.e. a relative throughput of about 0.427 and a service ratio to 1800 MHz of about 0.732 / 0.427 = 1.71; this is an interpolation, labelled as such, and is not tested.
- Cost: 6 more cells per block (3 frame kinds x 2 backgrounds), 30 -> 36; estimated +20% run time (about +16 minutes by the cell structure; an estimate, not a measurement). `design.py` B_LEVELS and its test would be updated before the run.

## Alternatives
1. Keep B at 5 levels (the literal reading). Cheapest; B then has no point at the fp16 knee, and the nearest lower level is 900 MHz.
2. Also add 750 MHz (the fp16 energy optimum): rejected, because it adds 6 more cells for a point whose energy is within 1% of the 1050 MHz point.

## Caveat that applies either way
The int4 proxy appears compute-bound because of a naive scalar dequantisation kernel (journal 0014), so its "knee = unlocked" must not be read as a property of real Q4 decode. The llama.cpp validation cell (registered as a future addendum) is what would tell us where a real engine's knee is; B's levels are not conditioned on it.
