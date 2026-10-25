# W5b unattended chain (docs/W5B_T3C_SITTING.md; plan addendum O-6 and its 2026-10-24 amendment).
# Steps, each one only if the previous one passed: (0) no-sleep settings, (1) T3c, (2) morning check (strict), (3) freeze the constants (mechanical), (4) the 6-cell evaluation trial, (5) its automatic checks, then STOP.
# It does NOT start evaluation block 1. Run from a normal PowerShell, with the admin clock helper already running in its own window and the laptop freshly restarted:
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\w5b_t3c_chain.ps1
$ErrorActionPreference = "Continue"
Set-Location C:\Users\arjun\governor
New-Item -ItemType Directory -Force data\w5b | Out-Null
Start-Transcript -Path data\w5b\chain_t3c_transcript.txt -Force | Out-Null
$start = Get-Date
$steps = [ordered]@{}

function Show-End($ok) {
    Write-Host ""
    Write-Host "================ W5b T3c CHAIN SUMMARY ================"
    foreach ($k in $steps.Keys) { Write-Host ("{0,-34} {1}" -f $k, $steps[$k]) }
    Write-Host ("elapsed: {0:N0} min" -f ((Get-Date) - $start).TotalMinutes)
    python experiments/w5b/chain_summary.py --t3c data/w5b/t3c/decisions.json --constants data/w5b/constants.json --sha data/w5b/constants.sha256 --trial data/w5b/eval_trial
    if ($ok) { Write-Host "RESULT: ALL STEPS PASSED. Evaluation block 1 was NOT started. Next: tell Claude; review; commit the constants; then the evaluation sessions." }
    else { Write-Host "RESULT: STOPPED ON A FAILURE (above). Nothing after the failed step was run. Paste this whole summary." }
    Write-Host "Sleep settings were changed; revert with:  powercfg /change standby-timeout-ac 30   and   powercfg /change hibernate-timeout-ac 0"
    Write-Host "Helper window: press Ctrl+C there once (note the prompt time and the message)."
    Stop-Transcript | Out-Null
}

function Stop-Chain($step, $why) {
    $steps[$step] = "FAIL: $why"
    Show-End $false
    exit 1
}

# 0. no-sleep settings
powercfg /change standby-timeout-ac 0
powercfg /change hibernate-timeout-ac 0
$steps["0 no-sleep settings"] = "set (standby and hibernate timeout 0 on AC)"

# 1. T3c: the c'B grid extension (24 cells) and the 6 d'B cells with the power headroom, plus one discarded cell (resumes after a plain stop only)
for ($i = 1; $i -le 3; $i++) {
    python experiments/w5b/tune.py --out data/w5b/t3c --plan t3c --c0 7 --merge-from data/w5b/t3b --power-source sampled --armoury-mode Performance --max-hours 2
    if ((Test-Path data/w5b/t3c/decisions.json) -or ($LASTEXITCODE -eq 1) -or ($LASTEXITCODE -eq 3)) { break }
    Start-Sleep -Seconds 60
}
if (-not (Test-Path data/w5b/t3c/decisions.json)) { Stop-Chain "1 T3c" "no decisions.json (last exit code $LASTEXITCODE): the sitting was refused, aborted or timed out" }
$steps["1 T3c"] = "ran (decisions.json written)"

# 2. morning check, strict: any problem fails the chain (flags only print)
python experiments/w5b/morning.py --out data/w5b/t3c --strict
if ($LASTEXITCODE -ne 0) { Stop-Chain "2 morning check (strict)" "problems in the T3c data (see above)" }
$steps["2 morning check (strict)"] = "PASS (0 problems)"

# 3. freeze the constants mechanically from the registered rules (re-freezing after review is allowed: no evaluation block has run)
python experiments/w5b/o7.py --dirs data/w5b/diag data/w5b/t3b data/w5b/t3c --out data/w5b/o7_tolerance.json
if ($LASTEXITCODE -ne 0) { Stop-Chain "3 O-7 tolerance" "o7.py failed" }
python experiments/w5b/freeze.py --tuning data/w5b/tuning/decisions.json --t3b data/w5b/t3b/decisions.json --t3c data/w5b/t3c/decisions.json --o7 data/w5b/o7_tolerance.json --out data/w5b/constants.json --write-sha data/w5b/constants.sha256
if ($LASTEXITCODE -ne 0) { Stop-Chain "3 freeze constants" "freeze.py refused (the T3c decisions are incomplete)" }
$sha = (Get-Content data/w5b/constants.sha256 -Raw).Trim()
$steps["3 freeze constants"] = "PASS (sha256 $sha)"

# 4. evaluation trial: 6 cells, one per path the evaluation adds (NOT a block, not data)
python experiments/w5b/evaluate.py --trial --blocks 4 --constants data/w5b/constants.json --constants-sha256 $sha --out data/w5b/eval_trial --armoury-mode Performance
if ($LASTEXITCODE -ne 0) { Stop-Chain "4 evaluation trial (6 cells)" "the trial run failed (exit code $LASTEXITCODE)" }
$steps["4 evaluation trial (6 cells)"] = "ran"

# 5. automatic checks of the trial
python experiments/w5b/evaluate.py --check-trial --out data/w5b/eval_trial
if ($LASTEXITCODE -ne 0) { Stop-Chain "5 trial checks" "an automatic check failed (see the problems above)" }
$steps["5 trial checks"] = "PASS"

$steps["6 STOP"] = "evaluation block 1 NOT started"
Show-End $true
exit 0
