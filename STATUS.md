# STATUS (overwritten at every stop)
Updated 2026-10-22 · Phase: W2 (Experiment G built and smoke-tested; one design decision blocks the full run)

## Just did (commits; see git log)
- Followed the requested order: addendum 2 registered (913fc82) -> multi-gap kernel test-first (28fb49c) -> P1-P8 analysis test-first on synthetic timelines incl. alternating suspend/resume (5fb7204) -> 15-cell smoke. Journal 0030, response reviews/2026-10-22_G_prerun_response.md. Suite 173 passed. Full G run NOT started.
- Smoke (unlocked, 1 block, not a result): overflow 0 (no untrusted blocks, no lost gaps); coverage as stated (R0.5 38% of fg requests inside the recorded interval, R1 82%, rest >= 99.5%).
- FINDING from the smoke: block gaps are not context switches beyond 3 blocks/SM. bg alone: 50.0% of blocks show ~267 us gaps; sweep 1/2/3/4/5/6 blocks per SM -> 0/0/0/25/40/50% of blocks. Witness blocks (blockIdx < 108) show 0 gaps alone. Draft addendum 3 (witness blocks, validity gate) committed as _DRAFT, NOT registered.

## Waiting for
- Reviewer + Arjun on the draft addendum 3 (experiments/w2_colocation_addendum_globaltimer_witness_2026-10-22_DRAFT.md).

## Decisions needed
1. Register addendum 3 (rename, commit before any G data), or run as registered? Recommendation: register it. As registered, P6/P7 and G_thr would be computed on blocks whose gaps are largely arbitration (bgalone 50% alone, so P7's >= 1% test is vacuous and P6 compares against starved blocks). The recorded data are identical either way (all blocks are kept), but the pre-registered reading must be fixed before data.
2. If addendum 3 is registered, the smoke suggests P4 (q 0.5-0.9 ms), P5 (s 0.2-0.3 ms) and P6 (zero overlap) may not hold as written (q ~0.375, s ~0.13, overlaps remain). I changed none of them; reviewer to say whether they stay as predictions.
3. Duration: 150 cells; the last two 15-cell smokes took 4.2 and 14.6 min (cool-down waits). Plan 1-2.5 h with the laptop untouched.

## Reviewer checkpoint due?
- Yes, before the run: the finding above and addendum 3. Results checkpoint after the run.

## Full G run (only after decision 1; admin PowerShell, AC power, clean tree, Armoury Crate Performance, Chrome and other apps closed, do not click in the window)
cd C:\Users\arjun\governor
python experiments\w2_colocation\run.py --part G --ambient-c 25 --armoury-mode Performance
