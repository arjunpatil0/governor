# STATUS (overwritten at every stop)
Updated 2026-10-21 · Phase: W2 (B done and committed; llama.cpp driver ready; Experiments A/A2 pending)

## Just did (commits)
- B results + raw data + journal 0016: c51b499; B report fixes (completed fraction, ceiling label, deadline-aware table) + B review committed: 9872221
- llama.cpp addendum registered: 8e5b490; source build of v0.7.0 OK; driver + tests + sanity check (101.0 vs 104.6 tok/s, -3.5%, pass): ecea182
- trace_cell.py for the Nsight trace: 1701500; journal 0017 + B response (finding 3 pending): 29e7984
- Coordination/documentation rules in CLAUDE.md, .obj gitignored: deeedbd; docs/TIMELINE.md + docs/CONCEPTS.md: next commit

## Waiting for
- Arjun's two Nsight Systems traces (`-t cuda,nvtx,wddm`) in data/nsys/ (fma60_membg_1800, fma60_membg_unlocked). data/nsys does not exist yet (checked after the rules commit). I will check that each contains BOTH the foreground and background processes, then explain fg_gpu_ms.

## Decisions needed
1. GitHub: install GitHub CLI (`winget install GitHub.cli`) and run `gh auth login` yourself in your shell, or create an empty private repo "governor" on github.com and give me nothing but the URL. Recommendation: gh route (`gh repo create governor --private --source . --push`); I do not have `gh` and will not handle credentials.
2. After the traces: go-ahead to implement llama.cpp part `L` (test-first) before Experiment A? Recommendation: yes, A is the most decision-relevant run, so run A first (needs only your admin shell) while I build part L.
3. docs/TIMELINE.md and docs/CONCEPTS.md exist (backfilled, 16 concepts). Say if you want a different CONCEPTS format. Recommendation: keep.

## Reviewer checkpoint due?
- Design change: no. Results before interpretation: B's results were reviewed (response written). Pre-registration before commit: none pending. Surprise: the fg_gpu_ms pattern under co-run (finding 3) is open until the traces are read.
