# W5a session 1 (written 2026-10-23; the list is frozen: plan addendum K)
Checklist: AC power; Armoury Crate mode Performance (say if different); Chrome closed; tray apps quit; Windows Update / driver updates paused; nothing else running; hands off during runs; do not run pytest or rebuild anything first.
The working tree must be clean and committed (the runner refuses otherwise; new files under data/ are allowed).

## 1. Administrator PowerShell: restart the helper (leave the window open)
```powershell
nvidia-smi -rgc; nvidia-smi -rmc
cd C:\Users\arjun\governor; python actuators/clock_helper.py --config C:\ProgramData\governor\clock_helper.json --log C:\ProgramData\governor\clock_helper.log
```

## 2. Normal PowerShell, in this order (paste back the output of steps a and b BEFORE c)
```powershell
cd C:\Users\arjun\governor
# a) context-shift check: the background alone for 40 s must run well past the old 1534-token limit (about 1 min)
python experiments/w4_smoke/smoke.py shift --run data/w5a/shift_check --armoury-mode Performance
# b) ONE trial cell of session 1 (about 1.5 min): proves the runner end to end
python experiments/w5a/run.py --list data/w5a/cell_list.json --list-sha256 8f913519a9988a316ad1c8275b303d60ed25c49ce0831cc240f4f8b8f7458d77 --session 1 --armoury-mode Performance --limit 1
# c) the rest of session 1 (94 cells, estimate about 2.2 h; resumes after the trial cell; stop it between cells with Ctrl+C if it runs past 2 h and run the same command again later)
python experiments/w5a/run.py --list data/w5a/cell_list.json --list-sha256 8f913519a9988a316ad1c8275b303d60ed25c49ce0831cc240f4f8b8f7458d77 --session 1 --armoury-mode Performance
```

## 3. After the run: Ctrl+C the helper window, then in the ADMIN window paste back
```powershell
nvidia-smi -q -d CLOCK | Select-String "Applications|SM"
Get-Content C:\ProgramData\governor\clock_helper.log -Tail 30
```
Then tell me the /export path if you made one. Session outputs: data/w5a/session1/ (cell.json per cell, manifest.json with SHA-256 of every file).
