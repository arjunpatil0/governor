# llama.cpp driver sanity check (addendum: driver tokens/s within +/-5% of llama-bench at unlocked)
Date 2026-10-21 · llama.cpp commit 620d2225cc43 (tag v0.7.0), SOURCE BUILD (CUDA, sm_89, -allow-unsupported-compiler; no prebuilt fallback needed) · model Llama-3.2-3B-Instruct-Q4_K_M.gguf (sha256 verified) · RTX 4070 Laptop, unlocked clocks (SM 1980 MHz idle at start, mem 8001 MHz; NOT run as admin, so no clock locks; the card's memory clock is 8001 MHz unlocked) · AC power not logged for this check.
- llama-bench: `-p 0 -n 256 -d 512 -r 5 -ngl 99` -> 104.62 tok/s (stddev 0.12) [data/llama/sanity/bench.csv]
- driver: 5 runs, first 256 tokens after a 512-token prefill: 101.4, 102.0, 101.0, 99.4, 99.0 -> median 101.01 tok/s [data/llama/sanity/drv_*.csv]
- ratio driver/llama-bench = 0.965 (-3.5%): **PASS** (limit +/-5%). The driver measures per-token end times after greedy sampling on the host, which llama-bench does not.
Limits: 5 repetitions at unlocked clocks only; the check is not part of the HL results.
