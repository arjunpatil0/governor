# CHANGELOG

Newest first. The v2 sprint entries (pausable decode, branch v2-foreground, merged into master for v2.0.0) are one entry per sprint: what changed, benchmark numbers, next step. v2 is a lightweight engineering track, not a pre-registered study; the v1 registered results, constants and the v1 driver exe are not touched.

## [Unreleased] public-ready

Preparation of the repository for external readers (branch public-ready). Documentation and housekeeping only; no code, data or measurement changed.

- README rewrite for external readers, privacy scrub, related work (cited in the v2 report, see v2.0.1).
- Housekeeping: version declared as 2.0.1 in `pyproject.toml` and `python/governor/__init__.py`; research journal entries 0070 to 0075 (v1.0.0 packaging, the 590 W audit, v2 sprints 1 to 4) written after the fact on 2026-11-12; `workloads/background/pause_patch/THIRD_PARTY_NOTICE.md` with the llama.cpp MIT notice for the patch; STATUS and TIMELINE updated.

## v2.0.1 (docs) (2026-11-08)

Related work section, novelty hedged. Documentation only; no code, data or measurement changed, and v2.0.0 stays tagged where it was.

- `docs/report/REPORT_V2.md` gains section 8, Related work (ConServe, QLLM, LayerLoom, Ripple, REEF, Hummingbird, GCAPS, FIKIT, VUDA), written from the abstracts only. It states that layer-level LLM preemption is established and positions this work as cross-process, on-device sharing against a 60 fps frame deadline on consumer Windows hardware without driver support. The abstract and the mechanism section now say the mechanism is not new.
- `docs/report/SOURCES_V2.md` lists the cited works with URLs; the PDF is rebuilt (5 pages).
- README v2 section: one sentence and links to the cited work.

## v2.0.0 (2026-11-08)

What this release is: the v1.0.0 toolkit plus pausable LLM decode (layer-group decode gated on the frame hint), measured in four sprints, with a report and a mechanism document. v1 registered results, constants and the v1 driver executable are unchanged; v1.0.0 stays tagged where it was.

Added
- `workloads/background/pause_patch/llama_pause_groups_620d2225c.patch`: the llama.cpp patch as a `.patch` file against the pinned commit (`git apply --check` passes on a clean checkout; byte-identical to the tree used for the measurements). `docs/PAUSABLE_DECODE.md` explains the mechanism and the build.
- `docs/report/REPORT_V2.md` and `REPORT_V2.pdf` (5 pages), `SOURCES_V2.md` (83 claims, each tied to a file and line) and `STYLE_CHECK_V2.md`; built by `build_report_v2.py`, `build_sources_v2.py` and `style_check_v2.py`.
- `tools/v2_figure.py` and `docs/figures/v2_cliff_vs_smooth.png`: throughput and excess late frames against free GPU time per frame, every end-to-end condition of sprints 2 to 4, from the committed data.
- README: a "v2: pausable decode" section above the v1 results (the v1 text is unchanged; one heading was added as an anchor for the link back).

Headline results (sources in the report): pausing costs 1.4% to 2.2% in token time at 14 groups with identical tokens; at 0.00% late frames the 8B went from 0 to 24.2 tok/s and the 3B from 19.95 to 47.9; with about 4 ms free per frame whole-token decode gets 0 tok/s and pausable decode 17.5 (+0.28 pp excess late, inside the noise band); at about 2 ms free (a stress level, the app alone misses 29%) 7.2 tok/s at +1.71 pp, a pass on the mean of two reps with rep 1 over the limit.

Known limits of v2.0.0
- The foreground is a synthetic kernel loop and the gates are static rules; there is no registered comparison with the v1 governor.
- Prefill is not split. The output head (about 1.3 ms for the 3B, 2.4 ms for the 8B) is the floor under the longest uninterruptible piece.
- Two or three reps per cell, one machine, one GPU and driver, Windows only. The 14-group gate has no power control and draws 57 to 60 W at 1800 MHz.
- Many forecasts were wrong (listed in the report, section 5).

## Low-slack study (v2 sprint 4, 2026-11-08)

What changed
- Tested whether the pausable gate still helps when the app leaves 4 ms (TIGHT) or 2 ms (VERY TIGHT) free per frame, and whether an early-start margin (the gate's guard, 1.0 ms) cuts collisions with early frames. Step 0: the gate already keeps one duration estimate per group (median of the last 8 clean durations), so nothing was switched. New: `tools/slack_cell.py` (calibrates the constant-cost foreground to a SOLO median frame time, runs 2 levels x 6 arms x 2 reps), `tools/slack_analyze.py`, and `run_cell_j` options for cost, guard and scene. Results and limits: `docs/V2_SPRINT4_LOW_SLACK.md`. The forecast and decision rule were pushed before any data existed.

Benchmark numbers
- 24 cells. SOLO median frame times 12.68 ms and 14.70 ms (3.99 and 1.97 ms free). 3B 14 groups, guard 0: 17.5 tok/s with +0.28 pp excess late at TIGHT, 7.2 tok/s with +1.71 pp at VERY TIGHT (rep 1 alone is +2.28 pp); whole token 0 tok/s. Verdict: PASS at both levels, no FAIL, MARGIN WORKS no (guard 1.0 cuts decode-attributed late frames 21 to 2 and 80 to 3 but keeps 76% and 64% of tok/s against 85% required). 8B: 5 to 6 tok/s at TIGHT, 1.5 to 2.0 at VERY TIGHT. The forecast was wrong about which 3B arm passes (guard 0, not guard 1.0) and about SOLO lateness at VERY TIGHT (29% against 17%). Power at most 50 W; `power_rejected` 0 in all cells.

Next step
- Owner's decision: correlated rather than independent jitter, and finding why guard 0 overlaps frames that are not early submits.

## Jitter study (v2 sprint 3, 2026-11-08)

What changed
- Tested whether the pausable gate keeps frames on time when the app is irregular: a seeded jitter loop for the synthetic foreground (frame cost, submit time, unannounced bursts), a SOLO arm so that decode is not blamed for the app's own late frames, and a late-frame cause breakdown matched to SOLO by sequence index. Results and limits: `docs/V2_SPRINT3_JITTER.md`. The forecast and decision rule were pushed before any data existed.

Benchmark numbers
- 28 cells (none 1 rep; moderate and heavy 3 reps; SOLO, 3B whole-token, 3B 14-group, 8B 14-group). Excess late frames over SOLO for the 3B 14-group gate: 0.00 pp at moderate, 0.08 pp at heavy (reps 0.03 to 0.14); whole-token gate 0.00 at both; limits were 1 and 2 pp. tok/s: 14 groups 48.2 and 45.9, whole token 21.9 and 23.3. Verdict by the stated rule: PASS, no FAIL, no OVERLAP BONUS (whole-token excess 0.00 against 0.08). 97% of late frames at heavy are the app's own (SOLO misses them too); jitter makes the group gate touch 16 to 35% of frames (0.1 to 0.8% without jitter) but the touches are short (slowdown p99 1.2 to 1.7) and the frames have 8 to 11 ms of slack. `power_rejected` 0 in all cells.

Next step
- Owner's decision: repeat with an app that has little slack (12 to 14 ms frames), where the number of group touches could matter, and with correlated rather than independent jitter.

## Handover study (v2 sprint 2, 2026-11-08)

What changed
- Measured, on hardware, whether pausable decode frees the GPU for the 60 fps app: a hint-gated decode driver (per token or per layer group), a cell runner with a marker-kernel handover measurement, the 8B group sweep and 12 end-to-end cells. Results and limits: `docs/V2_SPRINT2_HANDOVER.md`. The 1500 MHz lock of sprint 1 was read back (nvidia-smi and NVML read 1500 MHz throughout).

Benchmark numbers
- Handover: the foreground's first-kernel delay is about 0.48 ms at p50 and 0.84 to 0.87 ms at p99 whether decode runs whole tokens or 14 groups (max 1.7 ms); the brief's forecast of about 10 ms for whole tokens was wrong (WDDM time-slices every ~0.37 ms, so the app shares the GPU instead of waiting for the token).
- 8B: token 21.0 ms; G = 14 +1.4% with a 3.61 ms longest group; G = 28 +2.9% with 2.99 ms. The 8B output head is about 2.4 ms, so no G reaches 2.5 ms.
- End to end (3 reps, 60 s, static aligned gate at 1800 MHz, guard 0): S1 3B 19.95 -> 47.9 tok/s, S5 8B 0.0 -> 24.2 tok/s going from the whole-token gate to 14 groups, late frames 0.00% in all 12 cells, power 57.9 to 59.2 W, `power_rejected` 0. Verdict by the stated rule: WIN on throughput; the late-frame clause could not be tested because the baseline already had none.

Next step
- Owner's decision: test pausable decode where the baseline misses (the learned governor's unaligned mode, bursty frame costs), and split the output head by rows to bring the 8B longest group under 2.5 ms.

## Pause-cost study (brief called it "v2 sprint 1"; 2026-11-07 and 08)

What changed
- Measured what it costs to split one token's decode into G layer groups with a pause point between groups: a patched copy of the pinned llama.cpp (`workloads/background/pause_patch/`, built by `build_llama_v2.bat`), a pause-aware driver (`llama_pause_bench.cpp`), the sweep and analysis scripts (`tools/pause_bench.py`, `tools/pause_analyze.py`) and a pausable copy of the plant simulator (`sim/plant_pausable.py`, `tools/pause_payoff.py`). Results and limits: `docs/V2_SPRINT1_PAUSE_COST.md`.

Benchmark numbers
- 3B at a 1500 MHz lock, 3 x 300 tokens per configuration: token time 10.14 ms whole; overhead 0.3% (G = 2), 0.5% (4), 0.9% (7), 2.2% (14), 4.3% (28); longest group 5.57, 3.47, 2.58, 1.95, 1.63 ms. Graphs off: +14.2%. A forced 2 ms pause per boundary raised the token time by 6.07 ms at G = 4 and 12.17 ms at G = 7 (expected 6 and 12), so the boundaries are real pause points. Verdict by the pre-stated rule: GO.

Next step
- Sprint 2 (owner's decision): build the real pausable decode against a live frame hint and measure what the other process gains at a pause, which this study did not measure. The output projection (about 1.3 ms) is the floor under the longest group at layer granularity.

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

## v1.0.0 (2026-11-07)

What this release is: the toolkit as it stood at the end of the pre-registered evaluation, packaged so that someone else can read it, install the importable part and reproduce the no-GPU path. No registered data, results or constants were changed for the release.

Added in the packaging pass
- `README.md` rewritten as a short entry point (three sourced results, a diagram, a component table, a no-GPU and a GPU quickstart, the registered verdict). The previous README is kept in full as `docs/PROJECT_DETAILS.md`.
- `docs/FRAME_HINT_SPEC.md`: the frame-hint record as a spec another team can implement (layout, seqlock protocol, versioning, failure behaviour, a C writer and a C reader that were compiled and checked against the Python binding).
- Importable package `python/governor` with `FrameHintWriter`, `FrameHintReader` and `DeadlineGate`, thin wrappers over `python/slackhint`; `pyproject.toml` (`pip install -e ".[test]"`); `examples/minimal_gate.py` (plant simulator plus the gate in simulated time, no GPU); `tests/test_governor_package.py`.
- `LICENSE` (MIT).

Already in the repository at this version
- The frame hint library (`include/slackhint.h`, `python/slackhint`), the governed llama.cpp driver, the four controllers, the NVML admin helper, the plant simulator, the dashboard, the registered evaluation protocols and analysis, the audits (`docs/AUDIT_590W.md`) and the technical report (`docs/report/REPORT.pdf`, 6 pages).

Known limits of v1.0.0
- One laptop, one GPU, one driver (616.92), one synthetic foreground; Windows only.
- The learned governor did not meet its registered target (late frames above 1% in two of five scenes; non-inferiority against the primary reactive controller failed). Details in the report.
- The sampled NVML power reading glitches to about 588 W at idle on this driver. The registered power figures are energy-counter differences and are not affected; the guard that rejects such readings exists on the `v2-foreground` branch and is not part of v1.0.0.
- The energy-read sweep that would settle the worst-case counter overhead (`docs/W5B_ENERGY_READ_SWEEP_PROTOCOL.md`) was not run.
