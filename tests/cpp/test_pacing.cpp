// Reads golden cases (CSV) produced by tests/test_pacing_cpp.py and checks workloads/background/pacing.h against the Python reference values.
// U,t_start,t_end,duty,expected_wake        A,now,fg_busy,tok_est,guard,next_arrival,expected_start
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <sstream>
#include <string>
#include <vector>
#include "pacing.h"

static std::vector<std::string> split(const std::string &s) {
    std::vector<std::string> v; std::stringstream ss(s); std::string x;
    while (std::getline(ss, x, ',')) v.push_back(x);
    return v;
}

int main(int argc, char **argv) {
    if (argc < 2) { fprintf(stderr, "usage: test_pacing cases.csv\n"); return 2; }
    std::ifstream f(argv[1]); std::string line; int n = 0, bad = 0;
    while (std::getline(f, line)) {
        if (line.empty()) continue;
        auto v = split(line); n++;
        if (v[0] == "U") {
            double got = pacing::unaligned_wake(atof(v[1].c_str()), atof(v[2].c_str()), atof(v[3].c_str())), want = strtod(v[4].c_str(), nullptr);
            bool ok = (std::isinf(want) && std::isinf(got)) || std::fabs(got - want) <= 1e-9 * (1.0 + std::fabs(want));
            if (!ok) { printf("FAIL %s got %.12g\n", line.c_str(), got); bad++; }
        } else {
            bool got = pacing::aligned_may_start(atof(v[1].c_str()), atoi(v[2].c_str()) != 0, atof(v[3].c_str()), atof(v[4].c_str()), strtod(v[5].c_str(), nullptr));
            if (got != (atoi(v[6].c_str()) != 0)) { printf("FAIL %s got %d\n", line.c_str(), (int)got); bad++; }
        }
    }
    printf("CHECKED %d BAD %d\n", n, bad);
    return bad ? 1 : 0;
}
