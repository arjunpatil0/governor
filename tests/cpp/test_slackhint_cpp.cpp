// include/slackhint.h must also compile as C++ (extern "C" block) and round-trip in one process: producer create/publish -> consumer open/get; a stuck writer (odd seq) keeps the last good value.
#include <cmath>
#include <cstdio>
#include "slackhint.h"

static int fail(const char *what) { std::printf("FAIL %s\n", what); return 1; }

int main() {
    const char *name = "Local\\slackhint_cpp_inproc";
    slackhint_producer p;
    if (slackhint_producer_create(&p, name) != 0) return fail("create");
    slackhint_consumer c;
    if (slackhint_consumer_open(&c, name) != 0) return fail("open");
    int busy; double nd;
    slackhint_get(&c, 100.0, SLACKHINT_STALE_S, &busy, &nd);
    if (busy || !std::isinf(nd)) return fail("never written must be idle");
    slackhint_frame_started(&p, 10.0, 10.0167);
    slackhint_get(&c, 10.01, SLACKHINT_STALE_S, &busy, &nd);
    if (!busy || nd != 10.0167) return fail("busy record");
    slackhint_frame_done(&p, 10.007, 10.0334);
    slackhint_get(&c, 10.008, SLACKHINT_STALE_S, &busy, &nd);
    if (busy || nd != 10.0334) return fail("done record");
    *(volatile uint64_t *)p.m.p += 1;                                                  // a writer stuck mid-write
    slackhint_get(&c, 10.009, SLACKHINT_STALE_S, &busy, &nd);
    if (busy || nd != 10.0334) return fail("failed read must keep the last good value");
    slackhint_get(&c, 10.3, SLACKHINT_STALE_S, &busy, &nd);
    if (busy || !std::isinf(nd)) return fail("stale last good value must be idle");
    if (!slackhint_may_start(10.008, 0, 0.0101, 0.0, 10.0334) || slackhint_may_start(10.008, 0, 0.0101, 0.0, 10.017)) return fail("fit rule");
    if (slackhint_consumer_open(&c, "Local\\slackhint_cpp_does_not_exist") == 0) return fail("open of a missing block must fail");
    std::printf("OK\n");
    return 0;
}
