# STATUS (overwritten at every stop)
Updated 2026-10-23 - Phase: W4-5. Addendum O registered (40ca772) before any W5b data; the T1-T3 tuning runner is built (test-first) and the commands are written. Waiting for YOU to run the supervised trial and then the overnight sitting.

## Just did (journal 0050)
- Addendum O: fallback confirmed (d'B = hybrid + grey-box ModelController + shield); HGB recorded as a finding + limitation; d'B margin rule (smallest m in {0..0.4} with mean miss <= 1% over the six d'B tuning cells; no W5a number); exploratory arm d'B-HGB registered (S1/S5, 60 W, blocks 4-8, outside all families; controller written AFTER T1-T3, margin in block T3b, dropped if not ready by block 4); all tuning-block rules stated; the 3 h cap relaxed for T1-T3 only (flagged to the reviewer).
- Built experiments/w5b/{tune_lib,tune,executors,morning}.py + 31 tests. Simulator dry run of the whole plan: 157 cells (logic check only).

## Your next steps (docs/W5B_TUNING_SITTING.md has the literal commands)
1. Admin window: start the helper; press Ctrl+C ONCE (first elevated check of the fix: prompt within ~2 s, "clock reset done"), start it again.
2. Supervised trial (~10 min, six cells, one per executor path): python experiments/w5b/tune.py --out data/w5b/trial --armoury-mode Performance --trial ; paste the TRIAL lines.
3. If sane: the overnight command (T1->T2->T3 chained, --max-hours 11); morning: python experiments/w5b/morning.py --out data/w5b/tuning and the admin-window checks.

## Waiting for
Reviewer: the relaxation of the 3 h cap for the tuning blocks (addendum O section 4), the c'B/d'B tuning grids, the d'B-HGB staging.

## Risks / not verified
- HwExecutor has NEVER run on the GPU (governed c'B/d'B cells, bg-alone and fg-alone cells, thermal polling): hence the trial. Helper Ctrl+C untested elevated. d'B is aligned-only (granularity); a 35 W g'B may not exist. Cell time (~100 s) and size (157 cells in the simulator, up to ~480) are estimates. W5b evaluation not started.

## Notes
- Do not run pytest or rebuild before the sitting; the tree is clean and committed; exe hash bb875fbc unchanged. Uptime must be <= 2 h at the start of the sitting (fresh restart).
