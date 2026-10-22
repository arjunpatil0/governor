# 0031 — Addendum 3 registered (verified witness blocks, 3-bpsm controls); 17-cell smoke
Date: 2026-10-22 · Phase: W2 · Author: Claude Code · Review: reviews/2026-10-22_G_witness_review.md · Response: reviews/2026-10-22_G_witness_response.md · No full G run started.
## Done (commits)
- Addendum 3 registered (renamed from _DRAFT; text: witness blocks for fg and bg, %smid verification with the 3-earliest-per-SM fallback, validity gate, g_T4_3bpsm + g_bgalone_3bpsm, concurrency rule). Slip: b50cc2c holds the draft text under the final name (a git mv + commit ran while the Write of the registered text was denied); 675e861 holds the registered text; no data existed between them.
- Controls built test-first: design cells (17 per block), `calibrate(..., bps=3)` (GPU test), run.py passes blocks-per-SM to the fg/bg children and calibrates `fma3` for part G; analysis: `witness_mask` (nominal/fallback/excluded), `concurrency_verdict`, gate and control paragraph in the report. Suite 183 passed.
## Smoke (17 cells, unlocked clocks, one block; data/raw/w2_G_smoke/20261022T055838Z local; reports data/w2_G_smoke_report.md and ..._allblocks.md; NOT results)
- Calibration at 1800 MHz: fma 4.86e-5 ms/unit (6 per SM), fma3 2.52e-5 ms/unit (3 per SM).
- Witness set: every launch used the nominal blockIdx < 108 set (0 fallback, 0 excluded) in all timeline cells. Gate (i): bgalone witness preempted fraction 0.000% (6 per SM grid, 132,192 blocks) and 0.000% (3 per SM, 135,648 blocks).
- Overflow: 0 untrusted blocks, 0 gaps lost. Coverage: R0.5 41% of fg requests inside the recorded interval, R1 92%, others >= 99.5%.
- Control: g_T4_3bpsm 0 overlaps in 43,092 fg blocks; main cells 11,070 of 870,048 (same-SM 2,369 of them). By the registered rule the main-cell overlaps would be reported as UNEXPLAINED, not as concurrency. The control's bg blocks show 22.6% preemption: context switching is visible without arbitration. q 0.379 ms, s 0.129 ms, 146 negative-s transitions of 3,448 in the main cells (smoke, no prediction judged; P4/P5/P6 unchanged).
- Odd, not investigated: g_R1 p99 arrival-to-GPU-start 13.8 ms in this smoke (others 0.65-1.04 ms); unlocked clocks and one block, one cell flagged start_temp_not_reached.
## Not claimed
Why the main-cell overlaps exist when the 3-bpsm control has none (candidates: residual arbitration effects for witness blocks at 6 per SM, switch staggering that the control's smaller grid does not show); any prediction outcome.
