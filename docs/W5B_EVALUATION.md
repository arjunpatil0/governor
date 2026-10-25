# W5b evaluation blocks 4-13: how they run (written 2026-10-24; rules: addenda O-5 and O-6 = docs/W5B_ADDENDUM_O5.md, O6.md; code: experiments/w5b/evaluate.py, eval_lib.py, freeze.py; tests/test_w5b_eval.py)
STATUS (2026-10-25): constants FROZEN and committed (data/w5b/constants.json, addendum O-7), sha256 4aa2541d14271e00a9cfc245e2ad71aecab3ded795ce00a5c92193f1834f5974. NOT YET RUNNABLE for data: the supervised trial must be re-run first (3 of its 6 cells changed their steering budget because the headroom was corrected to the registered 2.692 W; section "Step A" at the end). Nothing below has been run on the hardware with these constants.

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

## Frozen constants (data/w5b/constants.json; sha256 4aa2541d14271e00a9cfc245e2ad71aecab3ded795ce00a5c92193f1834f5974)
c0 7 ms; g'B 60 W = 1800_a_g0_d1, 35 W = 1500_a_g0_d1; c'B target 0.2, ki 0.15, guard0 0.5, gmin 0.3 (selection O-7 = the registered pick; the miss rule was NOT met; at the grid edge; 0.6 tok/s: a degenerate comparator, see addendum O-7 section 2); d'B margin 0.3; power headroom 2.692 W (steering parameter 59.080 W at 60 W, 33.307 W at 35 W; feasibility on the counter, no tolerance); power source sampled. Any change to the file changes the hash and the runner refuses.

## Step A: re-run the supervised trial (about 15 min; six cells, not data). Needed because 3 of the 6 cells changed.
1. RESTART the laptop (uptime must be <= 2 h when each command starts). Armoury Crate Performance, AC power, Chrome closed, tray apps quit, Windows Update and NVIDIA updates paused. If you reverted the sleep settings, set them again in a normal PowerShell: `powercfg /change standby-timeout-ac 0` and `powercfg /change hibernate-timeout-ac 0`.
2. Administrator PowerShell, leave it open:
```powershell
nvidia-smi -rgc; nvidia-smi -rmc
cd C:\Users\arjun\governor; python actuators/clock_helper.py --config C:\ProgramData\governor\clock_helper.json --log C:\ProgramData\governor\clock_helper.log
```
3. Normal PowerShell (the trial, then its automatic check only if the trial ran):
```powershell
cd C:\Users\arjun\governor
python experiments/w5b/evaluate.py --trial --blocks 4 --constants data/w5b/constants.json --constants-sha256 4aa2541d14271e00a9cfc245e2ad71aecab3ded795ce00a5c92193f1834f5974 --out data/w5b/eval_trial2 --armoury-mode Performance; if ($LASTEXITCODE -eq 0) { python experiments/w5b/evaluate.py --check-trial --out data/w5b/eval_trial2 }
```
Expect `TRIAL CHECK: PASS (6 cells)`. The first trial (data/w5b/eval_trial, headroom 2.64 W) stays as a record. If the check fails, stop and paste the output.

## Step B: evaluation session 1 = the first two evaluation blocks (numbered 4 and 5; 90 cells; the runner's own estimate 2.5 h, limit 3 h)
Only after Step A printed PASS. It may follow Step A in the SAME boot (the uptime rule is checked when the command starts: it must be <= 2 h then). The working tree must be clean (the constants and docs are committed; untracked files under data/ are fine). The helper window stays open.
```powershell
cd C:\Users\arjun\governor
python experiments/w5b/evaluate.py --blocks 4 5 --constants data/w5b/constants.json --constants-sha256 4aa2541d14271e00a9cfc245e2ad71aecab3ded795ce00a5c92193f1834f5974 --out data/w5b/eval --armoury-mode Performance
```
Each block is whole or discarded; an incident stops the session with exit code 2, the incomplete block is discarded at the next call and rerun under the next free number with `--as-block` (I give the literal command then). Do not use the laptop during the session. At the end: Ctrl+C in the helper window once, then paste the last 20 lines of the session output and the helper-log lines (docs/W5B_T3C_SITTING.md section 3). Later sessions (6 7 / 8 9 10 / 11 12 13) use the same command with the other block numbers.
