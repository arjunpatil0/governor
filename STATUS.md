# STATUS (overwritten at every stop)
Updated 2026-10-21 · Phase: W2 (B done; traces read; Experiments A and A2 pending; llama.cpp driver ready, part L not written)

## Just did (commits)
- Traces read (journal 0019, commit b349750): both processes appear in both traces; the OS trace cannot show our context switches (HAGS ON; no kernel table because the children were killed); fg_gpu_ms defined from the code; the 1800-vs-unlocked pattern stays unexplained and co-run service times stay uninterpreted. Nsight agent failure logged as an incident. Large .nsys-rep/.sqlite gitignored (38/41 MB; sqlite 0.7-0.8 GB).
- Earlier: 09c6d92 (incident 0018, trace_cell.py fix), 429cb66, 0ae2e11 (docs), deeedbd (rules), ecea182 (llama driver + sanity check), c51b499 (B).

## Waiting for
- Arjun to run Experiment A (command below). I execute nothing while it runs.

## Decisions needed
1. Kernel-side %globaltimer diagnostic for the fg_gpu_ms pattern (needs an addendum before it runs)? Recommendation: skip for now; A and A2 are more decision-relevant.
2. After A: run A2 (`--part A2`), then I write llama.cpp part `L` code and tests while nothing runs. Recommendation: yes.

## Reviewer checkpoint due?
- Surprise: yes (HAGS hides context switches from the OS trace; the fg_gpu_ms pattern is unexplained). Results before interpretation: A's results when done. Pre-registration/design change: none pending.

## Experiment A command (admin PowerShell, AC power, clean tree)
cd C:\Users\arjun\governor
python experiments\w2_colocation\run.py --part A --ambient-c 25
