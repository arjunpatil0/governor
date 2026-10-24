# W5b block T3b sitting (written 2026-10-24; rules: plan addendum O-3 = docs/W5B_ADDENDUM_O3.md; the T1-T3 commands of docs/W5B_TUNING_SITTING.md are DONE)
Order inside one boot: restart -> helper -> DIAGNOSTIC (4 cells, about 8 min) -> the diagnostic gate (automatic) -> T3b (67 cells, about 1.9 h) -> morning checks. T3b runs ONLY if the gate passes. The d'B-HGB margin grid is not in this sitting (its controller does not exist yet, addendum O-3 section 5).
What changed since the last sitting: c'B's switching threshold is token-aware (period - clean token); every hardware cell logs a second, independent power measure; a diagnostic A/B for the governed-cell power anomaly (63-106 W at a few tok/s in all 36 c'B cells of the T1-T3 sitting; the c'B constants of that sitting are VOID).

## Before you start
RESTART the laptop (the diagnostic and T3b refuse an uptime above 2 h). Windows Update and NVIDIA driver updates paused; AC power; Armoury Crate Performance; Battery Health Charging Balanced 80%; Chrome closed; tray apps quit; nothing else running. Do NOT run pytest or rebuild anything. The tree is committed.
Optional (the run is about 2 h; skip if you stay at the laptop): `powercfg /change standby-timeout-ac 0` and `powercfg /change hibernate-timeout-ac 0` (revert with 30 and 0).

## 1. Administrator PowerShell: start the helper (leave it open)
```powershell
nvidia-smi -rgc; nvidia-smi -rmc
cd C:\Users\arjun\governor; python actuators/clock_helper.py --config C:\ProgramData\governor\clock_helper.json --log C:\ProgramData\governor\clock_helper.log
```

## 2. Normal PowerShell: diagnostic, gate, and (only on PASS) T3b, in one block
```powershell
cd C:\Users\arjun\governor
python experiments/w5b/tune.py --out data/w5b/diag --armoury-mode Performance --diag
python experiments/w5b/morning.py --out data/w5b/diag --gate diag
if ($LASTEXITCODE -eq 0) { for ($i = 1; $i -le 3; $i++) { python experiments/w5b/tune.py --out data/w5b/t3b --plan t3b --c0 7 --armoury-mode Performance --max-hours 4; if ((Test-Path data/w5b/t3b/decisions.json) -or ($LASTEXITCODE -eq 1) -or ($LASTEXITCODE -eq 3)) { break }; Start-Sleep -Seconds 60 } } else { Write-Host "DIAG GATE FAILED: T3b not started. Paste the output above." }
```
The diagnostic prints four lines (diag_static, diag_gov_static, diag_gov_static_noenergy, diag_cb) with miss, tok/s, energy-counter power, SAMPLED power and temperature; the gate prints PASS or FAIL with reasons. PASS means: the same action draws within 15% of the static path when run through the Governor loop, and every cell's energy-counter power is within 15% of its sampled power. If the gate FAILS, nothing else runs; paste the whole output (that is the result of the night).
If it PASSES, T3b runs: a discarded cell, the d'B margin grid (30 cells) and the c'B constants re-run (36 cells) at c0 = 7; stops are resumable (same command, same boot); `--max-hours 4` caps it.

## 3. After the run
```powershell
cd C:\Users\arjun\governor
python experiments/w5b/morning.py --out data/w5b/diag
python experiments/w5b/morning.py --out data/w5b/t3b
nvidia-smi --query-gpu=temperature.gpu,clocks.sm,power.draw --format=csv
```
Paste the output. Then Ctrl+C the helper once and, in the ADMIN window: `nvidia-smi -q -d CLOCK | Select-String "Applications|SM"` and `Get-Content C:\ProgramData\governor\clock_helper.log -Tail 30`. Tell me the /export path if you made one.
