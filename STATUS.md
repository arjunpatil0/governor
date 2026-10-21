# STATUS (overwritten at every stop)
Updated 2026-10-21 · Phase: W2 (B done and committed; llama.cpp driver ready; Experiments A/A2 pending)

## Just did (commits)
- Earlier: B c51b499, B report fixes 9872221, llama.cpp addendum 8e5b490, driver + sanity check ecea182, rules deeedbd, docs 0ae2e11.
- Nsight trace incident 0018: partial output inspected (children finished in ~11 s; they did not EXIT), trace_cell.py fixed test-first (fixed window, kill hung children, clocks reset in finally), smoke-tested without nsys. Commit: see git log (this commit).

## Waiting for
- Arjun to rerun the two traces (commands below). Per your rule: no parallel work during experiments; I do nothing that executes while they run.
- `nsys.exe` PID 18764 from the aborted run is still running: stop it first (`taskkill /PID 18764 /F`) and check `nvidia-smi -q -d CLOCK | findstr /i "SM"` shows clocks released.

## Decisions needed
1. After the traces: go-ahead to implement llama.cpp part `L` (code/tests only, nothing executing during experiments)? Recommendation: yes, between your runs.
2. Experiment A (19 cells x 10 blocks) next: `python experiments\w2_colocationun.py --part A --ambient-c 25` once traces are done. Recommendation: A before L.

## Reviewer checkpoint due?
- Surprise: yes, mild. The trace attempt contradicted the "overloaded fg never finishes" hypothesis (it finished; exit hung). Finding 3 stays open until a trace exists.
