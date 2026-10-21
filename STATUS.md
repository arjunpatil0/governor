# STATUS (overwritten at every stop)
Updated 2026-10-22 · Phase: W2 (A and A2 done and analysed; reviewer checkpoint due; part L code not written)

## Just did (commits)
- A2 analysed (journal 0023): SA1 phase-independent; SA2 k = 0.395 (s0 0.30 ms); SA3 no priority effect; SA4: fg 4 ms slowdown above 1+d, fg 9 ms overloaded at duty >= 0.5; exploratory tau = 0.260 ms (re-description of A's own cells, not an independent test; the curve also has a dip near 0.6 ms the model does not describe). Sensitivity without the 9 Chrome-window cells changes nothing material. Stall cells: latency and clocks normal, power lower.
- Incidents logged (Chrome, two QuickEdit stalls, analysis path bug). run.py hardened test-first: QuickEdit disabled at start, 30 s timeout on every nvidia-smi call. Full suite 110 passed.
- Earlier: Experiment A results (journal 0020), capped-wait addendum (journal 0022).

## Waiting for
- Reviewer: A + A2 together (journals 0020 and 0023, data/w2_A_results.md, data/w2_A_secondary_results.md). I execute nothing until Arjun decides.

## Decisions needed
1. The pre-stated globaltimer trigger is MET (SA2 k = 0.395 far from 1; SA4 fg4 slowdown above 1+d). Write the globaltimer addendum now? Recommendation: wait for the reviewer to see A and A2 first; they may want a different diagnostic.
2. Start part L (llama.cpp) code and tests now (nothing executing during runs)? Recommendation: yes.

## Reviewer checkpoint due?
- Results before interpretation: YES (A2, together with A). Surprise: yes (k far below 1; dip in the wait curve near 0.6 ms). Design change: none yet (possible globaltimer addendum).
