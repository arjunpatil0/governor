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
| GPU clocks | unlocked; the owner runs `nvidia-smi -rgc` first, the clock helper is not running, and the harness refuses to start a cell if the SM clock is locked |
| Shell | the sweep runs from an elevated PowerShell (PresentMon needs ETW rights); the LLM process is therefore elevated too, in every arm |
| Background | Chrome and tray apps closed |
| Game | Unigine Superposition (free Basic edition), installed by the owner from benchmark.unigine.com; install path and version recorded below |
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
