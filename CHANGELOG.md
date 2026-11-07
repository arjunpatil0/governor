# CHANGELOG (v2 track, branch v2-foreground)

One entry per sprint: what changed, benchmark numbers, next step. v2 is a lightweight engineering track, not a pre-registered study. The v1 registered results, constants and the v1 driver exe are not touched.

## Sprint 1 (2026-11-07)

What changed
- `workloads/foreground/yolo_loop.py`: YOLOv8 (ultralytics) at a fixed 30 FPS on an absolute schedule over a fixed, looped video file. CUDA-event time per frame, late frames recorded and never skipped, busy / next-frame-due published through the existing slackhint protocol. Refuses to run without CUDA.
- `telemetry/vram.py`: per-process GPU memory, sampled (never the energy counter). NVML names the processes but gives no memory figure on this WDDM driver, so the figure comes from the Windows per-process counter on the NVIDIA adapter.
- Dashboard: new "GPU memory per process" panel in live mode (`tools/dashboard`, `index.html` rebuilt from its parts).
- `tools/bench.py`: runs yolo-alone, yolo-3b-free, yolo-3b-paced, yolo-8b-free, yolo-8b-paced N times (default 3 x 60 s) and prints late %, frame p99, tok/s, mean sampled power, peak VRAM per process. "free" is the v1 driver unaligned at duty 1, "paced" is v1 aligned gap-filling (guard 0.5 ms).
- Tests: `tests/test_yolo_loop.py`, `tests/test_vram.py`, `tests/test_bench.py`.

Benchmark numbers
- None yet. The assistant ran nothing on the GPU beyond a 256 MiB allocation to check the VRAM reader (NVML returned no per-process figure; the Windows counter did).

Next step
- Install ultralytics (not installed yet), run the bench commands, read the first table, then decide the 8B question from the "does not fit" check and the VRAM columns.
