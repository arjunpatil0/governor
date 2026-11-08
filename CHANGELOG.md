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

## Pause-cost study (brief called it "v2 sprint 1"; 2026-11-07 and 08)

What changed
- Measured what it costs to split one token's decode into G layer groups with a pause point between groups: a patched copy of the pinned llama.cpp (`workloads/background/pause_patch/`, built by `build_llama_v2.bat`), a pause-aware driver (`llama_pause_bench.cpp`), the sweep and analysis scripts (`tools/pause_bench.py`, `tools/pause_analyze.py`) and a pausable copy of the plant simulator (`sim/plant_pausable.py`, `tools/pause_payoff.py`). Results and limits: `docs/V2_SPRINT1_PAUSE_COST.md`.

Benchmark numbers
- 3B at a 1500 MHz lock, 3 x 300 tokens per configuration: token time 10.14 ms whole; overhead 0.3% (G = 2), 0.5% (4), 0.9% (7), 2.2% (14), 4.3% (28); longest group 5.57, 3.47, 2.58, 1.95, 1.63 ms. Graphs off: +14.2%. A forced 2 ms pause per boundary raised the token time by 6.07 ms at G = 4 and 12.17 ms at G = 7 (expected 6 and 12), so the boundaries are real pause points. Verdict by the pre-stated rule: GO.

Next step
- Sprint 2 (owner's decision): build the real pausable decode against a live frame hint and measure what the other process gains at a pause, which this study did not measure. The output projection (about 1.3 ms) is the floor under the longest group at layer granularity.

## Handover study (v2 sprint 2, 2026-11-08)

What changed
- Measured, on hardware, whether pausable decode frees the GPU for the 60 fps app: a hint-gated decode driver (per token or per layer group), a cell runner with a marker-kernel handover measurement, the 8B group sweep and 12 end-to-end cells. Results and limits: `docs/V2_SPRINT2_HANDOVER.md`. The 1500 MHz lock of sprint 1 was read back (nvidia-smi and NVML read 1500 MHz throughout).

Benchmark numbers
- Handover: the foreground's first-kernel delay is about 0.48 ms at p50 and 0.84 to 0.87 ms at p99 whether decode runs whole tokens or 14 groups (max 1.7 ms); the brief's forecast of about 10 ms for whole tokens was wrong (WDDM time-slices every ~0.37 ms, so the app shares the GPU instead of waiting for the token).
- 8B: token 21.0 ms; G = 14 +1.4% with a 3.61 ms longest group; G = 28 +2.9% with 2.99 ms. The 8B output head is about 2.4 ms, so no G reaches 2.5 ms.
- End to end (3 reps, 60 s, static aligned gate at 1800 MHz, guard 0): S1 3B 19.95 -> 47.9 tok/s, S5 8B 0.0 -> 24.2 tok/s going from the whole-token gate to 14 groups, late frames 0.00% in all 12 cells, power 57.9 to 59.2 W, `power_rejected` 0. Verdict by the stated rule: WIN on throughput; the late-frame clause could not be tested because the baseline already had none.

Next step
- Owner's decision: test pausable decode where the baseline misses (the learned governor's unaligned mode, bursty frame costs), and split the output head by rows to bring the 8B longest group under 2.5 ms.

## Jitter study (v2 sprint 3, 2026-11-08)

What changed
- Tested whether the pausable gate keeps frames on time when the app is irregular: a seeded jitter loop for the synthetic foreground (frame cost, submit time, unannounced bursts), a SOLO arm so that decode is not blamed for the app's own late frames, and a late-frame cause breakdown matched to SOLO by sequence index. Results and limits: `docs/V2_SPRINT3_JITTER.md`. The forecast and decision rule were pushed before any data existed.

Benchmark numbers
- 28 cells (none 1 rep; moderate and heavy 3 reps; SOLO, 3B whole-token, 3B 14-group, 8B 14-group). Excess late frames over SOLO for the 3B 14-group gate: 0.00 pp at moderate, 0.08 pp at heavy (reps 0.03 to 0.14); whole-token gate 0.00 at both; limits were 1 and 2 pp. tok/s: 14 groups 48.2 and 45.9, whole token 21.9 and 23.3. Verdict by the stated rule: PASS, no FAIL, no OVERLAP BONUS (whole-token excess 0.00 against 0.08). 97% of late frames at heavy are the app's own (SOLO misses them too); jitter makes the group gate touch 16 to 35% of frames (0.1 to 0.8% without jitter) but the touches are short (slowdown p99 1.2 to 1.7) and the frames have 8 to 11 ms of slack. `power_rejected` 0 in all cells.

Next step
- Owner's decision: repeat with an app that has little slack (12 to 14 ms frames), where the number of group touches could matter, and with correlated rather than independent jitter.
