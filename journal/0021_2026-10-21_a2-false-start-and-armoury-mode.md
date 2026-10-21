# 0021 — Incidents: A2 false start (crash after 3 cells) and a memory-clock mismatch from the Armoury Crate mode
Date: 2026-10-21 · Phase: W2 (Experiment A2) · Author: Claude Code (run by Arjun, admin shell; report pasted by Arjun)

## Incident 1: A2 crashed after 3 cells
- Run dir (kept, gitignored like all data/raw; force-added as evidence): data/raw/w2_A2/20261021T174039Z (git_head 081f148, clean tree, admin). results.csv has 3 rows (sa4_fg4_alone, sa4_fg1_m2, duty_fg4_d0.75); cell 4 (duty_fg9_d0.5) crashed.
- Error (as reported): run.py line 180, run_cell: `units_fg = ctx["frame_units"][fg["frame"]]` -> `TypeError: 'NoneType' object is not subscriptable`.
- Cause (verified in code): design.py gives A2's 9 ms stream `frame = "fma_60hz"` (the B frame kernel), but run.py loaded frame units from the pilot only `if a.part == "B"`, so ctx["frame_units"] was None for A2.
- Why it was not caught: no run-level test covered A2, and `--smoke` runs only the first 3 cells of the block order, the 9 ms cell was 4th.
- Fix (test first): RED tests/test_w2_design.py::test_frame_units_loaded_for_every_part_whose_cells_use_a_frame (4 params failed: function missing). GREEN: design.frame_units_for_part(part, cells, pilot) returns the pilot frame units when any cell uses a frame (B and A2), else None; run.py uses it (21 tests pass in test_w2_design.py). Smoke now runs the first 3 cells plus the first cell of every other fg stream, so the 9 ms cell is exercised: `run.py --part A2 --smoke` (non-admin) ran 5/5 cells including duty_fg9_d0.5 (smoke dir data/raw/w2_A2_smoke/20261021T174452Z, clock-target flags expected without admin; not a result).
- The partial run is a false start, not data. A2 reruns from scratch.
- Design note for the A2 analysis (not a change): the 9 ms stream's kernel size is the pilot's fma_60hz frame sized at the UNLOCKED clock; at 1800 MHz that frame serves in about 12 ms (journal 0016: 12.1 ms alone). A2 analysis must use the measured alone-latency for that stream, not the nominal 9 ms.

## Incident 2: every A2 cell flagged mem_clock_left_target:8101
- Observation: all 3 A2 rows carry `mem_clock_left_target:8101` (A, B, C held 8001; flag threshold 1% of the 8001 lock). A2 samples show the GPU reporting 8101 MHz while the lock was set to 8001.
- Arjun's likely cause: switching Armoury Crate to Turbo before this run (vendor GPU memory overclock). NOT verified by me; the evidence is the clock samples plus Arjun's report. Arjun switched back to the mode used for A/B/C.
- The Armoury Crate mode was never recorded for A, B or C. The mode used for them is known only from Arjun's statement; it is not in any meta.json.
- Not detectable from software I have: I did not find a documented API; so the mode is now an explicit argument.
- Changes: `run.py --armoury-mode <mode>` is required for full runs and stored in meta.json (`armoury_mode`); smoke runs may omit it. CLAUDE.md run protocol updated.
- Consequence for A, B, C (checked in results.csv): per-cell median memory clock is 8001 MHz in every cell of A (190), B (360) and C (360); the only memory flag in any of them is one A cell (block 7, 7001). So their memory clocks were consistent with 8001. The Armoury Crate mode name itself is unrecorded for them.
