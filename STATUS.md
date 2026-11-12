# STATUS (overwritten at every stop)
Updated 2026-11-12 - Phase: v2 (pausable decode) complete through sprint 4 (docs/V2_SPRINT1_PAUSE_COST.md, V2_SPRINT2_HANDOVER.md, V2_SPRINT3_JITTER.md, V2_SPRINT4_LOW_SLACK.md; journals 0072-0075). Released as v2.0.0 (tag at 76aab2a) and v2.0.1 (docs, tag at 6cfd953). Branch public-ready (checked out) prepares the repo for external readers: README rewrite, privacy scrub, related work. Merge to master awaits the owner's approval. Nothing has been sent to anyone.

## Pending this pass (not committed)
pyproject.toml and python/governor/__init__.py at 2.0.1; journals 0070-0075 (written after the fact on 2026-11-12 from the git log and docs); CHANGELOG [Unreleased] public-ready; TIMELINE rows; workloads/background/pause_patch/THIRD_PARTY_NOTICE.md. README.md is modified and tests/test_readme_numbers.py and tools/readme_numbers.py are untracked in the working tree; this pass did not create or touch them.

Older open items: the owner's decisions listed in the sprint docs' "next" sections; what the write-up does with the negative registered result (W5b, journal 0066); prior-art search (not done beyond the v2 related-work list).

## Risks / not verified
- 590 W audit: a glitch shorter than one NVML update inside the W5b cells cannot be excluded (raw samples not stored); phantom energy at two energy reads per 60 s window was never measured (docs/AUDIT_590W.md).
- v2 was measured on one laptop GPU, one driver, one synthetic foreground at 1800 MHz; the sprint 4 VERY TIGHT pass rests on two reps, and the cause of the guard-0 overlap frames is not established.
- The "privacy scrub" in the public-ready list has no commit in git log; not verified here.
- demo.py has not been run on hardware (journal 0068; no later record of a run).
