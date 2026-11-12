# STATUS (overwritten at every stop)
Updated 2026-11-13 - Phase: v2 (pausable decode) complete through sprint 4 (docs/V2_SPRINT1_PAUSE_COST.md, V2_SPRINT2_HANDOVER.md, V2_SPRINT3_JITTER.md, V2_SPRINT4_LOW_SLACK.md; journals 0072-0075). Released as v2.0.0 (tag at 76aab2a) and v2.0.1 (docs, tag at 6cfd953). The public-ready work is merged to master (e557238): README rewrite with numbers generated from data/v2, related work in the v2 report, privacy scrub of non-registered files (94b1191), version 2.0.1, journals 0070-0075. The repo is about to be made public.

Open items: the owner's decisions listed in the sprint docs' "next" sections; what the write-up does with the negative registered result (W5b, journal 0066); prior-art search (not done beyond the v2 related-work list).

## Risks / not verified
- 590 W audit: a glitch shorter than one NVML update inside the W5b cells cannot be excluded (raw samples not stored); phantom energy at two energy reads per 60 s window was never measured (docs/AUDIT_590W.md).
- v2 was measured on one laptop GPU, one driver, one synthetic foreground at 1800 MHz; the sprint 4 VERY TIGHT pass rests on two reps, and the cause of the guard-0 overlap frames is not established.
- Registered data files (data/, journal/, reviews/) still contain the original Windows paths and process snapshots from the machine they were recorded on; they were not edited because manifests and hashes cover them.
- demo.py has not been run on hardware (journal 0068; no later record of a run).
