# R1 setup (frozen settings)

Committed before the first cell, as `docs/R1_PREREG.md` requires. A change to any value in the first table voids the sweep. The second table holds the values that are chosen from SOLO data in the smoke session and frozen in a separate commit before any loaded-arm cell is run.

## Fixed by the owner (2026-11-11)

| Setting | Value |
|---|---|
| Power | AC |
| Armoury Crate mode | Performance |
| HAGS (hardware-accelerated GPU scheduling) | on |
| GPU mode | Standard (hybrid): frames rendered by the RTX 4070 Laptop are presented through the Radeon 780M |
| Frame cap | NVIDIA Control Panel, Max Frame Rate 60, set for Superposition (the cap is a driver limiter, not vsync) |
| GPU clocks | unlocked; fresh restart, the clock helper is not started, and the harness refuses to start a cell if the helper's pipe is present or if the clock check (a load test, see the prereg) has not passed |
| NVIDIA power cap | the owner states 95 W. The enforced limit is dynamic on this laptop (74.7 to 95.0 W observed within minutes), so it is a recorded covariate, not a per-cell gate: the sweep is refused only if the maximum enforced limit during the clock-check load is below 94 W (check the Armoury Crate mode); see amendments 23 and 24 of the prereg |
| NVIDIA Control Panel | Power management mode: Normal; Superposition Max Frame Rate: 60 |
| Shell | the sweep runs from an elevated PowerShell (PresentMon needs ETW rights); the LLM process is therefore elevated too, in every arm |
| Background | Chrome and tray apps closed |
| Display | no external monitor; laptop panel; hybrid. The display state (nvidia-smi Disp.A), the idle VRAM and the nvidia-smi process list are recorded per cell or at sweep start |
| Game | Unigine Superposition (free Basic edition), installed by the owner from benchmark.unigine.com; folder `C:\Program Files\Unigine\Superposition Benchmark\bin`; the rendering process is `superposition.exe` (`launcher.exe` is only the menu and is never captured) |
| Vulkan SDK (IGPU arm build) | `C:\VulkanSDK\1.4.363.1`, glslc works (shaderc v2026.4) |
| PresentMon | 2.6.0 console build, sha256 b2a706bc6ad475749e3b7e3409263aa1e6906d45bdcf993f6dbc0f660188f1af (enforced) |
| LLM | stock llama.cpp at 620d2225c, Llama-3.2-3B Q4_K_M |
| Seed | 89770043 |

## Frozen after the SOLO smoke (separate commit, before any loaded-arm cell)

| Setting | Value |
|---|---|
| Superposition install path and version | `C:\Program Files\Unigine\Superposition Benchmark\bin\superposition.exe`, version 1.1 (ProductVersion and FileVersion of the executable, sha256 34a0792670445f9f6a576f47a859b9a53af932c5ac69a1cdfc60433778b0f55d) |
| Preset (resolution, quality) | frozen on 2026-11-11 from the SOLO smoke `SOLO_2` (confirmed by the owner): GAME mode, Custom preset, DirectX, Fullscreen off (windowed), 1920x1080, Textures Medium, Shaders Medium, Depth of Field off, Motion Blur off. Measured on that preset: 60.00 fps, frame time p50 16.67 ms and p99 16.73 ms, hitch share 0.00%, GPU busy per frame 6.49 ms median (p95 6.94 ms), so the acceptance rule (GPU busy 6 to 10 ms, hitch share below 1%) holds, at the low end of the range; my forecast assumed about 8 ms, so the UNGATED effect may be smaller than forecast. Not tuned further, by the owner's choice. |
| How the scene is started | GAME mode with the camera left still and no input, one running process (the free edition has no command-line tool and no looped benchmark; the benchmark camera path changes load over time). Departure from the prereg wording "restarted every cell": the game is NOT restarted between cells, because about 35 manual restarts are impractical. Scene drift is checked after the sweep from the GPU busy per frame of the SOLO cells across reps and is reported. |
| Executable PresentMon targets | `superposition.exe` only; `launcher.exe` is the menu and is never captured. The swapchain address changes per run and is not frozen. |
| Number of smoke runs before the freeze | 2 SOLO smoke runs, 0 loaded-arm runs. `SOLO_1` failed the window-continuity check (1,110 of 1,200 frames, one 329 ms stall in the window) and was discarded by the rig; `SOLO_2` passed. |
| Real PresentMon header | committed as `tests/realgame/data/pm_sample_real.csv` (the real header and the first 40 rows of `SOLO_2`, 23 columns, with a test): this build emits the gold-style names `FrameTime`, `GPUBusy`, `GPULatency`, `CPUStartQPC` and has no `FrameType` or `VideoBusy`; PresentMode is `Composed: Copy with GPU GDI` (windowed, composed copy). |

## Observed at setup time (2026-11-11, about 19:50, before any cell, read-only)

The owner's description of the display and of the power cap does not match these readings. They are recorded as measured; the harness's rules apply to what it reads at each cell, not to this table.

| Observation | Value |
|---|---|
| Shell used by the assistant | not elevated (the owner's elevated PowerShell is a separate window) |
| Clock helper | pipe `governor_clock` absent, no helper process visible |
| Idle state | P8, SM 210 MHz, 2.6 W, 47 C, 257 MiB used |
| nvidia-smi display | Disp.A: Off; display_active: Disabled; no `dwm.exe` in the nvidia-smi process list (only explorer.exe and claude.exe, type C+G) |
| nvidia-smi power cap | 90 W in the table, `power.limit` reads N/A, `power.max_limit` 140 W |
| NVML enforced power limit | 92.77 W at first reading (default limit 80 W; constraints 5 to 140 W); readings over the next minutes: 83.7 W idle, 74.7 W in the first second of a load, 95.0 W after about 4 s of load, 93.8 W idle a few minutes after a load |
| `nvidia-smi -q -d POWER` (20:18) | Current Power Limit 92.82 W (dynamic); Default 80.00 W, Min 5.00 W, Max 140.00 W (static fields; whether they change with the Armoury mode is not known) |
| NVML clocks event reasons at idle | 0x1 (GPU idle) |

## IGPU arm build record (2026-11-11)

| Item | Value |
|---|---|
| Source | the pinned llama.cpp tree `third_party/llama.cpp` at 620d2225c, unpatched, `git status --porcelain` empty after the build; build directory `build_vk` (git-ignored) |
| Build | `workloads/background/build_llama_vulkan.bat`: CMake with Ninja, `-DGGML_VULKAN=ON -DCMAKE_BUILD_TYPE=Release -DLLAMA_CURL=OFF -DGGML_NATIVE=OFF -DGGML_AVX2=ON -DGGML_FMA=ON -DGGML_F16C=ON`; Vulkan SDK 1.4.363.1 |
| Timebox | started 14:38 UTC, succeeded on the third attempt at 14:43 UTC, inside the 1 hour. Attempts 1 and 2 failed at the CMake CPU-feature probe (`HAS_AVX_1`: the test executable could not be removed, another process was using it). The third attempt skipped that probe with `GGML_NATIVE=OFF` and explicit AVX2, FMA and F16C flags; these flags affect only the CPU backend, and the iGPU arm offloads all layers to Vulkan. The CUDA build used by the other arms was configured with the default flags. |
| Devices (`llama-cli --list-devices`) | Vulkan0: AMD Radeon 780M Graphics (8049 MiB); Vulkan1: NVIDIA GeForce RTX 4070 Laptop GPU |
| IGPU selection | `GGML_VK_VISIBLE_DEVICES=0`, passed as `--igpu-vk-index 0` |
| Driver check (load only, no decoding) | `EXEC_MODE vulkan device=AMD Radeon 780M Graphics offloaded=29/29 n_layer=28 duty=0` |

## Rehearsal readings (2026-11-11, my non-elevated shell, throwaway directory, not data)

One LLM-alone cell run from the assistant's shell only to find crashes in the harness. These readings informed amendments 26 and 27 and are not results.

| Observation | Value |
|---|---|
| VRAM of the LLM alone, used after READY minus the 454 MiB baseline | 4139 MiB at n_ctx 16384; 3687 MiB at 12288; 3235 MiB at 8192 |
| Temperature over the 80 s LLM cell | 45 C at start, 81 C at the end; about 48 C 2.5 minutes later |
| Throttle reasons | SwPowerCap and a software thermal slowdown (0x20) flagged |
| Throughput and power in the 60 s window | 83.7 tok/s; 93.67 W from the energy counter; `power_rejected` 0 |
| Enforced power limit during the cell | minimum 72.7 W, maximum 95.0 W |

## Readings from the first sessions (2026-11-11)

| Observation | Value |
|---|---|
| VRAM with the game loaded and idle (`SOLO_2`) | 1835 MiB used, against 460 MiB for the idle desktop, so the game takes about 1.4 GB. With the LLM at n_ctx 12288 (3687 MiB) about 2.6 GB of the 8188 MiB remain: no paging is expected |
| nvidia-smi process list, `--llm-alone` run | `dwm.exe` listed on the RTX (type C+G) together with explorer.exe and claude.exe; `display_active` still Disabled. The earlier read at setup showed no `dwm.exe`; the owner's second description of the display (compositor on the RTX) is closer to this reading |
| LLM alone, elevated, game absent (`session2/llm_alone`) | 83.85 tok/s, 95.33 W (energy counter), `power_rejected` 0, 50 to 84 C, enforced limit 84.4 to 95.0 W, SM median 2385 MHz, no context reset |
| SOLO smoke (`SOLO_2`) | 60.00 fps, p50 16.67 ms, p99 16.73 ms, hitch share 0.00%, GPU busy 6.49 ms, 46.6 W, 56 to 62 C, enforced limit 86.4 to 95.0 W |

## Scene stability check (2026-11-11, game alone, no LLM)

A 10-minute PresentMon capture of `superposition.exe` alone (35,765 frames, `data/r1/session2/drift_10min.csv.gz`), taken because two smoke cells minutes apart had shown different GPU busy per frame (6.49 ms in `SOLO_2`, 4.61 ms in `UNGATED_1`, 6.36 ms in `UNGATED_2`). Result: GPU busy per frame, in 10 s bins, ranges from 6.40 to 6.49 ms (a 0.09 ms range, 1% of the median 6.48 ms); frame time p50 16.67 ms, p99 16.76 ms, 0.006% of frames above 25 ms. There is no drift, cycle or step in the game alone over 10 minutes, so the scene is stable and the departure from "restarted every cell" (see above) is not contradicted by this measurement. The change in GPU busy between the two UNGATED smoke cells therefore occurred with the LLM running, and its cause is not established: the sweep records GPU busy per frame for every cell, and it is reported as a result, not corrected.
