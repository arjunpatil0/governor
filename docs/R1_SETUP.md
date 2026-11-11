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
| NVIDIA power cap | 95 W as stated by the owner; the harness refuses to start a cell if the enforced power limit read from NVML is not within 1 W of 95 W (see the observed values below) |
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
| Superposition install path and version | (to be recorded) |
| Preset (resolution, quality) | (to be chosen from SOLO data so that GPU busy per frame is 6 to 10 ms at 60 fps with a hitch share below 1%) |
| How the scene is started | (benchmark sequence or static camera, restarted every cell) |
| Executable PresentMon targets | (to be recorded) |
| Number of smoke runs before the freeze | (to be recorded) |
| Real PresentMon header | (committed with the freeze, replacing the synthetic sample) |

## Observed at setup time (2026-11-11, about 19:50, before any cell, read-only)

The owner's description of the display and of the power cap does not match these readings. They are recorded as measured; the harness's rules apply to what it reads at each cell, not to this table.

| Observation | Value |
|---|---|
| Shell used by the assistant | not elevated (the owner's elevated PowerShell is a separate window) |
| Clock helper | pipe `governor_clock` absent, no helper process visible |
| Idle state | P8, SM 210 MHz, 2.6 W, 47 C, 257 MiB used |
| nvidia-smi display | Disp.A: Off; display_active: Disabled; no `dwm.exe` in the nvidia-smi process list (only explorer.exe and claude.exe, type C+G) |
| nvidia-smi power cap | 90 W in the table, `power.limit` reads N/A, `power.max_limit` 140 W |
| NVML enforced power limit | 92.77 W (default limit 80 W; constraints 5 to 140 W); the owner stated 95 W, so a cell started now would be refused by the power-cap rule |
| NVML clocks event reasons at idle | 0x1 (GPU idle) |
