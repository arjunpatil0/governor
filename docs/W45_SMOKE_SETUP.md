# W4-5 hardware smoke: one-time Administrator setup (written 2026-10-22; run in an Administrator PowerShell)
Purpose: create an admin-only directory for the clock helper's config and log, write the config, and start the helper. The helper refuses to start if its config file, its directory or its log directory is owned or writable by a non-administrator (docs/W45_CLOCK_HELPER_SECURITY.md).

```powershell
# Create the directory that will hold the helper's config and log
New-Item -ItemType Directory -Force C:\ProgramData\governor | Out-Null

# Remove inherited permissions so ordinary users cannot write there
icacls C:\ProgramData\governor /inheritance:r

# Give full control to SYSTEM and Administrators only (inherited by files created inside)
icacls C:\ProgramData\governor /grant "SYSTEM:(OI)(CI)F" "Administrators:(OI)(CI)F"

# Write the helper config: allowed SM clocks, 3 s watchdog, at least 1 s between lock changes (created from this elevated shell, so Administrators own it)
Set-Content -Encoding ascii C:\ProgramData\governor\clock_helper.json '{"allowed_mhz":[900,1050,1200,1350,1500,1800],"watchdog_s":3.0,"min_interval_s":1.0}'

# Verify: the owner must be BUILTIN\Administrators and only SYSTEM/Administrators may appear with write access
(Get-Acl C:\ProgramData\governor\clock_helper.json).Owner; icacls C:\ProgramData\governor\clock_helper.json

# Release any clock lock left over from earlier work, so the smoke starts from a known state
nvidia-smi -rgc; nvidia-smi -rmc

# Start the helper from the repository (leave this window open; Ctrl+C must stop it and release the clock lock)
cd C:\Users\arjun\governor; python actuators/clock_helper.py --config C:\ProgramData\governor\clock_helper.json --log C:\ProgramData\governor\clock_helper.log
```

Expected: the helper prints `clock helper listening on \\.\pipe\governor_clock; allowed [900, 1050, 1200, 1350, 1500, 1800] MHz`. Refusals are explicit (`SystemExit` with the reason: not elevated, untrusted directory, untrusted config, failed first reset).
Checks to run in a SECOND PowerShell while it runs, and report the output:
1. `nvidia-smi -q -d CLOCK | Select-String "Applications|SM"` (clock state before/after the smoke steps)
2. After Ctrl+C in the helper window: `nvidia-smi -q -d CLOCK` again; the SM clock must not be locked.
Not done by this setup: a logon task that runs `nvidia-smi -rgc` (an optional safety net for a hard-killed helper).
