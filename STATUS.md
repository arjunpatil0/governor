# STATUS (overwritten at every stop)
Updated 2026-10-21 · Phase: W2 (A done; capped-wait addendum registered; A2 awaiting rerun; part L code not written)

## Just did (commits)
- Capped-wait addendum registered before A2 data (post-hoc, exploratory, changes no decision rule; journal 0022). Armoury Crate mode recorded: Performance for A2; A/B/C "not recorded; inferred non-Turbo".
- A2 crash fixed test-first (0a9baae; journal 0021). Experiment A results: ea8546a (journal 0020).

## Waiting for
- Arjun to run A2 (command below). I execute nothing while it runs.

## Decisions needed
1. None. The reviewer reviews A and A2 together after A2 (Arjun's decision).

## Reviewer checkpoint due?
- Results before interpretation: after A2 (A and A2 together). No design change pending.

## Experiment A2 command (admin PowerShell, AC power, clean tree, Armoury Crate in Performance mode)
cd C:\Users\arjun\governor
python experiments\w2_colocation\run.py --part A2 --ambient-c 25 --armoury-mode Performance
