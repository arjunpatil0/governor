# W5b block T3c + freeze + evaluation trial: ONE unattended chain (written 2026-10-24, revised the same day; rules: addendum O-6 and its section 7 = docs/W5B_ADDENDUM_O6.md; T1-T3, the diagnostic and T3b are DONE)
The chain runs, each step only if the previous one passed, and STOPS on any failure or at the end:
0. the no-sleep power settings (standby and hibernate timeout 0 on AC);
1. T3c: 1 discarded cell + the c'B comparator grid extension (targets 0.35 and 0.2 x ki 0.05 and 0.15 on the six workload / scene cells = 24 cells) + 6 d'B cells at margin 0.3 WITH the power headroom (2.69 W, steering target 57.31 W) to confirm the margin rule still holds (the headroom is kept either way) = 31 cells, about 52 min; power source sampled (addendum O-5);
2. the morning check in strict mode (any problem fails the chain);
3. freeze: experiments/w5b/freeze.py writes data/w5b/constants.json and its sha256 mechanically from the registered rules (c0 and g'B from the T1-T3 decisions, d'B's margin from T3b, c'B's constants and the headroom from T3c);
4. the evaluation trial (6 cells, one per path the evaluation adds: d'B on the held-out 8B, eB with an idle phase, c'B in S1d, a static g'B, arm a on the 8B, a 35 W d'B cell; not a block, not data), about 12 min;
5. the automatic checks of the trial (governed cells on the sampled source with 0 energy reads, counter vs sampled power within 15%, full GPU offload, the 8B present, no incident);
then it prints an end summary (steps, c'B constants and whether the rule was met, the headroom, the d'B confirmation, the constants hash, the trial cells) and stops. IT CANNOT START EVALUATION BLOCK 1. Re-freezing after review is allowed since no evaluation block will have run. Total about 1.1 h, inside the 2 h uptime limit if you start within minutes of the restart.

## Before you start
RESTART the laptop (the tools refuse an uptime above 2 h). Windows Update and NVIDIA driver updates paused; AC power; Armoury Crate Performance; Battery Health Charging Balanced 80%; Chrome closed; tray apps quit; nothing else running. Do NOT run pytest or rebuild anything. The tree is committed.

## 1. Administrator PowerShell: start the helper (leave it open)
```powershell
nvidia-smi -rgc; nvidia-smi -rmc
cd C:\Users\arjun\governor; python actuators/clock_helper.py --config C:\ProgramData\governor\clock_helper.json --log C:\ProgramData\governor\clock_helper.log
```

## 2. Normal PowerShell: the chain (one command)
```powershell
cd C:\Users\arjun\governor
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\w5b_t3c_chain.ps1
```
The whole output is also written to data\w5b\chain_t3c_transcript.txt. The last lines are the summary; "RESULT: ALL STEPS PASSED. Evaluation block 1 was NOT started." means success; "RESULT: STOPPED ON A FAILURE" names the failed step and nothing after it was run.

## 3. After the chain
Paste the whole end summary. Then press Ctrl+C in the helper window once (note the time to the prompt and the message) and, in the ADMIN window, paste:
```powershell
Get-Content C:\ProgramData\governor\clock_helper.log | Select-String "ERR|FAIL|refused|WARNING|startup|shutdown|not needed|rate" | Select-Object -Last 80
Get-Content C:\ProgramData\governor\clock_helper.log -Tail 30
```
The sleep settings were changed by the chain; the summary prints the revert commands (standby 30, hibernate 0; use your previous values if they were different). I cannot read the helper log from my side (Administrators only).

## 4. What I do next (not yours)
Review the summary, commit data/w5b/constants.json (the evaluation runner checks its sha256), and give you the literal evaluation session commands (docs/W5B_EVALUATION.md).
