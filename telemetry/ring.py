"""Named shared-memory structures shared by the Python governor/daemon and the C++ governed llama.cpp driver (workloads/background/shm.h mirrors the layout).

SharedRing: single-writer ring of fixed-size records of doubles.
  header (32 B, little endian): u64 write_count | u64 capacity | u64 nfields | u64 magic        records: capacity x nfields x f64
  The writer stores the record, then publishes write_count + 1 (x86 stores are ordered). A reader that falls more than `capacity` behind loses the oldest records
  and reports how many.
SeqBlock: seqlock for a small vector of doubles (control values governor -> driver, pace values fg -> driver).
  header (16 B): u64 seq | u64 nfields        values: nfields x f64.   seq is odd while a write is in progress, 0 before the first write.
All timestamps stored in these structures are QPC seconds (time.perf_counter()), the same timeline as the W2 experiments."""
import mmap
import struct

import numpy as np

MAGIC = 0x47524E5247494E47          # marker checked by readers
_RING_HDR = 32
_SEQ_HDR = 16


class SharedRing:
    def __init__(self, name, capacity, nfields, create):
        self.name, self.capacity, self.nfields = name, int(capacity), int(nfields)
        self.size = _RING_HDR + self.capacity * self.nfields * 8
        self.mm = mmap.mmap(-1, self.size, tagname=name)
        if create:
            struct.pack_into("<QQQQ", self.mm, 0, 0, self.capacity, self.nfields, MAGIC)
        else:
            wc, cap, nf, magic = struct.unpack_from("<QQQQ", self.mm, 0)
            if magic != MAGIC or cap != self.capacity or nf != self.nfields:
                raise ValueError(f"ring {name}: geometry mismatch (header capacity {cap}, nfields {nf}, magic {magic:#x})")
        self.read_pos = 0

    def push(self, rec):
        if len(rec) != self.nfields:
            raise ValueError("record size")
        wc = struct.unpack_from("<Q", self.mm, 0)[0]
        struct.pack_into(f"<{self.nfields}d", self.mm, _RING_HDR + (wc % self.capacity) * self.nfields * 8, *[float(x) for x in rec])
        struct.pack_into("<Q", self.mm, 0, wc + 1)

    def read_new(self):
        """Records published since the last call -> (array (k, nfields), dropped). dropped counts records overwritten before they were read."""
        wc = struct.unpack_from("<Q", self.mm, 0)[0]
        dropped = max(0, wc - self.read_pos - self.capacity)
        start = self.read_pos + dropped
        out = np.empty((wc - start, self.nfields))
        for i, k in enumerate(range(start, wc)):
            out[i] = struct.unpack_from(f"<{self.nfields}d", self.mm, _RING_HDR + (k % self.capacity) * self.nfields * 8)
        self.read_pos = wc
        return out, int(dropped)

    @property
    def write_count(self):
        return struct.unpack_from("<Q", self.mm, 0)[0]


class SeqBlock:
    def __init__(self, name, nfields, create):
        self.name, self.nfields = name, int(nfields)
        self.mm = mmap.mmap(-1, _SEQ_HDR + 8 * self.nfields, tagname=name)
        if create:
            struct.pack_into("<QQ", self.mm, 0, 0, self.nfields)
        elif struct.unpack_from("<Q", self.mm, 8)[0] != self.nfields:
            raise ValueError(f"block {name}: nfields mismatch")

    def write(self, values):
        if len(values) != self.nfields:
            raise ValueError("block size")
        seq = struct.unpack_from("<Q", self.mm, 0)[0]
        struct.pack_into("<Q", self.mm, 0, seq + 1 if seq % 2 == 0 else seq)          # odd: write in progress
        struct.pack_into(f"<{self.nfields}d", self.mm, _SEQ_HDR, *[float(x) for x in values])
        struct.pack_into("<Q", self.mm, 0, (seq | 1) + 1)                               # even: published

    def read(self, retries=200):
        for _ in range(retries):
            s1 = struct.unpack_from("<Q", self.mm, 0)[0]
            if s1 == 0:
                return None
            if s1 % 2:
                continue
            v = struct.unpack_from(f"<{self.nfields}d", self.mm, _SEQ_HDR)
            if struct.unpack_from("<Q", self.mm, 0)[0] == s1:
                return v
        return None
