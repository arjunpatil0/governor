# W4-5 hardware smoke 2 (diagnostic, NOT a result; written 2026-10-22)
Question: why do background tokens end past the next frame arrival with aligned guard 0 (smoke 1), and which guard (0 / 0.5 / 1 / 2 ms) removes it? Does contention stretch token durations (background alone vs co-run)?
Records per run: token durations (tok_ms) and end times from the token ring, frame arrivals, overrun_ms past the next arrival (analysis/smoke_overrun.py, tested), fg p50/p99/miss, bg tok/s, mean power.
Runs (25 s each, 2 s trimmed): bg alone unaligned d1; aligned g0 d1; g0.5 d1; g1 d1; g2 d1; g0 d0.5; unaligned d1 with fg. Clock unlocked throughout. No hypothesis is tested.

## Before you start (hands off the machine during the run)
AC power; Armoury Crate mode Performance (as for the reset probe; say if it differs); Chrome closed; tray apps quit.

## 1. Administrator PowerShell: restart the helper (it has new reset handling since smoke 1; leave the window open)
```powershell
# Release any leftover clock lock so the smoke starts from a known state
nvidia-smi -rgc; nvidia-smi -rmc

# Start the helper from the repository (config already exists from the first setup)
cd %USERPROFILE%\governor; python actuators/clock_helper.py --config C:\ProgramData\governor\clock_helper.json --log C:\ProgramData\governor\clock_helper.log
```

## 2. Second (normal) PowerShell: warm the rebuilt exe once, then run the smoke
```powershell
cd %USERPROFILE%\governor
python experiments/w4_smoke/smoke.py warm --run data/w45_smoke/smoke2 --armoury-mode Performance
python experiments/w4_smoke/smoke.py overrun --run data/w45_smoke/smoke2 --armoury-mode Performance
```
Estimate (not measured): warm about 1 min, overrun about 7-9 min (7 runs of about 35-60 s each including model load). Each run prints one JSON line. Results: data/w45_smoke/smoke2/.

## 3. When it prints `saved .../overrun.json` (or an error): Ctrl+C the helper window, then paste back
```powershell
nvidia-smi -q -d CLOCK | Select-String "Applications|SM"
```
and the helper window's last lines (the helper log shows "reset not needed" vs "reset failed" separately now). Then tell me the path of the /export transcript if you made one.
