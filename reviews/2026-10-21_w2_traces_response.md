# Response to reviews/2026-10-21_w2_traces_review.md (Claude Code, 2026-10-21; review file untouched)
1. Defer globaltimer diagnostic: AGREED (Arjun too). Pre-stated trigger recorded in STATUS.md: if SA4's fg slowdown vs duty does not track the 1 + d reference, or SA2's k is far from 1, a globaltimer addendum is registered BEFORE that diagnostic runs. Not dropped.
2. cudaProfilerStop()/cuptiActivityFlushAll before the exit hang: NOTED; recorded in the trace_cell.py docstring (comment only, no behaviour change, no execution). Not implemented.
3. "In flight" is not "concurrent execution": journal 0019 already says "both contexts have work queued, NOT that kernels execute concurrently" and that the traces cannot show switch-in/out; journals are append-only, so no edit; this response restates it: separate contexts without MPS are time-sliced.
4. Co-run fg_gpu_ms uninterpreted: AGREED; unchanged.
Proceed: A, then A2, then part L code (nothing executing during Arjun's runs).
