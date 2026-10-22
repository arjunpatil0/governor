# Admin clock helper: security review and dispositions (2026-10-22)
Scope: actuators/clock_helper.py, actuators/clock_client.py, tests/test_clock_helper.py. Threat model: single-user Windows 11 laptop; the helper runs elevated; the unprivileged governor (same user) can lock/reset the SM clock only to allowlisted values. No cross-user or remote threat (pipe rejects remote clients, DACL = the user token SID).

## Tools run
- `/security-scan` (AgentShield via `npx ecc-agentshield scan --path actuators`): Grade A 100/100 but **Files scanned: 0**. AgentShield audits agent configuration (settings, hooks, MCP, agent prompts), not Python source, so this result says nothing about the helper. Not used as evidence.
- Code-level review by the ecc security-reviewer agent (read-only, two small probes of pywin32 behaviour): verdict "no privilege escalation from a same-user client; weaknesses are fail-safe correctness, the trust model for config/log files and availability". Findings and dispositions below. The reviewer's text is model output, not a human audit.

## Dispositions
| # | Finding | Disposition |
|---|---|---|
| HIGH-1 | A failed reset was forgotten (`locked=None` regardless), the watchdog never retried, RESET returned OK | FIXED. `dirty` state; retry every second in `tick()`; RESET returns ERR BACKEND on failure; PING/HB show `dirty`; startup aborts if the first reset fails. Tests: `test_a_failed_reset_is_remembered_retried_and_reported`, `test_watchdog_reset_failure_is_retried_not_forgotten`, `test_startup_reports_failure_when_the_first_reset_fails` |
| MED-1 | ACL check accepted a user-owned config (the client could widen its own allowlist); blacklist of three SIDs | FIXED. Owner must be SYSTEM/Administrators/TrustedInstaller; every allow-ACE with write/delete/ownership rights must belong to those (allowlist); the parent directory gets the same check. Tests with hostile ACEs on file and directory |
| MED-2 | TOCTOU between ACL check and read; reparse points | FIXED for the file: opened once (no write sharing, reparse point not followed), owner/DACL read from that handle, content read from it, reparse attribute refused. The symlink test is skipped here (no privilege to create symlinks). Residual: the parent directory is checked by path; safe only if the directory is admin-only, which is enforced at start |
| MED-3 | Elevated process appends to a log in a possibly user-controlled directory | PARTLY FIXED. `main()` refuses to run unless the log directory is trusted (same check). The log file is opened by path (RotatingFileHandler), not by handle: residual, bounded by the directory check. Setup note in the module docstring (icacls on C:\ProgramData\governor) |
| MED-4 | Log flooding | FIXED. RotatingFileHandler (1 MB x 3); rejected-lock / RESET / disconnect lines rate-limited to one per second with a suppressed count. Test: 1000 rejected LOCKs produce <= 3 records |
| MED-5 | An idle client holds the only pipe instance | FIXED. A monitor thread cancels I/O of a client silent for `idle_s` (10 s default); the serving thread then disconnects and accepts the next client. Test with idle_s 0.4 s. (Disconnecting from the monitor thread deadlocks on a synchronous handle; CancelIoEx via ctypes is used.) |
| MED-6 | Ctrl+C reset the lock but the process kept serving | FIXED in code: `shutdown()` sets `closed` (later commands get ERR SHUTDOWN, tested); the console handler also stops the server, flushes logs and exits the process. The handler itself is not unit-testable: **verify manually in the hardware smoke** (Ctrl+C must end the helper and leave the clock unlocked) |
| LOW-1 | DACL built from a `GetUserName()` lookup | FIXED. Uses the process token SID |
| LOW-2 | GENERIC_ALL on the pipe | FIXED. Mask 0x0012019B (read/write data, EA, attributes, READ_CONTROL, SYNCHRONIZE); the client requests exactly that mask (GENERIC_* would also ask for FILE_APPEND_DATA and be refused). Verified by the real-pipe tests |
| LOW-3 | `RESET\r\r\n` accepted | FIXED. One regex for all verbs |
| LOW-4 | HB could not tell the client its lock had lapsed | FIXED. HB/PING return `OK <mhz|none|dirty>` |
| LOW-5 | Failed LOCK did not count against the rate limit; RESET unlimited | LOCK FIXED (counted before the backend call). RESET and connect/disconnect stay unlimited (the log is rate-limited; NVML reset is idempotent). Accepted |
| LOW-6 | Client does not authenticate the server; no timeouts | NOT FIXED (accepted for the MVP). The first-instance flag makes the helper fail closed if a squatter owns the pipe name first; a fake server could only make the governor believe it locked a clock. Follow-up if ever used beyond this machine: check the pipe server process (GetNamedPipeServerProcessId) and add read timeouts |
| LOW-7 | Token handle leak | FIXED |

## Remaining risks (stated, not hidden)
- Hard kill / power loss of the helper leaves the lock until the next helper start or `nvidia-smi -rgc` (NVML has no server-side expiry). A scheduled task running `nvidia-smi -rgc` at logon is a cheap extra safety net; not created (needs your decision).
- Any process of the same user can lock/unlock the allowlisted clocks (accepted scope).
- NVML hung while the core lock is held blocks the watchdog.
- Test gaps still open: `main()` start-up ordering, the Ctrl+C path, squatting on the pipe name, REJECT_REMOTE (not testable locally), real NVML errors (need the GPU and admin; hardware smoke).
