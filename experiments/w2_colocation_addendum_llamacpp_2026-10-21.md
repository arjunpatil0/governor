# Addendum to w2_colocation.yaml: llama.cpp validation of the decode proxy (decisions by Arjun 2026-10-21 applied; NOT yet committed: registered after B's results are committed)
Date: 2026-10-21 · To be registered BEFORE any llama.cpp measurement exists, and to run right after Experiment B · Registration: b86d36e · C: f6f61ec, journals 0014/0015
Fulfils experiment_C.real_engine_validation in the yaml ("one llama.cpp cell (3B, Q4)... design registered in a dated addendum BEFORE it runs. Real CUDA build, no CPU fallback").
Registered after Experiment B results were committed (c51b499) and before any llama.cpp data or build exists.

## Why
Experiment C's int4 proxy lacks construct validity for Q4 decode (scalar dequantisation, clock-proportional throughput; journal 0015). Only the fp16 proxy's result (knee 1050 MHz, 0.96 throughput at 0.535 J/token against 0.861 unlocked) is claimed. This addendum measures where a REAL engine's knee lies so that the governor's decode assumptions rest on a real kernel stack.

## Verified facts (checked 2026-10-21; nothing downloaded or built yet)
- llama.cpp: github.com/ggml-org/llama.cpp reachable; tag v0.7.0 resolves to commit 620d2225cc436ab0b001e3200e590e3b286ef9ab (git ls-remote). Pin this commit; log the commit hash in meta.
- Model: huggingface.co/bartowski/Llama-3.2-3B-Instruct-GGUF exists, not gated, license "llama3.2" (the Llama 3.2 Community License; Arjun to accept before download). File Llama-3.2-3B-Instruct-Q4_K_M.gguf, 2,019,377,696 bytes, sha256 6c1a2b41161032677be168d354123594c0e6e67d2b9227c84f296ad037c728ff (HF tree API). The sha256 is re-verified after download.
- Toolchain on this machine: cmake and ninja ship inside VS BuildTools (Common7\IDE\CommonExtensions\Microsoft\CMake); nvcc 13.1 with MSVC 14.50 needs `-allow-unsupported-compiler`, as for workloads/background/build.bat. CUDA arch sm_89. 240 GB free on C:.

## Build (outside the tracked tree)
third_party\llama.cpp (gitignored), `cmake -G Ninja -DGGML_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES=89 -DCMAKE_CUDA_FLAGS=-allow-unsupported-compiler -DCMAKE_BUILD_TYPE=Release`, built from the developer prompt of VS BuildTools. If the pinned commit does not build against CUDA 13.1 the build fails loudly and the addendum is revised before any data (no silent fallback to CPU or to another version).
Execution-mode check, fail loudly: the run log must show all layers offloaded to the GPU (n_gpu_layers = all) and `ggml_cuda_init` finding the RTX 4070 Laptop; a build without CUDA, or any layer left on CPU, aborts the cell.

## Measurement design (same protocol as Experiment C so that results are comparable)
- Workload: Llama-3.2-3B-Instruct Q4_K_M, greedy decoding of a fixed prompt, KV cache reset per cell. The prompt is the first 512 tokens of a fixed text file committed under data/llama/ (sha256 logged); decoding then runs token by token.
- Driver: a small C++ program linked against libllama (`workloads/background/llama_decode_bench.cpp`) that decodes tokens one at a time and records each token's end time on the QPC timeline, as w2_decode_run does. Rationale: `llama-bench` reports aggregates only, so energy and clock samples could not be aligned to a fixed 4 s window. If libllama's API at the pinned commit makes the driver impractical, the fallback is `llama-bench -p 0 -n N -r R` with whole-process timing, and the addendum is revised and re-reviewed before data.
- Harness: a new part `L` in experiments/w2_colocation/run.py with a child role `llama`; cells = 9 SM levels [600, 750, 900, 1050, 1200, 1350, 1500, 1800, unlocked] x 10 blocks = 90 cells; memory clock locked at 8001 MHz; 1.5 s pre-roll, 4 s window, 2 s idle; the same 20 Hz clock/power sampling, exactly two energy-counter reads per window, thermal gate <= 68 C, AC and admin required, clean committed tree; clocks reset in a finally block.
- Estimated run time: about 25 minutes (cell structure: model load + 5 s lead + 5.5 s + idle; an estimate, not a measurement).
- Tests first: pure parts (cell list, token-window extraction, knee/energy summaries) get RED/GREEN tests before the run; the C++ driver gets a GPU integration test that checks token ids are produced and execution mode is GPU.

## Outcomes and decision rules (pre-registered)
- Tokens/s in the window, relative throughput vs the same block's unlocked cell, joules per token (energy-counter delta / tokens), effective GB/s (model file size x tokens/s).
- HL1 (descriptive classification of the knee, same definition as C: lowest level with median relative throughput >= 0.95, 90% block-bootstrap CI): the real engine is called "fp16-proxy-like" if its knee <= 1200 MHz, "intermediate" if 1200 < knee <= 1800 MHz, "int4-proxy-like" if its knee is above 1800 MHz or unlocked.
- HL2 (descriptive): the energy optimum and J/token there against unlocked; the throughput retained at the C fp16 knee (1050 MHz) and at the B reference clock 1800 MHz.
- HL3 (validity): the greedy token sequence must be identical in every cell of the same block (a correctness check that clock locks change timing, not results); any block with differing sequences is flagged, not dropped.
- The result is a number with a CI and a classification, not a test of significance; no multiplicity claim.

## Limitations to state in the results
One engine at one pinned commit, one model, one quantisation (Q4_K_M), batch 1, context ~512 to ~900 tokens; Q4_K_M kernels differ from the Q4_0 and other formats; no prompt-processing phase is measured (decode only); board-level energy counter with the W1 caveats; HAGS ON.

## Decisions (Arjun, 2026-10-21)
1. Arjun accepts the Llama 3.2 Community License and approves the 2.0 GB Q4_K_M download (sha256 re-verified afterwards).
2. Q4_K_M only (realistic deployment format). No Q4_0 run.
3. Custom C++ driver, with a pre-registered **driver sanity check** before any validation data: at the unlocked clock, driver tokens/s must be within +/-5% of `llama-bench` (same build, same model, same decode length, memory clock locked at 8001 as in the cells). If it fails, the driver is fixed and the check repeated before any run; the check's numbers are logged to data/ and are not part of the HL results.
4. Build with `-allow-unsupported-compiler`. If the pinned llama.cpp does not build, fall back to the official prebuilt Windows CUDA release of the same tag (v0.7.0) and build only the driver against its llama.dll; the build path used (source build or prebuilt) is recorded in meta. Any other deviation (different tag, CPU build) needs a revised addendum before data.
5. Order of work: nothing is downloaded or built while Experiment B runs (it would disturb the GPU/CPU). After B's results are committed: register this addendum (remove the .git/info/exclude line, drop `_DRAFT` from the name), then download, build, run the sanity check, and stop before the full validation run.
