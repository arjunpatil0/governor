# W5b evaluation blocks 4-13: how they run (written 2026-10-24; rules: addenda O-5 and O-6 = docs/W5B_ADDENDUM_O5.md, O6.md; code: experiments/w5b/evaluate.py, eval_lib.py, freeze.py; tests/test_w5b_eval.py)
STATUS: NOT RUNNABLE YET. It needs (1) T3c done (docs/W5B_T3C_SITTING.md), (2) the constants frozen and committed by me (data/w5b/constants.json, its sha256 printed by freeze.py), (3) the supervised trial below. The literal commands, with the hash, are added by me after the freeze; this file only fixes the structure.

## Structure
10 evaluation blocks, numbered 4-13. A block = 25 primary cells (scenes S0, S1, S1d, S2, S5 x controllers g'B, eB, c'B, d'B at 60 W, plus the reference arm a in the 5 scenes); blocks 4-8 add the 20 exploratory 35 W cells (no arm a): 45 cells. S3 and d'B-HGB are not built. Cell order inside a block is seeded-random. Background: 3B for S0, S1, S1d, S2; the held-out Llama-3.1-8B for S5 (its sha256 is checked the first time it is needed). Every governed cell uses the sampled power source and reads the energy counter zero times. Estimate 100 s per cell.
Sessions (whole blocks only, at most 3 h by the runner's own estimate, a FRESH RESTART before each; the runner refuses otherwise):
- session 1: blocks 4 5 (90 cells, about 2.5 h)
- session 2: blocks 6 7 (90 cells, about 2.5 h)
- session 3: blocks 8 9 10 (95 cells, about 2.6 h)
- session 4: blocks 11 12 13 (75 cells, about 2.1 h)
The configuration (git head of code, the yaml, exe hash, frozen constants, helper config) must be IDENTICAL across sessions; each session writes meta.json (Armoury mode, battery mode, boot time, uptime, power source, constants hash). A block interrupted by an incident is left incomplete, discarded whole by the next call and rerun under the next free block number with the same seed list (`--as-block`). Output: data/w5b/eval/results.csv (columns of analysis/w5_analysis.py) and one directory per block; the registered analysis is `python analysis/w5_analysis.py data/w5b/eval/results.csv` once all blocks are done.

## Supervised trial (before block 4; about 12 min; six cells, not data)
`evaluate.py --trial` runs one cell for each path the evaluation adds: d'B on the held-out 8B (S5), eB with an idle phase (S2), c'B in S1d, a static g'B (S0), arm a on the 8B, a 35 W d'B cell. Expect: 8B loads with all layers on the GPU, power_source sampled, gov_reads 0, counter and sampled power within 15%.
