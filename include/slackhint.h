/* slackhint.h - frame-slack hints: a foreground app tells a background worker when it is busy and when its next frame is due.
 * Single header, plain C99 (also compiles as C++). Windows only (named file mappings), like the code it is extracted from:
 *   workloads/background/shm.h (Block = seqlock), pace_view.h (last-good-value view), pacing.h (fit rule, duty gap), tok_estimate.h (clean-token estimate).
 * Wire format = telemetry/ring.py SeqBlock with nfields = 3 (docs/SPEC_FRAME_SLACK_HINTS.md section 2); the Python binding python/slackhint is byte-compatible.
 * All times are SECONDS on the QPC timeline (slackhint_now_s() == Python time.perf_counter()).
 * Producer = the foreground app (one writer per block). Consumer = the background worker (any number of readers). */
#ifndef SLACKHINT_H
#define SLACKHINT_H

#include <windows.h>
#include <math.h>
#include <stdint.h>
#include <string.h>

#ifdef __cplusplus
extern "C" {
#endif

#define SLACKHINT_NFIELDS 3
#define SLACKHINT_HDR_BYTES 16
#define SLACKHINT_SIZE_BYTES (SLACKHINT_HDR_BYTES + SLACKHINT_NFIELDS * 8)
#define SLACKHINT_STALE_S 0.1          /* a record older than this means "the app is idle" */
#define SLACKHINT_READ_RETRIES 200     /* spin retries of one raw read (microseconds); a failed read is NOT "idle" (see slackhint_get) */
#define SLACKHINT_EST_WINDOW 8

/* ---- time ---- */
static inline double slackhint_now_s(void) {
    LARGE_INTEGER f, c;
    QueryPerformanceFrequency(&f);
    QueryPerformanceCounter(&c);
    return (double)c.QuadPart / (double)f.QuadPart;
}

/* ---- mapping ---- */
typedef struct { HANDLE h; unsigned char *p; } slackhint_map;

static inline int slackhint_map_close(slackhint_map *m) {
    if (m->p) UnmapViewOfFile(m->p);
    if (m->h) CloseHandle(m->h);
    m->p = NULL; m->h = NULL;
    return 0;
}

/* ---- producer ---- */
typedef struct { slackhint_map m; } slackhint_producer;

/* Creates the named mapping (or attaches to one that exists with nfields == 3; an existing one is NOT zeroed). 0 = ok. */
static inline int slackhint_producer_create(slackhint_producer *pr, const char *name) {
    pr->m.h = CreateFileMappingA(INVALID_HANDLE_VALUE, NULL, PAGE_READWRITE, 0, SLACKHINT_SIZE_BYTES, name);
    if (!pr->m.h) return 1;
    int existed = (GetLastError() == ERROR_ALREADY_EXISTS);
    pr->m.p = (unsigned char *)MapViewOfFile(pr->m.h, FILE_MAP_ALL_ACCESS, 0, 0, SLACKHINT_SIZE_BYTES);
    if (!pr->m.p) { slackhint_map_close(&pr->m); return 2; }
    uint64_t *hd = (uint64_t *)pr->m.p;
    if (!existed || hd[1] == 0) { hd[0] = 0; hd[1] = SLACKHINT_NFIELDS; }
    else if (hd[1] != SLACKHINT_NFIELDS) { slackhint_map_close(&pr->m); return 3; }
    return 0;
}

/* One seqlock write of [busy, next_deadline_s, updated_s]. Single writer only. Same protocol as telemetry/ring.py SeqBlock.write: seq odd while writing, even when published. */
static inline void slackhint_publish(slackhint_producer *pr, int busy, double next_deadline_s, double now_s) {
    volatile uint64_t *seq = (volatile uint64_t *)pr->m.p;
    uint64_t s = *seq;
    *seq = (s % 2 == 0) ? s + 1 : s;
    MemoryBarrier();
    double v[SLACKHINT_NFIELDS];
    v[0] = busy ? 1.0 : 0.0; v[1] = next_deadline_s; v[2] = now_s;
    memcpy(pr->m.p + SLACKHINT_HDR_BYTES, v, sizeof v);
    MemoryBarrier();
    *seq = (s | 1) + 1;
}

/* Producer rules (spec section 4): publish busy BEFORE the frame starts (lead it by ~1 ms like the experiments, or at the frame start), publish not-busy plus the NEXT deadline when it completes. */
static inline void slackhint_frame_started(slackhint_producer *pr, double now_s, double next_deadline_s) { slackhint_publish(pr, 1, next_deadline_s, now_s); }
static inline void slackhint_frame_done(slackhint_producer *pr, double now_s, double next_deadline_s) { slackhint_publish(pr, 0, next_deadline_s, now_s); }
static inline void slackhint_idle(slackhint_producer *pr, double now_s) { slackhint_publish(pr, 0, INFINITY, now_s); }

/* ---- consumer ---- */
typedef struct {
    slackhint_map m;
    int have;                         /* a good value has been read at least once */
    double last[SLACKHINT_NFIELDS];   /* the last good [busy, next_deadline_s, updated_s] */
} slackhint_consumer;

/* Attaches to an existing mapping; 0 = ok, 1 = does not exist, 2 = map failed, 3 = geometry mismatch (no silent fallback). */
static inline int slackhint_consumer_open(slackhint_consumer *c, const char *name) {
    memset(c, 0, sizeof *c);
    c->m.h = OpenFileMappingA(FILE_MAP_ALL_ACCESS, FALSE, name);
    if (!c->m.h) return 1;
    c->m.p = (unsigned char *)MapViewOfFile(c->m.h, FILE_MAP_ALL_ACCESS, 0, 0, SLACKHINT_SIZE_BYTES);
    if (!c->m.p) { slackhint_map_close(&c->m); return 2; }
    if (((uint64_t *)c->m.p)[1] != SLACKHINT_NFIELDS) { slackhint_map_close(&c->m); return 3; }
    return 0;
}

/* Raw seqlock read: 1 = out holds a consistent record, 0 = never written or the writer kept it busy for all retries (a TRANSIENT failure, not "idle"). */
static inline int slackhint_read(const slackhint_consumer *c, double *out) {
    volatile uint64_t *seq = (volatile uint64_t *)c->m.p;
    for (int i = 0; i < SLACKHINT_READ_RETRIES; i++) {
        uint64_t s1 = *seq;
        if (s1 == 0) return 0;
        if (s1 & 1) continue;
        memcpy(out, c->m.p + SLACKHINT_HDR_BYTES, SLACKHINT_NFIELDS * 8);
        MemoryBarrier();
        if (*seq == s1) return 1;
    }
    return 0;
}

/* The consumer's view (port of shm::PaceView::get). A FAILED read keeps the LAST GOOD value; only a block never written, or a last good value older than stale_s, means "app idle"
 * (busy = 0, next deadline = +inf). Treating a failed read as idle made the experiment's driver start work at every publish (journal 0041). */
static inline void slackhint_get(slackhint_consumer *c, double now_s, double stale_s, int *busy, double *next_deadline_s) {
    double pc[SLACKHINT_NFIELDS];
    if (slackhint_read(c, pc)) { memcpy(c->last, pc, sizeof pc); c->have = 1; }
    *busy = 0;
    *next_deadline_s = INFINITY;
    if (c->have && now_s - c->last[2] <= stale_s) { *busy = c->last[0] != 0.0; *next_deadline_s = c->last[1]; }
}

/* Consumer rule (port of pacing::aligned_may_start, seconds): start a work unit only while the app is not busy and it is expected to end `guard_s` before the next deadline. */
static inline int slackhint_may_start(double now_s, int busy, double estimate_s, double guard_s, double next_deadline_s) {
    return (!busy) && (now_s + estimate_s + guard_s <= next_deadline_s + 1e-12);
}

/* Duty throttle (port of pacing::unaligned_wake): earliest next start after a unit that ran [t_start_s, t_end_s]; duty <= 0 never, duty >= 1 immediately. */
static inline double slackhint_duty_wake(double t_start_s, double t_end_s, double duty) {
    if (duty <= 0.0) return INFINITY;
    if (duty >= 1.0) return t_end_s;
    return t_end_s + (t_end_s - t_start_s) * (1.0 / duty - 1.0);
}

/* ---- work-unit duration estimate (port of tokest::TokenEstimate) ----
 * Keeps an EWMA of all units (0.9/0.1) AND the median of the last 8 units that did NOT overlap an app frame; value() = the clean median once one exists, else the EWMA.
 * The fit rule needs the duration of an UNDISTURBED unit: one unit stretched by a frame (about 2x in the experiments) must not inflate the estimate (journal 0042). */
typedef struct {
    int have, n_clean, pos;
    double ewma;
    double clean[SLACKHINT_EST_WINDOW];   /* ring of the last clean durations, in seconds */
} slackhint_estimator;

static inline void slackhint_est_init(slackhint_estimator *e) { memset(e, 0, sizeof *e); }

static inline void slackhint_est_push(slackhint_estimator *e, double unit_s, int overlapped) {
    e->ewma = e->have ? 0.9 * e->ewma + 0.1 * unit_s : unit_s;
    e->have = 1;
    if (!overlapped) {
        e->clean[e->pos] = unit_s;
        e->pos = (e->pos + 1) % SLACKHINT_EST_WINDOW;
        if (e->n_clean < SLACKHINT_EST_WINDOW) e->n_clean++;
    }
}

static inline double slackhint_est_ewma(const slackhint_estimator *e) { return e->have ? e->ewma : 0.0; }

static inline double slackhint_est_clean(const slackhint_estimator *e) {   /* NaN until a clean unit exists */
    if (e->n_clean == 0) return NAN;
    double s[SLACKHINT_EST_WINDOW];
    int n = e->n_clean;
    memcpy(s, e->clean, n * sizeof(double));
    for (int i = 1; i < n; i++) { double x = s[i]; int j = i - 1; while (j >= 0 && s[j] > x) { s[j + 1] = s[j]; j--; } s[j + 1] = x; }
    return (n % 2) ? s[n / 2] : 0.5 * (s[n / 2 - 1] + s[n / 2]);
}

static inline double slackhint_est_value(const slackhint_estimator *e) { return e->n_clean ? slackhint_est_clean(e) : slackhint_est_ewma(e); }

/* A unit that started against a finite next deadline overlapped a frame iff it ended after that deadline; one that started with no finite deadline (app idle) overlapped iff the app
 * published during the unit (updated_s >= t0_s). */
static inline int slackhint_unit_overlapped(double t1_s, double next_at_start_s, double t0_s, int have, double updated_s) {
    if (isfinite(next_at_start_s)) return t1_s > next_at_start_s;
    return have && updated_s >= t0_s;
}

static inline int slackhint_consumer_close(slackhint_consumer *c) { return slackhint_map_close(&c->m); }
static inline int slackhint_producer_close(slackhint_producer *p) { return slackhint_map_close(&p->m); }

#ifdef __cplusplus
}
#endif
#endif /* SLACKHINT_H */
