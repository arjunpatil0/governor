# STATUS (overwritten at every stop)
Updated 2026-10-24 - Phase: W4-5. The phantom-energy hypothesis for the governed-cell power is pre-registered (addendum O-4) with an automatic gate; everything is ready for tonight's run. Waiting for YOU: restart -> helper -> the diag + gate + T3b block (docs/W5B_T3B_SITTING.md, commands unchanged).

## Done since the last stop (journal 0054, addenda O-3 section 6 and O-4)
- Hypothesis: the Governor reads the NVML energy counter 10.0 times/s (measured in the sitting's gov_log), each extra read adds ~4.2 J (journal 0005) -> +42 W predicted; observed 63-106 W at 59-63 C. Five-arm diagnostic; gate verdicts CONFIRMED_PHANTOM (T3b runs with the sampled power source, chosen automatically), NO_ANOMALY (energy source), STOP (anything else; T3b refused). The gate prints counter / sampled / difference / reads per second / tok/s per arm and predicted vs observed inflation.
- Audit: no W1, W2 or W5a number is affected; smoke-1 governor power (invalid anyway), smoke-1 daemon energy column (unused) and the W5b governed cells (void) are. The morning check now fails a cell whose counter and sampled power differ by more than 15%.
- c'B token estimate scaled to the commanded clock; infeasible comparators confirmed in writing (score 0; vacuous non-inferiority passes labelled in the report); d'B-HGB accepted with the reviewer's conditions, NOT built.

- Gate amended (journal 0055, O-4 section 5): both passing verdicts also require the no-reads Governor arm to make the same tok/s as the static arm (within 15%), else STOP; diag_cb vs diag_cb_sampled tok/s is printed side by side (not gated).

## Waiting for
You: the run. If the gate says STOP, nothing else runs - paste the output (that is the result).

## Risks / not verified
- All of the above on hardware; the phantom is the leading explanation, not yet tested; governed d'B/c'B on hardware; clock flip-flops (contingency pre-stated); d'B-HGB is unbuilt (dropped if not ready by block 4).

## Notes
- Do not run pytest or rebuild before the run; exe hash bb875fbc unchanged.
