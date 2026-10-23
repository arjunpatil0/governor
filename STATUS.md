# STATUS (overwritten at every stop)
Updated 2026-10-23 - Phase: W4-5. Addendum N registered (e215814) and the ONE post-hoc re-run done: NO candidate passes; the fixed fallback applies (option B: d'B uses the grey-box ModelController with the safety shield). Stopped for review of the re-run result.

## Result (journal 0049, data/w5a/selection2.md)
- G: 39 false-feasible cells (22.5%), 4/10 false-feasible picks. GP, MLP: also fail the false-feasible gates. HGB: fails ONLY the ln-tok coverage gate (88.2% vs 90%; 78% when the 1B is held out); 1 false-feasible cell, 0/8 false-feasible picks, regret_rel 0.18, latency 7.97 ms (1 thread).
- Rule fixed before the run => nothing selected => fallback option B. Not adopted: HGB. Nothing tuned, no third round recommended.
- Also recorded today (journal 0048, addendum M): laptop restarted, Battery Health Charging = Balanced 80% (in meta.json), fresh restart before every W5b session; helper must be restarted in the Administrator window before any hardware step.

## Waiting for
1. Reviewer + Arjun: confirm the fallback (option B) for W5b and say whether the descriptive HGB result is only a limitation note; then the next step is W5b tuning (T1-T3) per the yaml.

## Risks / not verified
- Helper Ctrl+C untested elevated (first W5b tuning session). d'B never simulated. HW7 staleness data not analysed. The grey-box feasibility model is optimistic on this data (39 false-feasible cells): the safety shield matters. W5b not started.

## Notes
- Do NOT rebuild the driver exe (bb875fbc) or edit registered files. Run 1 = selection.md (unregistered choices marked), re-run = selection2.md (post hoc).
