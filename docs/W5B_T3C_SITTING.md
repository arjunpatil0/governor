# W5b block T3c sitting (written 2026-10-24; rules: addendum O-6 = docs/W5B_ADDENDUM_O6.md; T1-T3, the diagnostic and T3b are DONE)
T3c extends the c'B comparator grid to the targets 0.35 and 0.2 (x ki 0.05 and 0.15) on the same six workload / scene cells, so that the comparator is not under-tuned: 1 discarded cell + 24 cells = 25 cells, about 42 min at 100 s. The unchanged choice rule is then applied to the full 10-combination grid. Power source: sampled (addendum O-5). One extension only.

## Before you start
RESTART the laptop (uptime must be <= 2 h). Windows Update and NVIDIA driver updates paused; AC power; Armoury Crate Performance; Battery Health Charging Balanced 80%; Chrome closed; tray apps quit; nothing else running. Do NOT run pytest or rebuild anything. The tree is committed.

## 1. Administrator PowerShell: start the helper (leave it open)
```powershell
nvidia-smi -rgc; nvidia-smi -rmc
cd C:\Users\arjun\governor; python actuators/clock_helper.py --config C:\ProgramData\governor\clock_helper.json --log C:\ProgramData\governor\clock_helper.log
```

## 2. Normal PowerShell: T3c (resumable)
```powershell
cd C:\Users\arjun\governor
for ($i = 1; $i -le 3; $i++) { python experiments/w5b/tune.py --out data/w5b/t3c --plan t3c --c0 7 --merge-from data/w5b/t3b --power-source sampled --armoury-mode Performance --max-hours 2; if ((Test-Path data/w5b/t3c/decisions.json) -or ($LASTEXITCODE -eq 1) -or ($LASTEXITCODE -eq 3)) { break }; Start-Sleep -Seconds 60 }
```
The T3b cells are merged read-only (never re-run); only the discarded cell and the 24 new cells run. Same exit-code rules as before (2 = plain stop, resumed; 1 = abort or refusal, 3 = time limit).

## 3. After the run
```powershell
cd C:\Users\arjun\governor
python experiments/w5b/morning.py --out data/w5b/t3c
nvidia-smi --query-gpu=temperature.gpu,clocks.sm,power.draw --format=csv
```
Paste the output (expect 0 problems; the c_b line shows the chosen constants, rule_met and whether the winner is again at the grid edge). Then Ctrl+C the helper once and in the ADMIN window paste BOTH:
```powershell
Get-Content C:\ProgramData\governor\clock_helper.log | Select-String "ERR|FAIL|refused|WARNING|startup|shutdown|not needed|rate" | Select-Object -Last 80
Get-Content C:\ProgramData\governor\clock_helper.log -Tail 30
```
I cannot read the helper log from my side (Administrators only); the T3b sitting's log was not checked for that reason (addendum O-6 section 4). If you still have the window of that sitting open or the file untouched, the first command also covers it (it lists the last 80 notable lines). Tell me the /export path if you made one.

## 4. What I do next (not yours)
Freeze the constants (experiments/w5b/freeze.py from the three decisions files), commit data/w5b/constants.json, and give you the supervised evaluation trial and the session commands with the literal hash (docs/W5B_EVALUATION.md).
