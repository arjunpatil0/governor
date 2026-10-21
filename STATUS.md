# STATUS (overwritten at every stop)
Updated 2026-10-21 · Phase: W2 (A done and analysed; A2 pending; llama.cpp part L code not written)

## Just did (commits)
- Experiment A analysed (journal 0020): HA1 NOT SUPPORTED (slope 0.013, CI [0.013, 0.013]; 17% of cells within +/-25%), classified preempted_or_concurrent by the pre-registered ordered rule; HA2 NOT SUPPORTED (3/6 significant). Observed added wait 0.15-0.30 ms regardless of slice length 0.25-8 ms; predicted 0.13-8.5 ms. 39/190 cells flagged start_temp_not_reached (kept). Results + raw data committed (see git log).
- Earlier: 4a6fcd4 (traces review response), b349750 (journal 0019), c51b499 (B).

## Waiting for
- Arjun's go-ahead / reviewer pass on A's results, and Arjun to run A2. I execute nothing while it runs.

## Decisions needed
1. Run A2 next, before any interpretation of A? Recommendation: yes (A2's SA1 phase-independence and SA2 stretch are the pre-registered characterisation of exactly this outcome).
2. Reviewer checkpoint: A's results are in; interpretation is deliberately minimal (no mechanism). Recommendation: have the reviewer read journal 0020 and data/w2_A_results.md before A2 or in parallel with it.

## Reviewer checkpoint due?
- Results before interpretation: YES (A). Surprise: yes (model off by up to 28x at m=8). Pre-registration/design change: none.

## Experiment A2 command (admin PowerShell, AC power, clean tree)
cd C:\Users\arjun\governor
python experiments\w2_colocation\run.py --part A2 --ambient-c 25
