# STATUS (overwritten at every stop)
Updated 2026-10-23 - Phase: W4-5. W5a data COLLECTED and VERIFIED: 280/280 cells (sessions 94/93/93, run back to back), 0 problems. Waiting for sign-off of the model-selection protocol before anything is fitted.

## Just did (journal 0046)
- Verified W5a against the frozen list (analysis/w5a_verify.py, 4 tests; data/w5a/verification.json): no missing/extra/incident cells, manifests match, same Armoury mode / exe hash / git head in all sessions, no clock/offload/ring-drop flags, max 77 C. ~1.8 h per session (the 85 s/cell estimate was too high; ~70 s incl. cool-down).
- Flag worth knowing: 80 of 280 cells are OVERLOADED (frames abandoned; miss incl. abandoned >= 0.5) and 103 of the other 200 produced zero tokens. Analysis must use miss_frac_incl_abandoned.
- Helper Ctrl+C: handler only requests stop; main thread cancels the pipe wait, resets once, prints "shutting down... clock reset done"; second Ctrl+C ignored; 7 new tests (52 passed). Root cause of the old delay NOT reproduced; not yet run elevated with the new code.
- Drafted docs/W5A_MODEL_SELECTION_PROTOCOL.md (nothing fitted, no target values inspected beyond counts).

## Waiting for
1. Reviewer + Arjun: sign off the protocol draft, section 6: (a) whole-cell adaptation K=3 instead of "10 s", (b) targets + extra tok_s/power rule, (c) OK to pip install --use-feature=truststore lightgbm (or use sklearn HistGradientBoosting).
2. Nothing else blocks me.

## Risks (not verified)
- Candidate 1 (grey-box+RLS) needs a cell-level predict function (not written). HW7 staleness data not analysed. Helper reset errors still unexplained. d'B never simulated.

## Notes
- Do NOT rebuild the driver exe (hash bb875fbc must stay) or change the registered files. The helper is not part of the registered configuration.
