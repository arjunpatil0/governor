// C++ side of the named shared-memory structures created by telemetry/ring.py (Python layout is the reference; tests/test_shm_cpp.py checks the interop).
//   Ring  : header 32 B {u64 write_count, u64 capacity, u64 nfields, u64 magic} then capacity x nfields doubles. The writer stores the record, then publishes write_count + 1.
//   Block : header 16 B {u64 seq, u64 nfields} then nfields doubles; seqlock (seq odd while a write is in progress, 0 before the first write).
// Mappings are created by the Python governor; the driver only OPENS them and aborts on a geometry mismatch (no silent fallback).
#pragma once
#include <windows.h>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <vector>

namespace shm {

constexpr uint64_t MAGIC = 0x47524E5247494E47ULL;

struct Mapping {
    HANDLE h = nullptr;
    unsigned char *p = nullptr;
    bool open(const char *name, size_t size) {
        h = OpenFileMappingA(FILE_MAP_ALL_ACCESS, FALSE, name);
        if (!h) return false;
        p = (unsigned char *)MapViewOfFile(h, FILE_MAP_ALL_ACCESS, 0, 0, size);
        return p != nullptr;
    }
};

class Ring {
public:
    bool open(const char *name, uint64_t capacity, uint64_t nfields) {
        cap_ = capacity; nf_ = nfields;
        if (!m_.open(name, 32 + capacity * nfields * 8)) { fprintf(stderr, "shm: cannot open ring %s\n", name); return false; }
        uint64_t *hd = (uint64_t *)m_.p;
        if (hd[1] != capacity || hd[2] != nfields || hd[3] != MAGIC) { fprintf(stderr, "shm: ring %s geometry mismatch\n", name); return false; }
        return true;
    }
    void push(const double *rec) {
        uint64_t *hd = (uint64_t *)m_.p;
        uint64_t wc = *(volatile uint64_t *)&hd[0];
        memcpy(m_.p + 32 + (wc % cap_) * nf_ * 8, rec, nf_ * 8);
        InterlockedExchange64((volatile LONG64 *)&hd[0], (LONG64)(wc + 1));      // full barrier: the record is visible before the count
    }
private:
    Mapping m_; uint64_t cap_ = 0, nf_ = 0;
};

class Block {
public:
    bool open(const char *name, uint64_t nfields) {
        nf_ = nfields;
        if (!m_.open(name, 16 + nfields * 8)) { fprintf(stderr, "shm: cannot open block %s\n", name); return false; }
        if (((uint64_t *)m_.p)[1] != nfields) { fprintf(stderr, "shm: block %s geometry mismatch\n", name); return false; }
        return true;
    }
    // false = never written (or a writer kept it busy for all retries); out receives nfields doubles otherwise
    bool read(double *out, int retries = 200) const {
        volatile uint64_t *seq = (volatile uint64_t *)m_.p;
        for (int i = 0; i < retries; i++) {
            uint64_t s1 = *seq;
            if (s1 == 0) return false;
            if (s1 & 1) continue;
            memcpy(out, m_.p + 16, nf_ * 8);
            MemoryBarrier();
            if (*seq == s1) return true;
        }
        return false;
    }
private:
    Mapping m_; uint64_t nf_ = 0;
};

}  // namespace shm
