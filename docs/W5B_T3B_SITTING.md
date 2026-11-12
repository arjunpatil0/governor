# W5b block T3b sitting (rewritten 2026-10-24 after the diagnostic; rules: plan addenda O-3, O-4 and O-5 = docs/W5B_ADDENDUM_O3.md, O4.md, O5.md; the T1-T3 commands of docs/W5B_TUNING_SITTING.md are DONE; the diagnostic is DONE)
The diagnostic ran: the pre-registered gate printed STOP on the MAGNITUDE of the phantom (7.5 J per read in the g'B state, 2.7 J in the c'B state, against the assumed 4.2 J); every qualitative prediction held, and the fix arm (power from the mean of the NVML power samples, no energy reads in the loop) restored c'B from 5.7 to 12.7 tok/s. Addendum O-5 (post hoc) adopts the SAMPLED power source for T3b and every evaluation block. The gate output is not edited; it stays STOP.
So the T3b command passes the source explicitly. There is no diagnostic in this sitting any more.

## Before you start
RESTART the laptop (T3b refuses an uptime above 2 h). Windows Update and NVIDIA driver updates paused; AC power; Armoury Crate Performance; Battery Health Charging Balanced 80%; Chrome closed; tray apps quit; nothing else running. Do NOT run pytest or rebuild anything. The tree is committed.
Optional (about 2 h; skip if you stay at the laptop): `powercfg /change standby-timeout-ac 0` and `powercfg /change hibernate-timeout-ac 0` (revert with 30 and 0).

## 1. Administrator PowerShell: start the helper (leave it open)
```powershell
nvidia-smi -rgc; nvidia-smi -rmc
cd %USERPROFILE%\governor; python actuators/clock_helper.py --config C:\ProgramData\governor\clock_helper.json --log C:\ProgramData\governor\clock_helper.log
```

## 2. Normal PowerShell: T3b (67 cells, about 1.9 h at 100 s per cell; resumable)
```powershell
cd %USERPROFILE%\governor
for ($i = 1; $i -le 3; $i++) { python experiments/w5b/tune.py --out data/w5b/t3b --plan t3b --c0 7 --power-source sampled --armoury-mode Performance --max-hours 4; if ((Test-Path data/w5b/t3b/decisions.json) -or ($LASTEXITCODE -eq 1) -or ($LASTEXITCODE -eq 3)) { break }; Start-Sleep -Seconds 60 }
```
What it does: a discarded cell, the d'B margin grid (5 margins x 3 workloads x {S0, S1} = 30 cells) and the c'B constants grid re-run under the final controller (36 cells), all at c0 = 7, 60 W. Every governed cell takes its power from the mean of the NVML power samples and reads the energy counter ZERO times in its loop (the executor rejects a cell where it did not; meta.json records power_source = sampled). The retry loop resumes only after a plain stop (exit code 2); exit code 1 (an abort or a refusal) and 3 (the time limit) end it. A refusal message that mentions addendum O-5 means the explicit source was not accepted: paste it.

## 3. After the run
```powershell
cd %USERPROFILE%\governor
python experiments/w5b/morning.py --out data/w5b/t3b
nvidia-smi --query-gpu=temperature.gpu,clocks.sm,power.draw --format=csv
```
Paste the output. What to expect: 0 problems (a problem is, among others, a governed cell whose counter power and sampled power differ by more than 15%, or whose loop read the energy counter); decisions for d'B (margin by the rule of addendum O section 2) and c'B (constants; rule_met may be False: report it); clock changes at governed-cell start (contingency in addendum O-4 section 4 if 3 or more occur in the first 5 s). Then Ctrl+C the helper once and, in the ADMIN window: `nvidia-smi -q -d CLOCK | Select-String "Applications|SM"` and `Get-Content C:\ProgramData\governor\clock_helper.log -Tail 30`. Tell me the /export path if you made one.
