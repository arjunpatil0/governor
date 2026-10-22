# STATUS (overwritten at every stop)
Updated 2026-10-23 · Phase: W4-5. W5 yaml COMMITTED (1683d3c, blockers 1-4 + changes 5-6). W5a tooling built. Blocked on ONE decision of yours: the model downloads (below).

## Just did (journal 0044; response reviews/2026-10-23_w5_yaml_final_review_response.md)
- Yaml committed with the dated commit_note. Change 7 explained: the ~5% admission mismatch was a join artefact in MY report (6-decimal rounding on 100 ns ticks); 0 of 5375 aligned starts violate the fit test.
- analysis/w5_analysis.py written test-first (13 tests): HW1, HW2 (infeasible = 0, exact Wilcoxon, Holm, NI ratios, HW1 for d'B), HW3, HW7.
- W5a tooling test-first: experiments/w5a/w5a_design.py (cell list, 280 cells), w5a_metrics.py, run.py (hardware runner, no hardware run yet).
- Driver: context shift so 35 s cells never end early (not yet verified on hardware); the build test no longer changes the exe hash. Exe hash now bb875fbc... (needs one warm).
- 8B load pre-check NOT run: only the 3B is on disk.

## Decision needed from you (one)
Accept the Llama 3.2 / 3.1 Community Licences and approve downloading 8.1 GB (sha256 verified): Llama-3.2-1B-Instruct Q4_K_M (0.8 GB), Llama-3.1-8B-Instruct Q4_K_M (4.9 GB, held out), Phi-3.5-mini-instruct Q4_K_M (2.4 GB, MIT, my proposal for the 'other LLM family'). Yes / no / different other-family model.

## Then (my side, before W5a)
Download + checksum, models.json, 8B load pre-check (all layers on the GPU at context 2048) and the held-out addendum, freeze the cell list (seed, sha256) in an addendum, then W5a session-1 commands (first: `warm`, the `shift` smoke, one trial cell with --limit 1).

## Notes
- Windows Update and NVIDIA driver updates paused by you for the study. Do NOT rebuild the driver or run `git clean` between sessions.
- Simulator frozen. Run checklist: Administrator PowerShell for the helper; AC power; clean committed tree; Armoury mode stated; Chrome closed; tray apps quit; no clicking; warm every new exe.
