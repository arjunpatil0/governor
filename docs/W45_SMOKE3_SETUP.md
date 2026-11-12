# W4-5 hardware smoke 3 (diagnostic, NOT a result; written 2026-10-22)
Question: with the pace-view fix (journal 0041), does the driver's fit test gate the tokens? Aligned guard 0 and 1 ms at constant frame cost 4 ms (slack about 12.7 ms), 7 ms (about 9.7 ms) and 9 ms (about 7.6 ms) against a 10.1 ms token, plus an unaligned reference at 9 ms (does overlap break the deadline there?).
Expected (an expectation, not a result): cost 4: tokens fit, few long tokens; cost 7: almost no tokens start; cost 9: none start. 6 runs of 25 s, clock unlocked. Records tok_ms, overrun, fg latency, both token estimates and the overlap flag per run; analysis: python analysis/smoke2_report.py data/w45_smoke/smoke3

## Before you start (hands off the machine during the run)
AC power; Armoury Crate mode Performance; Chrome closed; tray apps quit.

## 1. Administrator PowerShell: restart the helper (leave the window open)
```powershell
# Release any leftover clock lock so the smoke starts from a known state
nvidia-smi -rgc; nvidia-smi -rmc

# Start the helper from the repository
cd %USERPROFILE%\governor; python actuators/clock_helper.py --config C:\ProgramData\governor\clock_helper.json --log C:\ProgramData\governor\clock_helper.log
```

## 2. Second (normal) PowerShell: warm the REBUILT exe once, then run the smoke
```powershell
cd %USERPROFILE%\governor
python experiments/w4_smoke/smoke.py warm --run data/w45_smoke/smoke3 --armoury-mode Performance
python experiments/w4_smoke/smoke.py gate --run data/w45_smoke/smoke3 --armoury-mode Performance
```
Estimate (not measured): warm about 1 min, gate about 4-5 min.

## 3. When it prints the final JSON (or an error): Ctrl+C the helper window, then in the ADMIN window paste back
```powershell
nvidia-smi -q -d CLOCK | Select-String "Applications|SM"
Get-Content C:\ProgramData\governor\clock_helper.log -Tail 30
```
