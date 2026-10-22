// The governed driver's view of the fg pace block [fg_busy, t_next_arrival_s, t_updated_s] (journal 0041).
// Smoke 2 showed that the driver treated a FAILED seqlock read (the Python writer mid-write: the 200-retry spin in shm::Block::read gives up after microseconds) as 'fg idle, next arrival = +inf',
// so a token started at every fg publish (1 ms before each frame, and at frame completion) whatever the guard. A failed read must keep the LAST GOOD value; only a block that was
// never written, or whose last good value is older than stale_s, means 'fg idle'. Caller: workloads/background/llama_governed_bench.cpp (slack-wait loop); test: tests/test_pace_view_cpp.py.
#pragma once
#include <cstring>
#include <limits>
#include "shm.h"

namespace shm {

struct PaceView {
    bool have = false;
    double last[3] = {0.0, 0.0, 0.0};

    // busy / next_ms: what the driver should assume now (now_s on the same QPC timeline as the fg's t_updated)
    void get(const Block &b, double now_s, double stale_s, bool &busy, double &next_ms) {
        double pc[3];
        if (b.read(pc)) { std::memcpy(last, pc, sizeof last); have = true; }
        busy = false;
        next_ms = std::numeric_limits<double>::infinity();
        if (have && now_s - last[2] <= stale_s) { busy = last[0] != 0.0; next_ms = last[1] * 1000.0; }
    }
};

}  // namespace shm
