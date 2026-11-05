/* C conformance program for include/slackhint.h (compiled as C by tests/test_slackhint_c.py).
 * usage: test_slackhint produce <name> <hold_ms> | stress_produce <name> <ms> | consume <name> | stress_consume <name> <ms> | estimator | rules */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "slackhint.h"

int main(int argc, char **argv) {
    if (argc < 2) return 2;
    const char *cmd = argv[1];
    if (strcmp(cmd, "rules") == 0) {
        printf("FIT %d %d %d %d %d\n",
               slackhint_may_start(0.0, 0, 0.010, 0.001, 0.011), slackhint_may_start(0.0, 0, 0.010, 0.001, 0.0109),
               slackhint_may_start(0.0, 1, 0.001, 0.0, INFINITY), slackhint_may_start(0.0, 0, 10.0, 1.0, INFINITY),
               slackhint_may_start(0.0, 0, 0.0101, 0.0, 0.0100));
        printf("DUTY %.12g %.12g %.12g %.12g %.12g\n", slackhint_duty_wake(1.0, 2.0, 0.0), slackhint_duty_wake(1.0, 2.0, 1.0), slackhint_duty_wake(1.0, 2.0, 0.5), slackhint_duty_wake(0.0, 0.01, 0.25),
               slackhint_duty_wake(1.0, 2.0, 1.5));
        printf("OVERLAP %d %d %d %d %d\n", slackhint_unit_overlapped(1.02, 1.01, 1.0, 1, 0.0), slackhint_unit_overlapped(1.005, 1.01, 1.0, 1, 0.0),
               slackhint_unit_overlapped(1.02, INFINITY, 1.0, 1, 1.01), slackhint_unit_overlapped(1.02, INFINITY, 1.0, 1, 0.5), slackhint_unit_overlapped(1.02, INFINITY, 1.0, 0, 0.0));
        return 0;
    }
    if (strcmp(cmd, "estimator") == 0) {
        slackhint_estimator e;
        slackhint_est_init(&e);
        for (int i = 0; i < 40; i++) {
            double u = 0.010 + ((i * 7) % 5) * 0.0001;
            int ov = (i % 4 == 0);
            if (ov) u *= 2.0;
            slackhint_est_push(&e, u, ov);
            double c = slackhint_est_clean(&e);
            if (c == c) printf("EST %d %.12g %.12g %.12g\n", i, slackhint_est_ewma(&e), c, slackhint_est_value(&e));
            else printf("EST %d %.12g none %.12g\n", i, slackhint_est_ewma(&e), slackhint_est_value(&e));
        }
        return 0;
    }
    if (argc < 4 && strcmp(cmd, "consume") != 0) return 2;
    if (argc < 3) return 2;
    if (strcmp(cmd, "produce") == 0 || strcmp(cmd, "stress_produce") == 0) {
        slackhint_producer p;
        if (slackhint_producer_create(&p, argv[2]) != 0) return 3;
        printf("READY\n"); fflush(stdout);
        if (strcmp(cmd, "produce") == 0) {
            slackhint_frame_started(&p, 3.25, 12.5);
            Sleep((DWORD)atoi(argv[3]));
        } else {
            double t_end = slackhint_now_s() + atof(argv[3]) / 1000.0;
            long long k = 0;
            while (slackhint_now_s() < t_end) { k++; slackhint_publish(&p, (int)(k % 2), k * 10.0, k * 10.0 - 5.0); }
            printf("WRITES %lld\n", k);
        }
        slackhint_producer_close(&p);
        return 0;
    }
    slackhint_consumer c;
    int rc = slackhint_consumer_open(&c, argv[2]);
    if (rc != 0) { printf("OPEN_FAILED %d\n", rc); return 3; }
    if (strcmp(cmd, "consume") == 0) {
        double v[3];
        if (!slackhint_read(&c, v)) { printf("NOREAD\n"); return 4; }
        int busy; double nd;
        slackhint_get(&c, v[2] + 0.01, SLACKHINT_STALE_S, &busy, &nd);
        printf("READ %.12g %.12g %.12g\nGET %d %.12g\n", v[0], v[1], v[2], busy, nd);
        slackhint_get(&c, v[2] + 1.0, SLACKHINT_STALE_S, &busy, &nd);                       /* stale: idle */
        printf("STALE %d %s\n", busy, isinf(nd) ? "inf" : "finite");
        return 0;
    }
    if (strcmp(cmd, "stress_consume") == 0) {
        double t_end = slackhint_now_s() + atof(argv[3]) / 1000.0, v[3];
        long long ok = 0, torn = 0, failed = 0;
        while (slackhint_now_s() < t_end) {
            if (!slackhint_read(&c, v)) { failed++; continue; }
            ok++;
            if (!(fabs(v[2] - (v[1] - 5.0)) < 1e-9 && v[0] == (double)(((long long)llround(v[1] / 10.0)) % 2))) torn++;
        }
        printf("OK %lld TORN %lld FAILED %lld\n", ok, torn, failed);
        return 0;
    }
    return 2;
}
