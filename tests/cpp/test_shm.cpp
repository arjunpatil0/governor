// Interop probe for workloads/background/shm.h: prints the control and pace blocks created by Python and pushes five token records into the Python ring.
// usage: test_shm <ctrl_name> <pace_name> <ring_name> <ring_capacity>
#include <cstdio>
#include <cstdlib>
#include "shm.h"

#ifndef PROBE_ID
#define PROBE_ID 0
#endif
static const int kProbeId = PROBE_ID;                 // /DPROBE_ID=n changes the bytes (new hash) for the first-run investigation (analysis/exe_first_run_probe.py)

int main(int argc, char **argv) {
    if (argc < 5 || kProbeId < 0) return 2;
    if (const char *lg = getenv("PROBE_LOG")) {       // optional: one line per process start (pid)
        FILE *o = fopen(lg, "a");
        if (o) { fprintf(o, "%lu\n", (unsigned long)GetCurrentProcessId()); fclose(o); }
    }
    shm::Block ctrl, pace; shm::Ring ring;
    if (!ctrl.open(argv[1], 3) || !pace.open(argv[2], 3)) return 3;
    if (!ring.open(argv[3], (uint64_t)atoi(argv[4]), 1)) return 4;
    double v[3];
    if (ctrl.read(v)) printf("CTRL %g %g %g\n", v[0], v[1], v[2]); else printf("CTRL none\n");
    if (pace.read(v)) printf("PACE %g %g %g\n", v[0], v[1], v[2]); else printf("PACE none\n");
    for (int i = 1; i <= 5; i++) { double t = (double)i; ring.push(&t); }
    return 0;
}
