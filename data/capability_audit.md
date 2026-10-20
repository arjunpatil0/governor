# Capability audit

Run: 2026-10-20T22:52:03 | admin: False | AC: True | NVIDIA GeForce RTX 4070 Laptop GPU (36 SMs, cc 8.9, 8187 MiB) | driver 616.92

| Item | Kind | Avail | Admin | Latency ms | Reading / measured effect | Note |
|---|---|---|---|---|---|---|
| NVML power_w | sensor | Y | False | 0.001 | 95.206 | read under GPU matmul load |
| NVML sm_clock_mhz | sensor | Y | False | 0.0012 | 2430 | read under GPU matmul load |
| NVML mem_clock_mhz | sensor | Y | False | 0.0012 | 8001 | read under GPU matmul load |
| NVML temp_c | sensor | Y | False | 0.001 | 71 | read under GPU matmul load |
| NVML util_gpu_pct | sensor | Y | False | 0.0013 | 100 | read under GPU matmul load |
| NVML vram_used_mib | sensor | Y | False | 0.0037 | 454 | read under GPU matmul load |
| NVML fan_pct | sensor | N |  |  |  | Not Supported |
| NVML total_energy_j | sensor | Y | False | 0.6444 | 15945.796 | read under GPU matmul load |
| NVML clock_event_reasons | sensor | Y | False | 0.3071 | ['SwPowerCap'] | read under GPU matmul load |
| NVML power_w update interval | sensor | Y | False | 220.1197 | median 220.1 ms, p90 500.1 ms over 16 changes; 925577 calls/s | latency_ms column = median interval between distinct values |
| NVML util_gpu_pct update interval | sensor | Y | False | 470.9535 | median 471.0 ms, p90 500.0 ms over 4 changes; 735430 calls/s | latency_ms column = median interval between distinct values |
| NVML temp_c update interval | sensor | Y | False | 971.2344 | median 971.2 ms, p90 1441.7 ms over 4 changes; 891403 calls/s | latency_ms column = median interval between distinct values |
| Power limit read/set (NVML) | actuator | N |  |  |  | Not Supported |
| nvidia-smi -lgc/-rgc (SM clock lock) | actuator | NOT_RUN | True | 71.3368 |  | not elevated; -rgc probe rc=4: 'The current user does not have permission to change clocks for GPU 00000000:01:00.0.\nTerminating early due to previous e'. Re-run from an Administrator shell for the apply/revert test. |
| nvidia-smi -lmc/-rmc (mem clock lock) | actuator | NOT_RUN | True |  |  | not elevated |
| VRAM headroom | sensor | Y | False | 137.2248 | total 8188 MiB, used 454, free 7733; allocated 6709 MiB ok | WDDM paging onset NOT measured here (needs over-subscription test in W2) |
| PDH GPU Engine counters | sensor | PARTIAL | False | 7.0476 | 559 engine instances, 84 with a Compute engine type; this process (pid 7088) summed engine util 0.0% while NVML util was ~100% | latency_ms = one CollectQueryData over all instances; refresh ~1 s. CUDA compute is NOT attributed to the process here: per-process fg/bg split cannot rely on PDH. |
| NVML per-process compute list | sensor | Y | False |  | 1 processes; this pid listed: True; usedGpuMemory sample: [None] | WDDM often reports usedGpuMemory as N/A or empty lists |
| NVML per-process graphics list | sensor | PARTIAL | False |  | 0 processes; this pid listed: False; usedGpuMemory sample: [] | WDDM often reports usedGpuMemory as N/A or empty lists |
| PresentMon (frame times) | sensor | N | True |  |  | not installed; get the Intel PresentMon release binary |
| LibreHardwareMonitor WMI (Ryzen package power) | sensor | N |  | 494.9206 |  | LHM not running / WMI namespace absent |
| HWiNFO shared memory | sensor | N |  |  |  | HWiNFO not running with Shared Memory Support enabled |
| Windows PDH Energy Meter rapl_package0_pkg | sensor | Y | False | 0.7818 | raw counter idle median 8183, all-core spin median 46930 (n=12/10, 250 ms polls) | unit assumed mW (Microsoft Energy Meter docs) - NOT yet validated against a wall meter or HWiNFO; treat as relative until checked |
| ryzenadj (CPU power limits) | actuator | N | True |  |  | not on PATH; needs release binary + driver (admin); Ryzen 7940HS support not yet verified |
| CPU priority class | actuator | Y | False | 0.1173 | BELOW_NORMAL set and reverted | effect NOT tested here (needs contended fg test) |
| CPU affinity | actuator | Y | False | 0.1563 | pinned to cpu 0 and restored (16 logical) |  |
| EcoQoS (ProcessPowerThrottling) | actuator | Y | False | 0.0217 | spin-loop iterations in 2 s: normal 19252688, EcoQoS 16382694 (-14.9%) | single run each; indicative only, not an effect-size estimate |
| Job-object CPU hard cap | actuator | Y | False | 0.1848 | child CPU 99% of one core -> 30% (target ~25%) | ok=True/True err=0 |

Execution mode: CUDA via torch on NVIDIA GeForce RTX 4070 Laptop GPU (no CPU fallback)
Ambient temp: NOT MEASURED (no sensor; enter manually per experiment)
nvcc: Build cuda_13.1.r13.1/compiler.36836380_0 | MSVC cl on PATH: False