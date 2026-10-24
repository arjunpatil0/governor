# STATUS (overwritten at every stop)
Updated 2026-10-24 - Phase: W4-5. The diagnostic ran; the pre-registered gate said STOP on magnitude only; every qualitative prediction held; addendum O-5 (POST HOC) adopts the sampled power source for T3b and all evaluation blocks. Waiting for YOU: restart -> helper -> the T3b command (docs/W5B_T3B_SITTING.md, rewritten; no diagnostic any more).

## Result of the diagnostic (journal 0056, addendum O-5; data/w5b/diag untouched, verdict STOP as computed)
- Counter inflated only where the Governor loop reads it (+74.7 W g'B state, +26.8 W c'B state); sampled power 39.7 / 39.6 / 39.9 W and throughput 19.9 / 20.0 / 20.0 tok/s identical across static / Governor / no-reads; fix arm: counter = sampled, c'B 5.7 -> 12.7 tok/s (miss 6% at the diagnostic constants).
- Magnitude failed: 7.5 J/read (g'B state) and 2.7 J/read (c'B state) vs the assumed 4.2 J: state-dependent (recorded in journal 0005 note, CONCEPTS, PAPER_MAP rows 28-29).

## Done
- tune.py: explicit --power-source sampled allowed for T3b (O-5 exists), auto + STOP still refused, explicit energy refused; HwExecutor default 'sampled', rejects a sampled cell whose loop read the counter; morning check fails any non-diag cell with Governor energy reads and keeps the 15% counter-vs-sampled failure. 87 related tests pass. Sweep protocol written (docs/W5B_ENERGY_READ_SWEEP_PROTOCOL.md), NOT run.

## Waiting for
You: T3b (67 cells, about 1.9 h): d'B margin grid + c'B grid re-run, power from the sampled source. d'B-HGB is accepted but not built (dropped if not ready by block 4).

## Risks / not verified
- Governed d'B / c'B in T3b on hardware; clock flip-flops (contingency in O-4); the c'B miss rate with the fix (6% at the diagnostic constants) is what the c'B grid tunes; the evaluation runner does not exist yet and must use the sampled source.

## Notes
- Do not run pytest or rebuild before the run; exe hash bb875fbc unchanged.
