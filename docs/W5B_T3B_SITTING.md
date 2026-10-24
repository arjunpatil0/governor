# W5b block T3b sitting (written 2026-10-24, revised the same evening; rules: plan addenda O-3 = docs/W5B_ADDENDUM_O3.md and O-4 = docs/W5B_ADDENDUM_O4.md; the T1-T3 commands of docs/W5B_TUNING_SITTING.md are DONE)
Order inside one boot: restart -> helper -> DIAGNOSTIC (5 cells, about 9 min) -> the diagnostic gate (automatic, prints the verdict) -> T3b (67 cells, about 1.9 h, with the power source the gate selected) -> morning checks. T3b runs ONLY if the gate passes. The d'B-HGB margin grid is not in this sitting (its controller does not exist yet, addendum O-3 section 5).
What changed since the last sitting: c'B's switching threshold is token-aware (period - clean token); every hardware cell logs a second, independent power measure; a diagnostic A/B for the governed-cell power anomaly (63-106 W at a few tok/s in all 36 c'B cells of the T1-T3 sitting; the c'B constants of that sitting are VOID). Leading explanation, PRE-REGISTERED with its prediction and decision rule in addendum O-4: the Governor loop reads the NVML energy counter 10 times a second and each extra read adds about 4.2 J of phantom energy (about +42 W). New in this run: the Governor can take its power signal from the mean of the NVML power samples instead (no energy reads in the loop); the gate chooses automatically.

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
The commands are the same as before; what they do has changed. The diagnostic runs FIVE cells (the same g'B action through the static path, through the Governor loop with its energy reads, through the Governor loop without them; c'B with energy reads; c'B on the sampled power source), then the gate prints, for every arm, the energy-counter power, the independent sampled power, their difference, the Governor's energy reads per second and tok/s, followed by the PREDICTED phantom inflation (4.2 J x reads/s, about 42 W) next to the OBSERVED one, and one of three verdicts:
- CONFIRMED_PHANTOM (exit code 0): the prediction holds; T3b starts and runs with the sampled power source (written to data/w5b/diag/power_source.json and into every governed cell and meta.json).
- NO_ANOMALY (exit code 0): the counter agrees with the sampled power on all arms; T3b starts with the energy source as designed.
- STOP (exit code 1): anything else (for example the no-reads arm is also off); T3b does NOT start. Paste the whole output: that is the result of the night.
`tune.py --plan t3b` also refuses to start by itself without a usable verdict. T3b: a discarded cell, the d'B margin grid (30 cells) and the c'B constants re-run (36 cells) at c0 = 7; stops are resumable (same command, same boot); `--max-hours 4` caps it.

## 3. After the run
```powershell
cd C:\Users\arjun\governor
python experiments/w5b/morning.py --out data/w5b/diag
python experiments/w5b/morning.py --out data/w5b/t3b
nvidia-smi --query-gpu=temperature.gpu,clocks.sm,power.draw --format=csv
```
Paste the output. Then Ctrl+C the helper once and, in the ADMIN window: `nvidia-smi -q -d CLOCK | Select-String "Applications|SM"` and `Get-Content C:\ProgramData\governor\clock_helper.log -Tail 30`. Tell me the /export path if you made one.
