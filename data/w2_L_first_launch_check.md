# Part L first-launch check (double-execution effect; no GPU)

Run 20261021T205034Z: 90 cells (10 blocks x 9 levels; expected 90).
- Cells whose logged tokens reproduce results.tokens exactly with a 4.0 s window starting 1.0-2.2 s after the first token: 90 of 90 (window offset range 1.00-1.56 s).
- Cells with duplicated token timestamps: 0; with non-monotone timestamps: 0.
- Cells with a non-empty flags column: 0.

First cell (block 0, first level run) against the other blocks of the same level (total tokens logged / span of the log in s / tok/s):

| level | b0 tokens | others median | b0 span | others span | b0 tok/s | others median tok/s | b0 / others |
|---|---|---|---|---|---|---|---|
| llama_1350 | 537 | 537 | 5.593 | 5.583 | 95.75 | 95.50 | 1.003 |
| llama_600 | 348 | 347 | 5.581 | 5.577 | 62.25 | 62.00 | 1.004 |
| llama_1200 | 524 | 521 | 5.588 | 5.581 | 93.25 | 93.00 | 1.003 |
| llama_900 | 470 | 467 | 5.583 | 5.579 | 83.75 | 83.25 | 1.006 |
| llama_1500 | 548 | 546 | 5.574 | 5.581 | 98.25 | 97.25 | 1.010 |
| llama_1050 | 503 | 498 | 5.577 | 5.583 | 89.75 | 89.00 | 1.008 |
| llama_1800 | 559 | 557 | 5.577 | 5.582 | 99.75 | 99.25 | 1.005 |
| llama_750 | 418 | 414 | 5.573 | 5.582 | 74.75 | 74.00 | 1.010 |
| llama_unlocked | 557 | 551 | 5.553 | 5.548 | 102.00 | 100.75 | 1.012 |

- llama_decode_bench.exe last written (mtime) 2026-10-21 13:55:06.378007889+00:00; part L smoke meta(s) ['2026-10-21 20:40:57.771327496+00:00']; full run meta 2026-10-21 20:50:34.124293804+00:00.
- So the binary had been executed before the first measured cell of the full run (smoke run and earlier sanity runs), i.e. the first launch of that hash was not a measured cell.

Reading: no sign of duplicated or missing token-log lines or cells; block 0 is within the range of the other blocks (b0/others about 1.003-1.012 in tok/s, the same sign at every level, i.e. a slightly faster first block, not a duplicated one). The driver writes its output once at the end and uses no named shared objects, so the mechanism seen with the named-ring probe (journal 0037) has no object to duplicate here. Not checked: whether the W2 DLLs (loaded in-process) were scanned/emulated; they have no named-object side effects either.