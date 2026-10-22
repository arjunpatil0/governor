// Golden-case runner for workloads/background/tok_estimate.h (tests/test_tok_estimate_cpp.py).
//   T,tok_ms,overlapped            -> pushes the token, prints "E ewma clean value" (clean = nan until a clean token exists)
//   O,t1,next_at_start,t0,have,upd -> prints "O 0|1" (token_overlapped)
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <sstream>
#include <string>
#include <vector>
#include "tok_estimate.h"

static std::vector<std::string> split(const std::string &s) {
    std::vector<std::string> v; std::stringstream ss(s); std::string x;
    while (std::getline(ss, x, ',')) v.push_back(x);
    return v;
}

int main(int argc, char **argv) {
    if (argc < 2) return 2;
    std::ifstream f(argv[1]); std::string line;
    tokest::TokenEstimate est;
    while (std::getline(f, line)) {
        if (line.empty()) continue;
        auto v = split(line);
        if (v[0] == "T") {
            est.push(atof(v[1].c_str()), atoi(v[2].c_str()) != 0);
            printf("E %.12g %.12g %.12g\n", est.ewma(), est.clean(), est.value());
        } else {
            printf("O %d\n", tokest::token_overlapped(strtod(v[1].c_str(), nullptr), strtod(v[2].c_str(), nullptr), strtod(v[3].c_str(), nullptr), atoi(v[4].c_str()) != 0, strtod(v[5].c_str(), nullptr)) ? 1 : 0);
        }
    }
    return 0;
}
