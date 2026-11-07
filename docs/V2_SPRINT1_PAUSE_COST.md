# V2 sprint 1: what it costs to make LLM decode pausable at layer boundaries

Branch v2-foreground. One question: if one token's decode is split into G groups of layers with a pause point between groups, how much slower does each token get, and how long is the longest uninterruptible piece? Written in the order it was done; the forecast was committed before any measurement.

## Verdict

(pending: filled in after the measurement)

## Decision rule (fixed before measuring)

- GO: some G has a longest group of at most 2.5 ms and a total per-token overhead of at most 15% against G = 1. Sprint 2 builds the real pausable decode.
- MARGINAL: the overhead at that G is 15 to 30%. Reported for the owner to decide.
- STOP: the overhead is above 30%, or no G gets the longest group below 2.5 ms. Written up as a finding on why layer-level preemption does not pay on WDDM at this scale.

## Path taken

Real split, not a proxy (decided after the feasibility reading below). If the patched build or the driver cannot be made to work, the fallback is the standalone proxy microbenchmark, and this section will say so.

### Feasibility reading (pinned llama.cpp, commit 620d2225c, version 0.7.0)

Where the graph is captured and launched. `ggml_backend_cuda_graph_compute` (ggml/src/ggml-cuda/ggml-cuda.cu, line 4684) decides whether to use a CUDA graph for the whole ggml compute graph of one token. If it does, it begins stream capture (`cudaStreamBeginCapture`, line 4739), evaluates every node in `ggml_cuda_graph_evaluate_and_capture` (line 4449), ends capture (`cudaStreamEndCapture`, line 4638), instantiates or updates the executable graph and launches it once with `cudaGraphLaunch` (line 4659). The captured graphs are kept in a map keyed by the first node of the cgraph (`ggml_cuda_graph_get_key`, `cuda_graphs` in common.cuh line 1463), so several graphs per backend context already work if the cgraph handed in differs.

(a) Minimal patch. In `ggml_backend_cuda_graph_compute`, when a group count G above 1 is requested (an environment variable, default off so the stock behaviour is unchanged), partition `cgraph->nodes` into G contiguous ranges that end after the node named `l_out-<layer>` (llama.cpp names each layer's output that way), build a view of each range with the existing `ggml_graph_view(cgraph, i0, i1)`, run each view through the same capture and launch path (each view has its own first node, hence its own graph key), and between groups synchronise the stream and call a host hook. The hook receives the group index, host launch and completion times and the CUDA-event duration, and is where the frame-slack hint is read. About 90 to 120 lines in ggml-cuda.cu plus a small exported setter for the hook in ggml-cuda.h. A new driver (a copy of the decode driver, with the hook installed) is about 150 lines. The change goes in a copy of the source tree and a separate build directory, so the pinned build and the v1 evaluation driver stay untouched.

(b) State across a pause. Activations live in the compute buffer that ggml's graph allocator plans once for the whole graph, and the KV cache lives in persistent backend buffers. Splitting the node list keeps the node order, so nothing is freed or reused earlier than in the whole graph, and no copies are needed. What a pause does cost is that the stream drains: to hand the GPU back, group i must have finished before group i + 1 is launched, which needs a stream synchronise and a fresh graph launch per boundary.

(c) What forces graphs off. The environment switch `GGML_CUDA_DISABLE_GRAPHS`; a mul_mat_id node that needs a synchronise (mixture-of-experts models, not the 3B); node properties that change from one token to the next (the code then resets its warm-up and runs the nodes directly until the graph is stable again); and the capture lock around `cudaStreamBeginCapture`. For this 3B the graph is stable between tokens except when the padded KV length changes, which the 300-token runs rarely cross. A split view has no `uid`, so its node properties are compared on every call, which is a host-side cost per group that is part of what the experiment measures.

## Forecast (committed before measuring)

Model: the chunking project's barrier model, `t = a + b x max_cost + c x sum of per-chunk slowest-warp terms` (R-squared 0.97 to 0.98, `variance_gpu_project/ARCHIVE_NOTE.md`), in which every chunk boundary is a global barrier and costs the straggler tail of the chunk that ends. For decode the same structure appears as a drained stream at each pause point. A kernel graph inside one CUDA graph launches its kernels back to back, so a boundary adds three things that a single graph does not have: the wake-up of the host after the stream synchronise, the submission of the next graph through the WDDM kernel-mode driver, and the tail of the last kernel of the group running alone on the GPU. I take 100 microseconds per boundary as the central estimate (range 50 to 200), from the 2 to 34 ms of host overhead per run that the chunking project measured at chunk counts in the tens to hundreds. Baseline: 97.25 tok/s at the 1500 MHz lock (`data/w2_L_results.md`), so 10.28 ms per token. The token is not uniform over layers: the output projection at the end costs about 0.8 ms (a roughly 200 MB tied embedding at the memory bandwidth of this GPU), leaving about 0.33 ms per layer, so the last group is always the longest from G = 7 up.

| G | boundaries | forecast overhead (us per token) | forecast slowdown | forecast longest group (ms) |
|---|---|---|---|---|
| 1 | 0 | 0 | 0% | 10.3 |
| 2 | 1 | 100 | 1.0% | 5.4 |
| 4 | 3 | 300 | 2.9% | 3.1 |
| 7 | 6 | 600 | 5.8% | 2.1 |
| 14 | 13 | 1300 | 12.6% | 1.5 |
| 28 | 27 | 2700 | 26.3% | 1.1 |

By this forecast the rule gives GO at G = 7 (longest group 2.1 ms, overhead about 6%), and the overhead only reaches the marginal band at G = 28. The forecast would be wrong in a way that matters if the per-boundary cost is nearer 400 microseconds, which puts G = 7 at about 23% (marginal).

## Measured

(pending)

## Simulator estimate

(pending)

## Limitations

(pending)
