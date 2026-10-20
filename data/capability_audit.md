# Capability audit

Run: 2026-10-20T22:50:10 | admin: False | AC: True | NVIDIA GeForce RTX 4070 Laptop GPU (36 SMs, cc 8.9, 8187 MiB) | driver 616.92

| Item | Kind | Avail | Admin | Latency ms | Reading / measured effect | Note |
|---|---|---|---|---|---|---|
| NVML power_w | sensor | Y | False | 0.0011 | 95.043 | read under GPU matmul load |
| NVML sm_clock_mhz | sensor | Y | False | 0.0013 | 2460 | read under GPU matmul load |
| NVML mem_clock_mhz | sensor | Y | False | 0.0012 | 8001 | read under GPU matmul load |
| NVML temp_c | sensor | Y | False | 0.0011 | 67 | read under GPU matmul load |
| NVML util_gpu_pct | sensor | Y | False | 0.0013 | 99 | read under GPU matmul load |
| NVML vram_used_mib | sensor | Y | False | 0.0036 | 454 | read under GPU matmul load |
| NVML fan_pct | sensor | N |  |  |  | Not Supported |
| NVML total_energy_j | sensor | Y | False | 0.5005 | 12768.344 | read under GPU matmul load |
| NVML clock_event_reasons | sensor | Y | False | 0.4682 | ['SwPowerCap'] | read under GPU matmul load |
| NVML power_w update interval | sensor | Y | False | 235.1593 | median 235.2 ms, p90 500.1 ms over 16 changes; 955563 calls/s | latency_ms column = median interval between distinct values |
| NVML util_gpu_pct update interval | sensor | Y | False | 499.9423 | median 499.9 ms, p90 499.9 ms over 3 changes; 761072 calls/s | latency_ms column = median interval between distinct values |
| NVML temp_c update interval | sensor | Y | False | 985.9091 | median 985.9 ms, p90 1471.9 ms over 4 changes; 875898 calls/s | latency_ms column = median interval between distinct values |
| Power limit read/set (NVML) | actuator | N |  |  |  | Not Supported |
| nvidia-smi -lgc/-rgc (SM clock lock) | actuator | NOT_RUN | True | 58.5626 |  | not elevated; -rgc probe rc=4: 'The current user does not have permission to change clocks for GPU 00000000:01:00.0.\nTerminating early due to previous e'. Re-run from an Administrator shell for the apply/revert test. |
| nvidia-smi -lmc/-rmc (mem clock lock) | actuator | NOT_RUN | True |  |  | not elevated |
| VRAM headroom | sensor | Y | False | 136.4294 | total 8188 MiB, used 454, free 7733; allocated 6709 MiB ok | WDDM paging onset NOT measured here (needs over-subscription test in W2) |
| PDH GPU Engine counters | sensor | Y | False | 6.6756 | 559 engine instances; this process (pid 9916) summed engine util 0.0%; top instance: 0_0x00013FE2_phys_0_eng_0_engtype_3D)\Utilization Percentage | latency_ms = one CollectQueryData over all instances; counter refresh is ~1 s so >1 Hz polling is not useful |
| PresentMon (frame times) | sensor | N | True |  |  | not installed; get the Intel PresentMon release binary |
| LibreHardwareMonitor WMI (Ryzen package power) | sensor | N |  | 555.2544 |  | LHM not running / WMI namespace absent |
| HWiNFO shared memory | sensor | N |  |  |  | HWiNFO not running with Shared Memory Support enabled |
| Windows PDH Energy Meter rapl_package0_pkg | sensor | Y | False | 0.8078 | raw counter idle median 9439, all-core spin median 50864 (n=12/10, 250 ms polls) | unit assumed mW (Microsoft Energy Meter docs) - NOT yet validated against a wall meter or HWiNFO; treat as relative until checked |
| ryzenadj (CPU power limits) | actuator | N | True |  |  | not on PATH; needs release binary + driver (admin); Ryzen 7940HS support not yet verified |
| CPU priority class | actuator | Y | False | 0.0829 | BELOW_NORMAL set and reverted | effect NOT tested here (needs contended fg test) |
| CPU affinity | actuator | Y | False | 0.1607 | pinned to cpu 0 and restored (16 logical) |  |
| EcoQoS (ProcessPowerThrottling) | actuator | Y | False | 0.0296 | spin-loop iterations in 2 s: normal 20491249, EcoQoS 13641657 (-33.4%) | single run each; indicative only, not an effect-size estimate |
| Job-object CPU hard cap | actuator | Y | False | 0.1857 | child CPU 100% of one core -> 30% (target ~25%) | ok=True/True err=0 |

Execution mode: CUDA via torch on NVIDIA GeForce RTX 4070 Laptop GPU (no CPU fallback)
Ambient temp: NOT MEASURED (no sensor; enter manually per experiment)
nvcc: Build cuda_13.1.r13.1/compiler.36836380_0 | MSVC cl on PATH: False