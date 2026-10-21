# STATUS (overwritten at every stop)
Updated 2026-10-22 · Phase: W2 (G registered and built; full G run ready, waiting for your decision 1 and the go)

## Just did (commits; see git log)
- Answered the L+G review (journal 0028): L report now has tok/s + power + J/token table, the proxy lesson (labelled interpretation) and the Reliability item resolved (it is exactly the 10 llama_unlocked cells). G addendum REGISTERED (renamed from _DRAFT, header-only change) before any G code.
- Built the instrumented kernels test-first and ran pre-checks (i)-(iii) in smoke mode (journal 0029, data/w2_G_prechecks.md): timer step 1024 ns; one shared GPU/host timebase (0 fg blocks outside their host window, offset differences within the round trips); overhead found at 1.6x (a branch in the FMA loop), fixed to 0.999-1.004x. A crash (block start from thread 0 only) and a missed DLL rebuild are logged. 14-cell smoke ran clean. Suite 147 passed.
- Transcript docs/transcripts/2026-10-22_session-1.md committed; repo pushed to origin (arjunpatil0/governor).

## Waiting for
- Your go for the full G run (command below).

## Decisions needed
1. Registered pre-check (iii) asks for "fg-alone latency within 5%" but the 14 cells have no uninstrumented fg-alone twin. Recommendation: add g_baseline_off as a 15th cell (one-line addendum before the run, +10 cells). Without it, (iii) is judged on R_m vs R_m_off and the R_2 wait only. Say "add it" or "run as registered".
2. Duration: the 14-cell smoke took 14.6 min because of cool-down waits, so expect roughly 1.5-2.5 h for 140 cells (estimate from one smoke, not measured). Need a long idle window.
3. Reviewer: please confirm the implementation choices in journal 0029 (G_thr from median block-mean read gap; read interval 64; bg record buffer covers only ~1.9 s of timeline at m = 0.5 ms).

## Reviewer checkpoint due?
- Design: choices in decision 3. Results: after the G run.
- Still not written: the P1-P8 analysis/report code for G. I will write it test-first on synthetic data (CPU only) after the run unless you want it before; say so.

## Full G run (admin PowerShell, AC power, clean tree, Armoury Crate Performance, Chrome and other apps closed, do not click in the window)
cd C:\Users\arjun\governor
python experiments\w2_colocation\run.py --part G --ambient-c 25 --armoury-mode Performance
