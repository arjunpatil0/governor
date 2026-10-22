// Probe for the governed driver's view of the pace block (smoke 2 diagnosis, journal 0041): spins like the driver's slack-wait loop and counts how often the driver would believe
// "the fg is idle (not busy, next arrival = +inf)" while the Python writer only ever publishes busy/not-busy with a finite next arrival.
// usage: probe_pace_view <pace_name> <seconds> <legacy|view>
//   legacy = the driver as it was in smoke 2 (a failed read is treated as 'fg idle'); view = shm::PaceView (a failed read keeps the last good value).
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <limits>
#include "pace_view.h"

static double qpc_s() {
    LARGE_INTEGER f, c; QueryPerformanceFrequency(&f); QueryPerformanceCounter(&c);
    return (double)c.QuadPart / (double)f.QuadPart;
}

int main(int argc, char **argv) {
    if (argc < 4) return 2;
    shm::Block pace;
    if (!pace.open(argv[1], 3)) return 3;
    double secs = atof(argv[2]);
    bool legacy = strcmp(argv[3], "legacy") == 0;
    const double inf = std::numeric_limits<double>::infinity();
    shm::PaceView view;
    double t_end = qpc_s() + secs;
    long long polls = 0, phantom_idle = 0, failed_reads = 0, busy_polls = 0;
    bool seen = false;
    while (qpc_s() < t_end) {
        double now_s = qpc_s(), pc[3];
        bool busy = false; double next_ms = inf;
        if (legacy) {
            bool ok = pace.read(pc);
            if (!ok && seen) failed_reads++;
            if (ok) { seen = true; }
            if (ok && now_s - pc[2] <= 0.1) { busy = pc[0] != 0.0; next_ms = pc[1] * 1000.0; }
        } else {
            view.get(pace, now_s, 0.1, busy, next_ms);
            seen = view.have;
        }
        polls++;
        if (busy) busy_polls++;
        if (seen && !busy && next_ms == inf) phantom_idle++;
    }
    printf("POLLS %lld PHANTOM_IDLE %lld FAILED_READS %lld BUSY_POLLS %lld\n", polls, phantom_idle, failed_reads, busy_polls);
    return 0;
}
