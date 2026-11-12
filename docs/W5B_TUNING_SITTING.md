# W5b tuning sitting T1-T3 (written 2026-10-23, revised after the first trial; rules: plan addendum O = docs/W5B_ADDENDUM_O.md and O-1 = docs/W5B_ADDENDUM_O1.md)
The first trial ran 4 cells and crashed in the governed cell (live clock 2475 MHz outside the model range): FIXED (clamp, logged), and d'B now shares the action space of the other controllers (aligned and unaligned pacing). The d'B margin grid is NOT in this sitting any more (block T3b later). Run the supervised TRIAL again (step 3, about 10 min, ALL SIX cells must print without an exception) before the overnight sitting. The sitting is unattended only after that.

## Before you start (checklist)
RESTART the laptop first: the trial and the sitting both refuse an uptime above 2 h. Sequence: restart -> step 1 -> step 3 (trial, about 10 min) -> step 4 (sitting) all within the same 2 h.
Windows Update and NVIDIA driver updates paused; AC power; Armoury Crate mode Performance; Battery Health Charging Balanced 80% (recorded); Chrome closed; tray apps quit; nothing else running. Do NOT run pytest or rebuild anything; the working tree must be clean and committed (it is: git head is recorded in meta.json).
Overnight only: keep the lid open and stop the laptop from sleeping on AC, in a normal PowerShell (revert command at the end):
```powershell
powercfg /change standby-timeout-ac 0
powercfg /change hibernate-timeout-ac 0
```

## 1. Administrator PowerShell: start the helper (leave the window open)
```powershell
nvidia-smi -rgc; nvidia-smi -rmc
cd %USERPROFILE%\governor; python actuators/clock_helper.py --config C:\ProgramData\governor\clock_helper.json --log C:\ProgramData\governor\clock_helper.log
```
(The Ctrl+C fix passed its elevated check on 2026-10-23: prompt back, "shutting down... clock reset done". Nothing more to check at the start.)

## 3. Normal PowerShell: supervised trial (about 10 min; six cells, one per executor path; not data)
```powershell
cd %USERPROFILE%\governor
python experiments/w5b/tune.py --out data/w5b/trial2 --armoury-mode Performance --trial
```
Paste back the six TRIAL lines. Changes since the first trial (addenda O-1, O-2): c'B and d'B both switch pacing mode inside the cell; the fg-alone cell now runs twice (about 40 s): c0m at a LOCKED 1800 MHz (expected about 7 ms = nominal; the morning check flags a ratio outside 0.85-1.15) and c0m_unlocked with the SM clock logged for both (we expect about 6.7 ms and an SM median clearly below 2460 if the GPU does not hold boost when 40% busy). The new fields clamp_events and final_pacing_mode are in the cell.json files. Other expected shape (hardware numbers will differ): bg-alone about 97 tok/s for the 3B; arm a misses a lot; the static cell at 1500 MHz gives 0 tok/s (frame 8.5 ms, no slack: expected, not a bug); c'B and d'B print miss, tok/s, power and clock_changes; no exception. If anything raises, stop and paste the traceback. Also paste `Get-Content data/w5b/trial2/cells/trial_fgalone/cell.json | Select-String "c0m|sm_"`.

## 4. The overnight sitting (T1 -> T2 -> T3 chained; resumable; one command)
```powershell
cd %USERPROFILE%\governor
for ($i = 1; $i -le 3; $i++) { python experiments/w5b/tune.py --out data/w5b/tuning --armoury-mode Performance --max-hours 11; if ((Test-Path data/w5b/tuning/decisions.json) -or ($LASTEXITCODE -eq 1) -or ($LASTEXITCODE -eq 3)) { break }; Start-Sleep -Seconds 60 }
```
What it does: refuses to start unless uptime <= 2 h, AC, Armoury mode given, clean tree, Chrome closed; writes meta.json (Armoury mode, battery mode, boot time, uptime, git head, exe hash, yaml and addendum hashes); runs the discarded cell, the three background-alone references, the c0 search 7..11 (each tried c0 with a foreground-alone cell and arm a in S1; the 70-static sweep only where arm a misses more than 5%), stage 2, g'B/eB and the c'B grid (36 cells); stores every cell as it finishes; recomputes all decisions from the stored cells; writes decisions.json and manifest.json. Each cell: 5 s warm-up + 60 s measured, 20 s minimum cool-down and below 55 C. A failure on two consecutive cells, a clock lock that is not released, a temperature above 85 C or a HwThermalSlowdown / HwPowerBrake event stops the sitting (finished cells are kept); the retry loop resumes only after a plain stop (exit code 2 without decisions.json), never after an abort (exit code 1) or the time limit (exit code 3). --max-hours 11 stops starting new cells after 11 h.
Size (ESTIMATE): the simulator dry run of this exact plan produced 127 cells, about 3.5 h at about 100 s per cell (the trial's cells took 52 s, 15 s, 80 s, 80 s, plus about 30 s of cool-down and start-up each); if the hardware needs several c0 sweeps it can reach about 450 cells (12 h; the time limit then stops new cells and exits with code 3). A re-run of the same command in the SAME boot resumes without the uptime refusal (meta.json keeps the original sitting start and notes the resume); after a reboot the fresh-restart rule applies again. The measured cell time replaces the estimate.

## 5. Morning / end-of-run checks
Normal PowerShell:
```powershell
cd %USERPROFILE%\governor
python experiments/w5b/morning.py --out data/w5b/tuning
nvidia-smi --query-gpu=temperature.gpu,clocks.sm,power.draw --format=csv
```
Paste the output. It lists the cell count, incidents, flags (thermal / power-brake bits, clock not applied, abandoned frames, ring drops, temperature >= 83 C, partial offload), the meta (Armoury mode, battery mode, boot time, uptime, git head, exe hash), the c0 search, g'B per budget, c'B pacing and constants, the clamp total and the manifest check. "decisions.json missing" or a stop report means the sitting stopped: do not rerun anything by hand, paste the output.
Then Ctrl+C the helper (note the time to the prompt and the message) and in the ADMIN window:
```powershell
nvidia-smi -q -d CLOCK | Select-String "Applications|SM"
Get-Content C:\ProgramData\governor\clock_helper.log -Tail 30
```
Revert the sleep settings (normal PowerShell; use your previous values if they were not these):
```powershell
powercfg /change standby-timeout-ac 30
powercfg /change hibernate-timeout-ac 0
```
Tell me the /export path if you made one.
