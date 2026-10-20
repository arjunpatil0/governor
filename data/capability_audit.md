# Capability audit

Run: 2026-10-20T23:18:27 | admin: True | AC: True | NVIDIA GeForce RTX 4070 Laptop GPU (36 SMs, cc 8.9, 8187 MiB) | driver 616.92

| Item | Kind | Avail | Admin | Latency ms | Reading / measured effect | Note |
|---|---|---|---|---|---|---|
| NVML power_w | sensor | Y | False | 0.0006 | 95.151 | read under GPU matmul load |
| NVML sm_clock_mhz | sensor | Y | False | 0.0007 | 2445 | read under GPU matmul load |
| NVML mem_clock_mhz | sensor | Y | False | 0.0007 | 8001 | read under GPU matmul load |
| NVML temp_c | sensor | Y | False | 0.0006 | 68 | read under GPU matmul load |
| NVML util_gpu_pct | sensor | Y | False | 0.0007 | 100 | read under GPU matmul load |
| NVML vram_used_mib | sensor | Y | False | 0.0022 | 454 | read under GPU matmul load |
| NVML fan_pct | sensor | N |  |  |  | Not Supported |
| NVML total_energy_j | sensor | Y | False | 0.4889 | 20810.301 | read under GPU matmul load |
| NVML clock_event_reasons | sensor | Y | False | 0.2496 | ['SwPowerCap'] | read under GPU matmul load |
| NVML power_w update interval | sensor | Y | False | 22.3335 | median 22.3 ms, p90 500.1 ms over 16 changes; 972870 calls/s | latency_ms column = median interval between distinct values |
| NVML util_gpu_pct update interval | sensor | Y | False | 999.1852 | median 999.2 ms, p90 1000.1 ms over 5 changes; 753908 calls/s | latency_ms column = median interval between distinct values |
| NVML temp_c update interval | sensor | Y | False | 1773.4377 | median 1773.4 ms, p90 1546.2 ms over 2 changes; 903063 calls/s | latency_ms column = median interval between distinct values |
| Power limit read/set (NVML) | actuator | N |  |  |  | Not Supported |
| nvidia-smi -lgc/-rgc (SM clock lock) | actuator | Y | True | 443.2346 | median SM clock 2385 -> 1200 (target 1200) -> 2430 MHz after revert; power while locked 28.5 W | smi apply 81 ms, revert smi 65 ms, revert settle 429.68820000533015; rc=0/0 'GPU clocks set to "(gpuClkMin 1200, gpuClkMax 1200)" for GPU 00000000:01:00.0\nAl' |
| nvidia-smi -lmc/-rmc (mem clock lock) | actuator | Y | True | 84.4157 | lock to max 8001 MHz rc=0 | Memory clocks set to "(memClkMin 8001, memClkMax 8001)" for GPU 00000000:01:00.0 All done. (accept/reject only; effect NOT tested) |
| VRAM headroom | sensor | Y | False | 214.2243 | total 8188 MiB, used 454, free 7733; allocated 6709 MiB ok | WDDM paging onset NOT measured here (needs over-subscription test in W2) |
| PDH GPU Engine counters | sensor | PARTIAL | False | 6.6717 | 559 engine instances, 84 with a Compute engine type; this process (pid 32608) summed engine util 0.0% while NVML util was ~100% | latency_ms = one CollectQueryData over all instances; refresh ~1 s. CUDA compute is NOT attributed to the process here: per-process fg/bg split cannot rely on PDH. |
| NVML per-process compute list | sensor | Y | False |  | 1 processes; this pid listed: True; usedGpuMemory sample: [None] | WDDM often reports usedGpuMemory as N/A or empty lists |
| NVML per-process graphics list | sensor | PARTIAL | False |  | 0 processes; this pid listed: False; usedGpuMemory sample: [] | WDDM often reports usedGpuMemory as N/A or empty lists |
| PresentMon (frame times) | sensor | N | True |  |  | not installed; get the Intel PresentMon release binary |
| LibreHardwareMonitor WMI (Ryzen package power) | sensor | N |  | 437.6508 |  | LHM not running / WMI namespace absent |
| HWiNFO shared memory | sensor | N |  |  |  | HWiNFO not running with Shared Memory Support enabled |
| Windows PDH Energy Meter rapl_package0_pkg | sensor | Y | False | 0.7626 | raw counter idle median 9630, all-core spin median 48061 (n=12/10, 250 ms polls) | unit assumed mW (Microsoft Energy Meter docs) - NOT yet validated against a wall meter or HWiNFO; treat as relative until checked |
| ryzenadj (CPU power limits) | actuator | N | True |  |  | not on PATH; needs release binary + driver (admin); Ryzen 7940HS support not yet verified |
| CPU priority class | actuator | Y | False | 0.0901 | BELOW_NORMAL set and reverted | effect NOT tested here (needs contended fg test) |
| CPU affinity | actuator | Y | False | 0.2355 | pinned to cpu 0 and restored (16 logical) |  |
| EcoQoS (ProcessPowerThrottling) | actuator | Y | False | 0.0231 | spin-loop iterations in 2 s: normal 21244231, EcoQoS 16022550 (-24.6%) | single run each; indicative only, not an effect-size estimate |
| Job-object CPU hard cap | actuator | Y | False | 0.1768 | child CPU 99% of one core -> 31% (target ~25%) | ok=True/True err=0 |

Execution mode: CUDA via torch on NVIDIA GeForce RTX 4070 Laptop GPU (no CPU fallback)
Ambient temp: NOT MEASURED (no sensor; enter manually per experiment)
nvcc: Build cuda_13.1.r13.1/compiler.36836380_0 | MSVC cl on PATH: False