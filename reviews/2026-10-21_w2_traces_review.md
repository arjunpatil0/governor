# Review: Nsight traces / fg_gpu_ms (journal 0019, STATUS at 4f48ea1)
Reviewer: Claude (cloud session). Status key: [AGREE] · [NOTE]

1. [AGREE] Defer the %globaltimer diagnostic until after A and the secondary. Users experience
   end-to-end latency and misses, and A's secondary (SA4 duty sweep, SA2 stretch) measures exactly
   that at host level. Don't drop it, though: whether a foreground frame is preempted mid-kernel or only
   waits before starting decides whether the governor should use slice size or duty cycle as its
   knob. Pre-stated trigger: if SA4's fg slowdown vs duty doesn't track the 1 + d reference, or SA2's k
   is far from 1, register the globaltimer addendum then.
2. [NOTE] The missing CUDA kernel table (children killed before CUPTI flushes) has a cheap fix
   for any future trace: have each child call cudaProfilerStop() (or cuptiActivityFlushAll) right after
   writing its output, before the hang-prone exit. Record it in the trace_cell docstring; no action now.
3. [NOTE] "Packets in flight at the same time" means both contexts had work queued, not that they
   executed concurrently. Without MPS, separate contexts are time-sliced. Make sure journal 0019 doesn't
   read as evidence of concurrent execution.
4. [AGREE] Co-run fg_gpu_ms stays uninterpreted; B report uses latency, miss and completed fractions.
Proceed: A, then the secondary (A2), then part L code with nothing executing during runs.
