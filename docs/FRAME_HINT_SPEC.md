# Frame hint: a spec for sharing frame timing between two processes

Version 1. Every detail below was taken from the code that ran the evaluation: `include/slackhint.h` (C), `python/slackhint/__init__.py` (Python) and `telemetry/ring.py` (the `SeqBlock` they are byte-compatible with). Where this text and the code could disagree, the code wins; the one place where two implementations differ is described in section 4. The evidence for each design choice, with measurements, is in the older draft [docs/SPEC_FRAME_SLACK_HINTS.md](SPEC_FRAME_SLACK_HINTS.md). Scope: Windows and a single machine, with one writer and any number of readers. The two C programs of section 9 were compiled and run against the Python binding in both directions before they were put here.

## 1. What it is for

An application that renders frames at a fixed rate tells a background worker two facts: whether a frame is running, and when the next frame is due. The worker starts a unit of work only if it will finish before that deadline. The channel carries nothing else. It has no queue and no acknowledgement, and the worker cannot talk back.

## 2. Time base

All times are seconds as a 64-bit float on one clock that both processes read. On Windows that clock is `QueryPerformanceCounter` divided by `QueryPerformanceFrequency` (Python: `time.perf_counter()`). A deadline is a point on that clock, not an interval. Two processes on different machines, or on different clocks, cannot use the protocol.

## 3. The record

A named file mapping of 40 bytes, little endian, created with the system page file as backing store. The name is any string both sides agree on and is passed to the operating system unchanged (the experiments used names that start with `Local\`, which keeps the mapping inside one login session).

| offset | size | field | meaning |
|---|---|---|---|
| 0 | u64 | `seq` | seqlock version: 0 before the first write, odd while a write is in progress, even when a record is published |
| 8 | u64 | `nfields` | 3 in version 1 |
| 16 | f64 | `busy` | 1.0 while a frame is running or about to run, 0.0 otherwise (no other value is written) |
| 24 | f64 | `next_deadline_s` | when the next frame is due, in seconds; `+inf` means no frame is expected |
| 32 | f64 | `updated_s` | the writer's clock when it published this record, in seconds |

## 4. Writing (one writer only)

Creation. The writer creates the mapping with the 40-byte size. If the mapping is new, or its `nfields` is 0, it sets `seq` to 0 and `nfields` to 3. If the mapping already exists with `nfields` equal to 3 it attaches without touching it (the C `slackhint_producer_create`). If `nfields` has any other value it refuses. The Python `Producer(create=True)` differs: it always writes `seq = 0` and `nfields = 3`, even into an existing mapping, and `create=False` attaches and refuses a wrong `nfields`. A second writer process must use the attach path, because zeroing a live record lets a reader see `seq` return to 0.

Publishing a record takes three steps. Read `seq` into `s`. Store `s + 1` if `s` is even and leave it unchanged if it is odd (an odd value on entry means an earlier writer died mid-write). Execute a full memory barrier. Store `busy`, `next_deadline_s` and `updated_s` in that order. Execute a full memory barrier. Store `(s | 1) + 1`, which is even. The C code uses `MemoryBarrier()`. The Python writer has no barrier calls and relies on x86 store ordering, so it is valid on x86-64 only.

What the application publishes:

| moment | call | `busy` | `next_deadline_s` |
|---|---|---|---|
| about 1 ms before a frame starts | frame started | 1 | due time of the frame that follows this one, `ts + period` |
| when the frame completes | frame done | 0 | the same value, `ts + period` |
| when the application stops producing frames | idle | 0 | `+inf` |

The 1 ms lead is the value the experiments used. It lets a worker that polled just before the publish see the frame coming. Fields are never updated one by one, only as a whole record.

## 5. Reading

A raw read tries up to 200 times (a few microseconds in total). Each try reads `seq` into `s1`. If `s1` is 0 the record was never written and the read fails. If `s1` is odd a write is in progress and the try repeats. Otherwise copy the three doubles, execute a memory barrier, read `seq` again, and accept the copy only if `seq` still equals `s1`. After 200 tries without success the read fails. A failed read is a transient condition, not a statement that the application is idle.

The view the worker should act on adds two rules. First, a failed read keeps the last good record. Second, the application counts as idle (`busy = 0`, `next_deadline_s = +inf`) in only two cases: no good record has ever been read, or the last good record's `updated_s` is more than 0.1 s older than the reader's current time. Treating a failed read as idle made the experiments' driver start a unit at every publish regardless of the deadline (the evidence is in the older draft, section 6.1), which is why the rule exists. A reader attaches to an existing mapping only: if the mapping does not exist it reports that, and if `nfields` is not 3 it refuses.

## 6. Versioning

`nfields` is the only version marker. The record size is 16 + 8 x `nfields`. A different `nfields` is a different protocol version, and every implementation refuses a record whose `nfields` it does not know (C return code 3, Python `ValueError`). There is no negotiation and no magic number in this record. A later version that adds a field, a frame period for example, must change `nfields`.

## 7. What a worker does with the record (policy, not part of the wire format)

These are the rules the experiments used. They are optional, and they matter for the results.

The fit rule: start a unit only if `busy` is 0 and `now + estimate + guard <= next_deadline_s + 1e-12`. The experiments began with a guard of 0.5 ms. A guard cannot create slack: if the unit is longer than the gap, nothing starts.

The estimate must be the duration of an undisturbed unit. Keep an exponentially weighted average of all units (weight 0.9 on the old value, 0.1 on the new) and the median of the last 8 units that did not overlap a frame. Use the median once one exists, the average before. A unit overlapped a frame if it started against a finite deadline and ended after it, or if it started while the application was idle and the application published during it.

The duty gap, an optional throttle: after a unit that ran from `t0` to `t1` the earliest next start is `t1 + (t1 - t0) x (1 / duty - 1)`. A duty of 1 means no gap and a duty of 0 or less means never.

## 8. Failure behaviour

| situation | what happens |
|---|---|
| the application publishes nothing for more than 0.1 s (stalled or crashed between publishes) | readers treat the application as idle and the worker runs free |
| the writer crashes while a write is in progress | `seq` stays odd, every read fails after its 200 tries, the reader keeps its last good record, and 0.1 s later it counts the application as idle |
| the writer restarts | an attaching writer continues from the current `seq`; a writer that zeroes the record resets `seq` to 0 and readers see "never written" until the first publish |
| a reader starts before the writer | the mapping does not exist and the reader reports it |
| `nfields` is not 3 | the reader or writer refuses |
| a read overlaps a write | the seqlock check detects it and the try repeats |
| two writers | not supported, and not detected |
| any other process in the session knows the name | it can read and write the record; there is no authentication |

## 9. A writer and a reader in C

The writer renders a 4 ms frame every 1/60 s and publishes busy 1 ms before each frame and not busy at its end. The reader polls every 50 ms and prints what a worker would see. Both were compiled with MSVC as C and tested against `python/slackhint` in both directions (a C writer read by the Python consumer and the C reader, a Python producer read by the C reader). Each is about 20 lines of logic.

```c
/* writer.c */
#include <windows.h>
#include <stdint.h>
#include <string.h>
#include <math.h>
static double now_s(void) { LARGE_INTEGER f, c; QueryPerformanceFrequency(&f); QueryPerformanceCounter(&c); return (double)c.QuadPart / (double)f.QuadPart; }
static void publish(volatile uint64_t *seq, int busy, double next_deadline_s, double updated_s) {
    uint64_t s = *seq;
    *seq = (s % 2 == 0) ? s + 1 : s;                       /* odd: write in progress */
    MemoryBarrier();
    double v[3] = { busy ? 1.0 : 0.0, next_deadline_s, updated_s };
    memcpy((unsigned char *)seq + 16, v, sizeof v);
    MemoryBarrier();
    *seq = (s | 1) + 1;                                    /* even: published */
}
int main(int argc, char **argv) {
    const char *name = argc > 1 ? argv[1] : "Local\\framehint_demo";
    HANDLE h = CreateFileMappingA(INVALID_HANDLE_VALUE, NULL, PAGE_READWRITE, 0, 40, name);
    int existed = GetLastError() == ERROR_ALREADY_EXISTS;
    volatile uint64_t *seq = (volatile uint64_t *)MapViewOfFile(h, FILE_MAP_ALL_ACCESS, 0, 0, 40);
    if (!existed || seq[1] == 0) { seq[0] = 0; seq[1] = 3; } else if (seq[1] != 3) return 3;
    double period = 1.0 / 60.0, due = now_s() + period;    /* a frame is due every 1/60 s */
    for (int k = 0; k < 60; k++, due += period) {
        while (now_s() < due - 0.001) Sleep(0);
        publish(seq, 1, due + period, now_s());            /* busy, 1 ms before the frame */
        while (now_s() < due + 0.004) ;                    /* a 4 ms frame */
        publish(seq, 0, due + period, now_s());            /* done: not busy, next frame at due + period */
    }
    publish(seq, 0, INFINITY, now_s());                    /* the application stops: idle */
    return 0;
}
```

```c
/* reader.c */
#include <windows.h>
#include <stdint.h>
#include <string.h>
#include <stdio.h>
#include <math.h>
static double now_s(void) { LARGE_INTEGER f, c; QueryPerformanceFrequency(&f); QueryPerformanceCounter(&c); return (double)c.QuadPart / (double)f.QuadPart; }
static int read_hint(const volatile uint64_t *seq, double out[3]) {   /* 1 = consistent record, 0 = never written or writer busy for 200 tries */
    for (int i = 0; i < 200; i++) {
        uint64_t s1 = *seq;
        if (s1 == 0) return 0;                             /* never written */
        if (s1 & 1) continue;                              /* write in progress */
        memcpy(out, (const unsigned char *)seq + 16, 24);
        MemoryBarrier();
        if (*seq == s1) return 1;                          /* unchanged while copying */
    }
    return 0;
}
int main(int argc, char **argv) {
    const char *name = argc > 1 ? argv[1] : "Local\\framehint_demo";
    HANDLE h = OpenFileMappingA(FILE_MAP_ALL_ACCESS, FALSE, name);
    if (!h) return 1;                                      /* no writer yet */
    const volatile uint64_t *seq = (const volatile uint64_t *)MapViewOfFile(h, FILE_MAP_ALL_ACCESS, 0, 0, 40);
    if (seq[1] != 3) return 3;                             /* wrong geometry: refuse */
    double last[3] = { 0, 0, 0 }; int have = 0;
    for (int i = 0; i < 20; i++, Sleep(50)) {
        double v[3], now = now_s();
        if (read_hint(seq, v)) { memcpy(last, v, sizeof v); have = 1; }          /* a failed read keeps the last good record */
        int busy = 0; double next = INFINITY;                                   /* default: the application is idle */
        if (have && now - last[2] <= 0.1) { busy = last[0] != 0.0; next = last[1]; }   /* older than 0.1 s means idle */
        printf("busy=%d next_deadline_in=%.4f s\n", busy, next - now);
    }
    return 0;
}
```

Build with `cl /nologo /TC writer.c` and `cl /nologo /TC reader.c`, run the writer, then the reader with the same name argument. The same code is available as a single header, `include/slackhint.h`, and as the Python binding `python/slackhint`; the importable package `python/governor` wraps the Python binding.
