"""slackhint: frame-slack hints between a foreground app (producer) and a background worker (consumer). Python binding of include/slackhint.h; byte-compatible with it and with
telemetry/ring.py SeqBlock (nfields = 3). Windows only (named mappings via mmap tagname). Spec: docs/SPEC_FRAME_SLACK_HINTS.md.
Record = seqlock header (u64 seq, u64 nfields = 3) + [busy, next_deadline_s, updated_s] as f64, all times in seconds on time.perf_counter()'s timeline (QPC)."""
import math
import mmap
import struct
import time

NFIELDS = 3
HDR_BYTES = 16
SIZE_BYTES = HDR_BYTES + NFIELDS * 8
STALE_S = 0.1
READ_RETRIES = 200
EST_WINDOW = 8
INF = math.inf


def now_s():
    return time.perf_counter()


class Producer:
    """The foreground app side. One writer per block. create=True initialises the header (use for the first creator); create=False attaches to an existing block."""

    def __init__(self, name, create=True):
        self.name = name
        self.mm = mmap.mmap(-1, SIZE_BYTES, tagname=name)
        if create:
            struct.pack_into("<QQ", self.mm, 0, 0, NFIELDS)
        elif struct.unpack_from("<Q", self.mm, 8)[0] != NFIELDS:
            raise ValueError(f"slackhint block {name}: nfields mismatch")

    def publish(self, busy, next_deadline_s, now):
        seq = struct.unpack_from("<Q", self.mm, 0)[0]
        struct.pack_into("<Q", self.mm, 0, seq + 1 if seq % 2 == 0 else seq)        # odd: write in progress
        struct.pack_into("<3d", self.mm, HDR_BYTES, 1.0 if busy else 0.0, float(next_deadline_s), float(now))
        struct.pack_into("<Q", self.mm, 0, (seq | 1) + 1)                            # even: published

    def frame_started(self, now, next_deadline_s):
        self.publish(True, next_deadline_s, now)

    def frame_done(self, now, next_deadline_s):
        self.publish(False, next_deadline_s, now)

    def idle(self, now):
        self.publish(False, INF, now)


class Consumer:
    """The background worker side. Attaches to an existing block (raises ValueError if the geometry does not match: no silent fallback)."""

    def __init__(self, name):
        self.name = name
        self.mm = mmap.mmap(-1, SIZE_BYTES, tagname=name)
        if struct.unpack_from("<Q", self.mm, 8)[0] != NFIELDS:
            raise ValueError(f"slackhint block {name}: nfields mismatch (does the producer exist?)")
        self.have = False
        self.last = (0.0, 0.0, 0.0)

    def read(self, retries=READ_RETRIES):
        """Raw seqlock read -> (busy, next_deadline_s, updated_s), or None if never written / the writer kept it busy for all retries (a TRANSIENT failure, not 'idle')."""
        for _ in range(retries):
            s1 = struct.unpack_from("<Q", self.mm, 0)[0]
            if s1 == 0:
                return None
            if s1 % 2:
                continue
            v = struct.unpack_from("<3d", self.mm, HDR_BYTES)
            if struct.unpack_from("<Q", self.mm, 0)[0] == s1:
                return v
        return None

    def get(self, now, stale_s=STALE_S):
        """(busy, next_deadline_s). A failed read keeps the LAST GOOD value; only a never-written block or a last good value older than stale_s means 'app idle' (False, inf)."""
        v = self.read()
        if v is not None:
            self.last, self.have = v, True
        if self.have and now - self.last[2] <= stale_s:
            return self.last[0] != 0.0, self.last[1]
        return False, INF


def may_start(now, busy, estimate_s, guard_s, next_deadline_s):
    """Start a work unit only while the app is not busy and it is expected to end guard_s before the next deadline."""
    return (not busy) and (now + estimate_s + guard_s <= next_deadline_s + 1e-12)


def duty_wake(t_start_s, t_end_s, duty):
    """Earliest next start after a unit that ran [t_start_s, t_end_s]: duty <= 0 never (inf), duty >= 1 immediately, else t_end + duration * (1/duty - 1)."""
    if duty <= 0.0:
        return INF
    if duty >= 1.0:
        return t_end_s
    return t_end_s + (t_end_s - t_start_s) * (1.0 / duty - 1.0)


def unit_overlapped(t1_s, next_at_start_s, t0_s, have, updated_s):
    """A unit that started against a finite deadline overlapped a frame iff it ended after it; one that started with the app idle overlapped iff the app published during the unit."""
    if math.isfinite(next_at_start_s):
        return t1_s > next_at_start_s
    return bool(have) and updated_s >= t0_s


class Estimator:
    """Work-unit duration estimate: EWMA of all units (0.9/0.1) and the median of the last 8 units that did not overlap a frame; value() = the clean median once one exists, else the EWMA."""

    def __init__(self):
        self.have, self.e, self.c = False, 0.0, []

    def push(self, unit_s, overlapped):
        self.e = 0.9 * self.e + 0.1 * unit_s if self.have else unit_s
        self.have = True
        if not overlapped:
            self.c.append(unit_s)
            self.c = self.c[-EST_WINDOW:]

    def ewma(self):
        return self.e if self.have else 0.0

    def clean(self):
        if not self.c:
            return math.nan
        s = sorted(self.c)
        n = len(s)
        return s[n // 2] if n % 2 else 0.5 * (s[n // 2 - 1] + s[n // 2])

    def value(self):
        return self.clean() if self.c else self.ewma()
