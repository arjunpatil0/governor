# W5b tuning sitting T1-T3 (written 2026-10-23; rules: plan addendum O = docs/W5B_ADDENDUM_O.md)
The hardware executor (experiments/w5b/executors.py HwExecutor) has NEVER run on the GPU. Run the supervised TRIAL (step 3, about 10 min) before the overnight sitting. The sitting is unattended only after the trial printed sane numbers.

## Before you start (checklist)
Fresh restart (uptime must be <= 2 h; the script refuses otherwise); Windows Update and NVIDIA driver updates paused; AC power; Armoury Crate mode Performance; Battery Health Charging Balanced 80% (recorded); Chrome closed; tray apps quit; nothing else running. Do NOT run pytest or rebuild anything; the working tree must be clean and committed (it is: git head is recorded in meta.json).
Overnight only: keep the lid open and stop the laptop from sleeping on AC, in a normal PowerShell (revert command at the end):
```powershell
powercfg /change standby-timeout-ac 0
powercfg /change hibernate-timeout-ac 0
```

## 1. Administrator PowerShell: restart the helper (leave the window open)
```powershell
nvidia-smi -rgc; nvidia-smi -rmc
cd C:\Users\arjun\governor; python actuators/clock_helper.py --config C:\ProgramData\governor\clock_helper.json --log C:\ProgramData\governor\clock_helper.log
```

## 2. First elevated check of the Ctrl+C fix (once, right after step 1)
Press Ctrl+C ONCE in the helper window. Expected: the prompt is back within about 2 s and "shutting down... clock reset done" is printed. Tell me what you saw (time to prompt, the message). Then start the helper again with the second line of step 1 and leave it running.

## 3. Normal PowerShell: supervised trial (about 10 min; six cells, one per executor path; not data)
```powershell
cd C:\Users\arjun\governor
python experiments/w5b/tune.py --out data/w5b/trial --armoury-mode Performance --trial
```
Paste back the six TRIAL lines. Expected shape (the simulator gives the same pattern; hardware numbers will differ): bg-alone tok/s about 100 for the 3B; fg-alone c0m about 5 ms at c0 = 7; arm a misses a lot; the static cell, c'B and d'B print miss, tok/s, power and clock_changes; no exception. If anything raises, stop and paste the traceback.

## 4. The overnight sitting (T1 -> T2 -> T3 chained; resumable; one command)
```powershell
cd C:\Users\arjun\governor
for ($i = 1; $i -le 3; $i++) { python experiments/w5b/tune.py --out data/w5b/tuning --armoury-mode Performance --max-hours 11; if ((Test-Path data/w5b/tuning/decisions.json) -or ($LASTEXITCODE -eq 1) -or ($LASTEXITCODE -eq 3)) { break }; Start-Sleep -Seconds 60 }
```
What it does: refuses to start unless uptime <= 2 h, AC, Armoury mode given, clean tree, Chrome closed; writes meta.json (Armoury mode, battery mode, boot time, uptime, git head, exe hash, yaml and addendum hashes); runs the discarded cell, the three background-alone references, the c0 search 7..11 (each tried c0 with a foreground-alone cell and arm a in S1; the 70-static sweep only where arm a misses > 5%), stage 2, the c'B grid (36 cells) and the d'B margin grid (30 cells); stores every cell as it finishes; recomputes all decisions from the stored cells; writes decisions.json and manifest.json. Each cell: 5 s warm-up + 60 s measured, 20 s minimum cool-down and below 55 C. A failure on two consecutive cells, a clock lock that is not released, a temperature above 85 C or a HwThermalSlowdown / HwPowerBrake event stops the sitting (finished cells are kept); the retry loop above resumes only after a plain stop (exit code 2 without decisions.json), never after an abort (exit code 1) or the time limit (exit code 3). --max-hours 11 stops starting new cells after 11 h.
Size (ESTIMATE): the simulator dry run of this exact plan produced 157 cells, about 4.4 h at about 100 s per cell; if the hardware needs several c0 sweeps it can reach about 480 cells (13 h; --max-hours 11 stops starting new cells and exits with code 3, which ends the loop). A re-run of the same command in the SAME boot resumes without the uptime refusal (meta.json keeps the original sitting start and notes the resume); after a reboot the fresh-restart rule applies again. The measured cell time replaces the estimate.

## 5. Morning checks
Normal PowerShell:
```powershell
cd C:\Users\arjun\governor
python experiments/w5b/morning.py --out data/w5b/tuning
```
Paste the output. Then Ctrl+C the helper (second use of the new Ctrl+C: note the time and the message) and in the ADMIN window:
```powershell
nvidia-smi -q -d CLOCK | Select-String "Applications|SM"
Get-Content C:\ProgramData\governor\clock_helper.log -Tail 30
```
Revert the sleep settings (normal PowerShell; use your previous values if they were not these):
```powershell
powercfg /change standby-timeout-ac 30
powercfg /change hibernate-timeout-ac 0
```
Tell me the /export path if you made one. A stop report (decisions.json "stop") means the HW0 gate failed at every c0 or the sitting was aborted: do not rerun anything, paste the morning output.
