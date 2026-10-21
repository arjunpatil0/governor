# 0015 — B levels decided; construct-validity statement for the int4 proxy; plan for the llama.cpp validation
Date: 2026-10-21 · Phase: W2 (between Experiments C and B) · Author: Claude Code (decisions by Arjun)
## Question
What should Experiment B include after C's results, and what exactly may and may not be concluded from C?
## Decisions (Arjun, 2026-10-21)
1. **B gets 1050 MHz as a descriptive level, exactly as the addendum proposed** (experiments/w2_colocation_addendum_B_levels_2026-10-21.md, committed with design.py): B_LEVELS = 900, 1050, 1200, 1500, 1800, unlocked; 36 cells per block; HB1 and HB2 stay on {900, 1200, 1500} against 1800, Holm families unchanged. 1050 is the fp16 proxy's knee (journal 0014).
   The 1050 W1 prediction is a linear interpolation between W1's 900 and 1200 MHz levels (service ratio to 1800 ≈ 1.71) and is reported, never tested.
2. **Main finding of Experiment C: the fp16 proxy.** At 1050 MHz it keeps 0.96 of its unlocked throughput at 0.535 J/token against 0.861 J/token unlocked (about 38% lower; board-level energy counter, W1 addendum caveats apply). Source: data/w2_C_results.md, run data/raw/w2_C/20261021T085528Z.
3. **Construct validity of the int4 proxy, stated explicitly.** HC1 is supported statistically (int4 knee above fp16 knee in 10 of 10 blocks), but the int4 proxy lacks construct validity for Q4 decode: its dequantisation is scalar and its throughput is clock-proportional (relative throughput 0.743 at 1800 MHz against 1800/2460 = 0.732). Only the direction (more ALU work per byte raises the knee) is supported; the magnitude does not transfer. The int4 knee must not be used in any governor claim. The same text is now generated into data/w2_C_results.md by `report_C`.
4. **Plan: a llama.cpp validation addendum runs right after B** (3B Q4, a real CUDA build, the same 9 levels, memory locked at 8001, 10 blocks). A draft is prepared and kept uncommitted until Arjun has had it reviewed.
## What this changes
- The decode-relevant clock for a bandwidth-bound background is about 1050 MHz on this machine (not the 1200 MHz assumed in 0006), measured on a proxy that is bandwidth-limited by construction. Whether real Q4 decode behaves like fp16 or like int4 or in between is open until the validation cell.
- Governor design claims about decode must wait for the validation addendum; B still answers the foreground side (what the lock costs a compute-bound foreground) independent of that.
## Next
Experiment B (admin, AC, clean tree), then the llama.cpp validation addendum review and run.
