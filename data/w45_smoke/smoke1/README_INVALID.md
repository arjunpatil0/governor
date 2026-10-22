# smoke 1: which numbers are invalid (written 2026-10-23, journal 0042)
The governed driver of smoke 1 treated a failed (mid-write) pace-block read as 'fg idle' (journal 0041), so its aligned-mode pacing ignored the fit test and the guard.
INVALID: driver.json aligned runs (aligned_g0_d1, aligned_g0_d0.5) and governor.json / governor_driver.csv (the c'B governor loop, fg miss 5.7%, tok/s, guard behaviour).
Not affected by this bug but a plumbing smoke only: frame.json, clock.json, daemon.*, and the unaligned driver run (its branch does not read the pace block).
The files are kept unchanged.
