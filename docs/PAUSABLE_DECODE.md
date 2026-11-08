# Pausable decode: how it works and how to build it

This document is for an engineer who wants to reproduce or extend the v2 work: llama.cpp decode that can stop between layer groups and resume when a real-time app on the same GPU says there is room. The measurements are in `docs/report/REPORT_V2.md` and the four sprint documents (`docs/V2_SPRINT1_PAUSE_COST.md` to `docs/V2_SPRINT4_LOW_SLACK.md`). This document describes the mechanism only, as of release v2.0.0 (2026-11-08); no hardware was run for it.

## The problem the mechanism solves

llama.cpp decodes one token as one CUDA graph: a single launch that keeps the GPU busy for 10.1 ms (Llama-3.2-3B Q4_K_M, 1500 MHz lock) or 21.0 ms (Llama-3.1-8B). A 60 fps app that needs the GPU for 7 ms of every 16.67 ms frame leaves a gap of 9.67 ms, so a 10.1 ms token never fits, and a gate that starts only whole tokens that fit starts none. A pause point inside the token lets the decode use a gap that is shorter than a token: it runs a group of layers, checks the app's frame hint, and runs the next group only if that group is predicted to finish before the next frame is due.

## The token as G CUDA graphs

The patch (`workloads/background/pause_patch/llama_pause_groups_620d2225c.patch`) changes one function in `ggml/src/ggml-cuda/ggml-cuda.cu`, `ggml_backend_cuda_graph_compute`, which receives the ggml compute graph of one token and decides whether to run it as a CUDA graph. The original is renamed `ggml_backend_cuda_graph_compute_whole` and left unchanged. A new function with the old name checks the environment variable `GGML_CUDA_PAUSE_GROUPS`. With the variable unset or at 1 the new function calls the old one and nothing else happens, so the stock behaviour is untouched. With G above 1 it splits the token as follows.

llama.cpp names the output of every transformer layer `l_out-<layer>`. The patch scans `cgraph->nodes` for those names and records the index of each layer's last node. With L layers (28 for the 3B, 32 for the 8B) it cuts the node list into G contiguous ranges, each ending after a layer boundary: group g ends after layer `(g + 1) * L / G - 1`, and the last group also takes every node after the final layer, which is the output norm and the output projection (the output head). If the graph has fewer than G layer-output nodes the patch runs it whole.

Each range is run through `ggml_backend_cuda_graph_compute_whole`, the unchanged capture and launch path. That path keeps its captured CUDA graphs in a map keyed by the first node of the graph it is given, so each group, whose first node differs, gets its own CUDA graph with no change to the map. After the first token the groups are replayed with `cudaGraphLaunch`, as the whole-token graph was. Keeping the graphs matters: turning CUDA graphs off made the token 14.2% slower (11.58 ms against 10.14 ms) in sprint 1, against 2.2% for 14 groups.

### The ggml_graph_view workaround

The obvious way to hand a range of nodes to the old path is `ggml_graph_view(cgraph, start, end)`, which returns a graph that points into the parent's node array. That function is not exported from `ggml-base.dll`, and the first link of the patched build failed on it. The patch builds the same view by copying the `ggml_cgraph` struct and setting the fields the function would set: `size = 0`, `n_nodes = end + 1 - start`, `n_leafs = 0`, `nodes = cgraph->nodes + start`, and null `grads`, `grad_accs` and `leafs`, with `uid = 0`. A view with `uid` 0 has its node properties compared on every call, and that host-side cost is inside the measured 2.2%. If a later ggml exports the function, the copy can be replaced by a call.

State across a pause needs no copying. Activations live in the compute buffer that ggml's graph allocator plans once for the whole graph, and the KV cache lives in persistent buffers. Splitting the node list keeps node order, so nothing is freed or reused earlier than in the whole graph. The greedy tokens of the split runs were identical to the stock run at every G tried (the same 320 tokens in all nine configurations of sprint 1).

## The host sync and the hint check

After each group the patch records two CUDA events around the launch, calls `cudaStreamSynchronize` on the backend's stream, reads the host clock, computes the group's GPU time from the events and calls a host hook:

```
typedef void (*ggml_backend_cuda_group_hook_t)(int group, int n_groups, double t_launch_s,
                                               double t_done_s, float gpu_ms, void * user);
void ggml_backend_cuda_set_group_hook(ggml_backend_cuda_group_hook_t hook, void * user);
```

The stream synchronise is the pause point: when it returns, the GPU has nothing of ours queued, and the host decides when the next group launches by deciding when to return from the hook. The hook runs on the decode thread, so returning late is the whole mechanism. Times are `steady_clock` seconds on the host. The host-visible gap between a group's completion and the next launch is about 1 microsecond, and the hint check takes under 1 microsecond. Sprint 1 checked that each boundary is a real pause point by forcing a 2 ms busy-wait in the hook at every boundary: G = 4 rose by 6.07 ms (expected 6.0) and G = 7 by 12.17 ms (expected 12.0).

The reference driver, `workloads/background/llama_handover_bench.cpp`, installs a hook that reads the frame-hint record (`docs/FRAME_HINT_SPEC.md`: busy flag, next deadline and update time in a 40-byte seqlock mapping) and waits until the rule of section 7 of that spec holds: the app is not busy and `now + predicted_group_time + guard <= next_deadline`. The wait is a spin on `YieldProcessor`. A `Sleep(1)` wake-up comes in 1.5 to 2 ms steps and sleeps through a gap that is about 1 ms wide; with it the whole-token baseline delivered 1.5 tok/s where the registered v1 setting delivered 19.97 (sprint 2, first run, kept in `data/v2/s2` and marked superseded). The guard is the early-start margin. The driver's built-in default is 0.5 ms; every measurement in the report sets it explicitly through `GUARD_MS` (0 in sprints 2 and 3, 0 and 1.0 in sprint 4). The same rule also runs once before the first group of each token, so a token is gated by the same code whatever G is.

## Per-group duration prediction

The gate needs to know how long the next group will take, and groups differ. For the 3B at 14 groups a layer group takes about 0.7 ms and the last group, which holds the output head, about 1.9 ms. The driver keeps one estimator per group index (`g_est`, one entry per group; one entry for the whole token at G = 1). Each is the median of that group's last 8 clean durations, where a duration is clean if the group ended before the deadline it was gated against, so a group that overran does not enter the median. Until the first clean duration exists the estimate is an exponentially weighted average of the durations seen (0.9 old, 0.1 new). The duration is host launch to host completion, so it includes launch and synchronise latency.

One property matters when gaps are tight: after a run of overruns the median can lag the true duration until clean groups return, because the overrun groups are excluded. A p90 predictor in place of the median plus a fixed guard is the obvious refinement; it was not built.

## Applying the patch and building

The patch is against llama.cpp commit `620d2225cc436ab0b001e3200e590e3b286ef9ab` ("llama.cpp : bump version to 0.7.0 (#30603)"), the pinned version of this repository. It touches two files: `ggml/include/ggml-cuda.h` (the hook typedef and setter, 4 lines) and `ggml/src/ggml-cuda/ggml-cuda.cu` (about 60 lines). `git apply --check` passes on a clean checkout of that commit, and applying it gives files byte-identical to the patched tree used for every v2 measurement.

```
git clone https://github.com/ggml-org/llama.cpp third_party/llama.cpp_v2
git -C third_party/llama.cpp_v2 checkout 620d2225cc436ab0b001e3200e590e3b286ef9ab
git -C third_party/llama.cpp_v2 apply ../../workloads/background/pause_patch/llama_pause_groups_620d2225c.patch
workloads\background\build_llama_v2.bat          (CMake and Ninja, CUDA architecture 89, Release, own build directory)
workloads\background\build_llama_handover.bat    (builds llama_handover_bench.exe against it)
```

`workloads/background/pause_patch/apply_pause_patch.py <llama.cpp dir>` makes the same edit by text substitution and was the tool used for the measurements; the `.patch` file is its output. The build files assume Visual Studio Build Tools 18 (edit the `vcvars64.bat` path in the `.bat` files for another install) and an Ada GPU (architecture 89, the RTX 4070 Laptop), and they pass `-allow-unsupported-compiler` to nvcc. The pinned, unpatched build in `third_party/llama.cpp` and the v1 driver executable are not touched by any of this.

To use the patch from your own code: set `GGML_CUDA_PAUSE_GROUPS` before the first `llama_decode`, resolve `ggml_backend_cuda_set_group_hook` with `GetProcAddress` on `ggml-cuda.dll` (the driver does, and exits if the symbol is missing, so it cannot run a stock build by mistake), install a hook that blocks until your gate opens, and decode with batch size 1. Each group's CUDA graph is captured on first use, so run a few ungated tokens first; the driver runs three.

## What is not done

Prefill is not made pausable. The measurements concern single-token decode. Sprint 1 states that prefill was not split, and the driver prefills once, before the measured window starts. Reading the patch, it splits any graph that has at least G layer-output nodes, so a prefill batch run in the same process with the variable set would also be cut into groups and synchronised. I did not run or check that case, and gating a prefill of a long prompt, hundreds of milliseconds of GPU work, has not been designed.

The output head is the floor under the longest uninterruptible piece. At layer granularity the last group is its layers plus the output projection: about 1.3 ms of head for the 3B and about 2.4 ms for the 8B, against about 0.3 ms and 0.63 ms for one layer. With 14 groups the longest piece is 1.95 ms for the 3B and 3.61 ms for the 8B; with 28 groups, 1.63 ms and 2.99 ms. No group count gets the 8B below about 3 ms. Splitting the output projection by rows would lower the floor and was not tried.

Other limits. Graphs are re-captured when the padded KV length changes, which 300-token runs did not exercise at length. Mixture-of-experts models whose `mul_mat_id` nodes need a synchronise are not covered, and the models used are dense. The gate has no power control: with the 14-group gate the card draws 57 to 60 W at a locked 1800 MHz. The foreground in every measurement is a synthetic kernel, not a renderer. Windows with WDDM is the only platform used, and its 0.37 ms time slice sets how short a pause must be to matter (sprint 2).

## Where the code is

| What | Where |
|---|---|
| CUDA patch (the mechanism) | `workloads/background/pause_patch/llama_pause_groups_620d2225c.patch`, `apply_pause_patch.py` |
| Decode driver with the hint gate | `workloads/background/llama_handover_bench.cpp` |
| Driver that only measures pause cost | `workloads/background/llama_pause_bench.cpp` |
| Frame-hint record and gate rule | `docs/FRAME_HINT_SPEC.md` |
| Cell runners and analysis | `tools/handover_cell.py`, `tools/jitter_cell.py`, `tools/slack_cell.py`, `tools/*_analyze.py` |
| Headline figure | `tools/v2_figure.py` |
