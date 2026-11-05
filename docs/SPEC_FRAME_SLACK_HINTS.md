# Frame-slack hints: protocol specification (v1, draft, 2026-11-06)

A foreground app that renders at a fixed rate (here: a 60 Hz synthetic FMA loop with a 16.667 ms deadline) publishes two facts through a small shared-memory record: **is a frame running**, and **when is the next frame due**. A background worker (here: llama.cpp token decoding on the same GPU) reads the record and starts a work unit only when it is expected to finish before that deadline. This document specifies the record, the producer and consumer rules and the failure modes, and cites what our experiments did and did not show. It describes what was built and run (workloads/background/{shm,pace_view,pacing,tok_estimate}.h, telemetry/{ring,fg_publisher}.py, workloads/foreground/frame_loop.py); the reusable extraction is include/slackhint.h and python/slackhint. It claims no novelty (README, prior-art TODO).

Scope: Windows, one machine (ASUS laptop, RTX 4070 Laptop GPU, WDDM time-slicing), two processes, one producer per block. Not covered: other operating systems, multiple producers, GPUs with hardware partitioning, preemption-capable schedulers.

## 1. Roles and timeline
- **Producer** = the foreground app; **consumer** = the background worker. They share one named mapping (`Local\<name>`), no other channel.
- Per frame k with scheduled arrival `ts_k` and period `T` (1/60 s): the producer publishes *busy* shortly **before** the frame (`lead_ms` = 1.0 in workloads/foreground/frame_loop.py), runs the frame, publishes *not busy* with `next_deadline = ts_k + T` when it completes. When the app stops producing frames it publishes `idle` (next deadline = +inf).
- The consumer polls the record (tens of microseconds per poll), keeps a duration estimate of its work unit and decides, at each poll, whether to start one.

## 2. Record layout (wire format v1)
One named file mapping of 40 bytes, little endian. It is exactly telemetry/ring.py `SeqBlock` with `nfields = 3`.

| offset | size | field | meaning |
|---|---|---|---|
| 0 | u64 | `seq` | seqlock version: 0 before the first write, **odd while a write is in progress**, even when published |
| 8 | u64 | `nfields` | 3; a consumer or producer that finds another value refuses to attach (no silent fallback) |
| 16 | f64 | `busy` | 0.0 or 1.0: a frame is (about to be) running |
| 24 | f64 | `next_deadline_s` | QPC seconds of the next frame arrival/deadline; `+inf` = no frame expected |
| 32 | f64 | `updated_s` | QPC seconds when the producer published this record |

- **Time base:** QPC seconds (`QueryPerformanceCounter / Frequency`); Python's `time.perf_counter()` is on the same timeline on this Windows machine (the C++ reader and the Python writer of tests/test_pace_view_cpp.py share it: a mismatch would make every record look stale or fresh, and the test sees busy polls and no phantom idle).
- **Period:** not a field of v1. The consumer does not need it for the fit rule; it can be derived from successive `next_deadline_s` values. A period field would change `nfields` (v2, not built, not evaluated; section 8).
- **Seqlock write** (single writer): read `seq`; store `seq+1` if even (odd = in progress); full barrier; store the three doubles; full barrier; store `(seq|1)+1`. **Seqlock read:** read `seq` s1; 0 = never written; odd = retry; copy the doubles; barrier; accept iff `seq == s1`; give up after 200 retries (microseconds).
- Validated on x86-64 Windows only; the C header uses `MemoryBarrier()` on both sides; the Python writer relies on x86 store ordering (telemetry/ring.py).

## 3. Producer rules
1. Create the mapping before any consumer attaches (consumers refuse a missing mapping).
2. **Publish busy before the frame starts**, with the next deadline (`frame_started(now, ts_k + T)`). Lead the frame by about 1 ms so a consumer that polled just before cannot start a unit that overlaps the frame start.
3. **Publish not-busy with the next deadline when the frame completes** (`frame_done(now, ts_k + T)`), so the consumer sees the slack as early as possible.
4. When the app stops producing frames publish `idle(now)` (busy 0, deadline +inf); a producer that crashes or stalls is equivalent after 100 ms (rule C5).
5. One writer per block. Publish only consistent triples; do not update fields separately.

## 4. Consumer rules
- **C1 view.** Read with the seqlock; a **failed read keeps the last good record** (it is a transient failure, not information). Only a block never written, or whose last good record is older than the stale limit, means *app idle*: `busy = 0`, `next_deadline = +inf` (`slackhint_get`, a port of `shm::PaceView`).
- **C2 fit rule (slack filling).** Start a work unit only if the app is not busy **and** `now + estimate + guard <= next_deadline` (`slackhint_may_start`, a port of `pacing::aligned_may_start`; a 1e-12 s tolerance). The experiments used guard 0.5 ms as the starting value; the guard cannot create slack (section 6.3).
- **C3 estimate.** The fit rule needs the duration of an *undisturbed* unit. Keep the median of the last 8 units that did **not** overlap a frame (the clean estimate; the EWMA of all units, 0.9/0.1, is the fallback until one clean unit exists). A unit overlapped a frame iff it ended after the next deadline it was gated against, or (started with the app idle) the app published during it (`slackhint_est_*`, `slackhint_unit_overlapped`, ports of `tokest::`).
- **C4 duty throttle.** After a unit that ran `[t0, t1]`, the earliest next start is `t1 + (t1 - t0) * (1/duty - 1)`; duty 1 = no gap, duty <= 0 = never (`slackhint_duty_wake`, a port of `pacing::unaligned_wake`). In the experiments duty also throttled slack filling as a power-budget knob (aligned mode honours the duty gap).
- **C5 staleness.** A record older than **100 ms** (`updated_s`) means the app is idle and the worker runs free.
- **C6 no hints needed.** A consumer that never uses the fit rule (the experiments' *unaligned* mode: duty-cycle pacing only) ignores the block; its units may overlap frames.

## 5. Units and conventions
The library API is in **seconds**; the experiments' C++ driver works in milliseconds internally (`pacing.h`). The records of the experiments are the same records (the layout is in seconds throughout). Estimates and guards in the fit rule must use the same unit as the record.

## 6. Failure modes (what happens, what the protocol does, evidence, limits)

### 6.1 Torn reads / failed reads
- *What:* a reader can catch the writer mid-write (odd `seq`) or see `seq` change during the copy; the 200-retry spin gives up in microseconds. Every publish (two per frame) opens such a window.
- *Protocol:* seqlock (never accept a changed or odd `seq`) plus **C1: a failed read keeps the last good record**.
- *Evidence:* the experiment's driver treated a failed read as "never written / app idle" (busy 0, next deadline +inf), so the fit rule passed and tokens started at every publish whatever the guard (journal 0041; data/w45_smoke/smoke2_report.md: guard 0 / 0.5 / 1 / 2 ms gave the same 30 / 28 / 27 / 27% stretched-token share, all stretched tokens starting 1.0 ms before an arrival, i.e. at the busy publish). Reproduced without the GPU: with the real C++ reader against a Python writer emulating the frame loop the legacy policy saw 25368 phantom-idle polls in 5 s (all of them failed reads) and the fixed policy none (journal 0041; tests/test_pace_view_cpp.py asserts > 0 and == 0). Conformance: tests/test_slackhint_py.py and tests/test_slackhint_c.py run a stress test with a writer publishing as fast as it can and assert no inconsistent record is ever returned (C writer / Python reader and Python writer / C reader).
- *Limits:* the causal link is established by the mechanism reproduction and three consistent observations; it was not logged per token (journal 0041 says so). All smoke-1 numbers of the aligned path were declared invalid (journal 0042). No W1/W2 result used this code. Memory ordering was validated on x86 only.

### 6.2 Stale estimates (after clock changes, or after a stretched unit)
- *What:* the fit rule is only as good as the duration estimate. (a) A unit stretched by a frame (about 2x in our measurements) lifts an all-unit EWMA; (b) after the governor changes the SM clock the clean estimate describes the old clock until new clean units arrive.
- *Protocol:* **C3** keeps the clean median, so (a) is handled; for (b) the estimate refreshes within 8 clean units; there is no explicit invalidation on a clock change.
- *Evidence for (a):* token durations are bimodal while the foreground runs: clean 10.1 ms, stretched 20.7 ms (2.05x) (journal 0041, data/w45_smoke/smoke2_report.md); the clean-estimate design and its unit tests are in journal 0042 and tests/test_tok_estimate_cpp.py (C++ against a Python reference on 300 random tokens; stretched tokens leave the clean estimate alone and lift the EWMA).
- *Evidence for (b):* **none.** The pre-registered descriptive check (experiments/w5_governor.yaml HW7, analysis/w5_analysis.py `hw7_staleness`) needs `est_clean_ms` around every clock change; the data are logged in the driver CSVs but I found no analysis result in the repository (journal 0046: "not yet analysed"). Treat (b) as untested.
- *Limits:* the 8-unit window, the 0.9/0.1 EWMA and the median are design choices that were not tuned or ablated against alternatives.

### 6.3 Work units larger than the slack
- *What:* the slack after a frame is `T - frame time`; if a unit takes longer than the slack the fit rule never admits one. With a clean 3B token of 10.1 ms the slack holds a token only if the frame takes at most 16.67 - 10.1 = 6.57 ms (journal 0042); at light frames the rule is capped at one token per frame (60 tok/s at 60 Hz).
- *Protocol:* the guard **cannot** create slack. The consumer must either use another clock/work-unit size, or leave slack filling for **duty-cycle pacing (C4 without the fit rule) and accept overlap**.
- *Evidence:* smoke 3 (data/w45_smoke/smoke3_report.md, diagnostic, nominal frame cost 4 / 7 / 9 ms, measured foreground p50 3.0 / 5.2 / 6.7 ms): aligned slack filling gave 60.0 and 59.9 tok/s with 0% stretched tokens and foreground miss 0.000 at the first two, and 23 tokens (0.0 tok/s in the window) at 9 ms; the unaligned run at 9 ms had foreground miss 1.000 (p50 308.6 ms) at 37.0 tok/s (the report's own title says "smoke 2": the file holds the smoke 3 runs). Registered evaluation (docs/W5B_RESULTS.md observation 1, data/w5b/eval_descriptive.md): the static aligned setting 1800_a_g0_d1 made **0 tokens in the window in all 40 cells of S0 and S5** at 60 W, because no token fits the slack there, while it ran 19.97 tok/s (S1), 16.56 (S1d) and 31.98 (S2) with 10/10 feasible cells and foreground miss 0.0-0.04%. The learned controller d'B ended in unaligned (overlapping) pacing in all 75 of its cells and missed the 1% limit in S1 (median 1.72%) and S5 (4.72%) in every block.
- *Limits:* one frame cost family, one background (llama.cpp CUDA decode of 1B/3B/8B models), one GPU. The reading that overlap under WDDM time-slicing costs a few percent of deadline misses is a hypothesis; the data are compatible with it but do not isolate the mechanism (docs/W5B_RESULTS.md, post hoc section).

### 6.4 Other
- **Producer gone or stalled:** the record ages past 100 ms and the consumer runs free (C5). *Limit:* a consumer that runs free can hurt a producer that is merely slow to publish; 100 ms is a tuned-by-hand constant.
- **Consumer polls before the first write:** `seq == 0` is "never written" = idle until the first publish.
- **Geometry mismatch / missing block:** the consumer refuses to start (`slackhint_consumer_open` returns 1 or 3; the Python `Consumer` raises `ValueError`).
- **Named-mapping access:** any process of the same session can open `Local\<name>` and write it; no authentication. Out of scope for the experiments.

## 7. What was and was not measured (summary of limits)
- **Measured:** the failure mechanism of 6.1 (mechanism reproduction + hardware smoke); the granularity of 6.3 (smoke 3, evaluation S0-S5); the foreground miss of aligned slack filling in the registered evaluation (g'B/eB: 0.0-0.04% median miss where tokens run).
- **Not measured:** the benefit of the hints against a no-hint baseline in a controlled ablation (arm a in the evaluation is unaligned, ungoverned, at 87-92 W, a different comparison); the staleness of the estimate after clock changes (6.2 b); any other GPU, OS, frame rate or workload.
- **Registered result on the governed system, as computed** (docs/W5B_RESULTS.md): the learned controller d'B **does not earn its place** under the registered reading. This specification is about the hint channel, not about that result.
- Every number above traces to the file it cites; none is estimated.

## 8. Conformance and open items
- **Conformance suite** (pytest, Windows + MSVC, no GPU): tests/test_slackhint_py.py (13 tests: wire format both ways against telemetry/ring.py, never-written = idle, 100 ms stale, failed read keeps the last good value, fit-rule boundaries, duty wake, clean estimator, overlap rule, torn-read stress), tests/test_slackhint_c.py (9 tests: the C header compiled as C against the Python binding and SeqBlock in both directions, rules and estimator equal to Python, torn-read stress both ways, missing/mismatched block refused, header compiles as C++), plus the pre-existing tests/test_shm_cpp.py, tests/test_pace_view_cpp.py, tests/test_pacing_cpp.py, tests/test_tok_estimate_cpp.py for the experiments' own code.
- **Open:** (1) a `period` field and a version field (v2; would change `nfields`); (2) POSIX shared memory and non-x86 ordering (C11 atomics); (3) an explicit estimate invalidation after a clock change, if 6.2 (b) turns out to matter; (4) multi-producer; (5) prior-art search (README, TODO).
