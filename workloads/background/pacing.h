// Pacing decisions of the governed llama.cpp driver. C++ mirror of sim/pacing.py (the reference); tests/test_pacing_cpp.py compares both on golden cases.
// All times in ms on one monotone timeline (QPC).
#pragma once
#include <cmath>
#include <limits>

namespace pacing {

// Duty cycle: after a token, sleep measured_token_time * (1/duty - 1). duty <= 0: never wake; duty >= 1: no gap.
inline double unaligned_wake(double t_start, double t_end, double duty) {
    if (duty <= 0.0) return std::numeric_limits<double>::infinity();
    if (duty >= 1.0) return t_end;
    return t_end + (t_end - t_start) * (1.0 / duty - 1.0);
}

// Slack filling: start a token only while no fg frame is queued/running and it is expected to end `guard` ms before the next fg arrival
// (next_arrival = +inf when no frame is expected soon, i.e. the fg is idle).
inline bool aligned_may_start(double now, bool fg_busy, double tok_est, double guard, double next_arrival) {
    return (!fg_busy) && (now + tok_est + guard <= next_arrival + 1e-9);
}

}  // namespace pacing
