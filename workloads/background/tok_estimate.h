// Token-duration estimate of the governed driver (journal 0042; reviewer decision 2026-10-22 after smoke 2).
// The fit test (pacing::aligned_may_start) needs the duration of an UNDISTURBED token. The smoke-2 driver used an EWMA of all tokens, so one token stretched by a frame
// (about 2x) lifted it and blocked tokens that would fit. TokenEstimate keeps BOTH: ewma() (all tokens, 0.9/0.1) and clean() (median of the last 8 tokens not overlapped by a frame);
// value() = clean() once a clean token exists, else ewma(). Caller: workloads/background/llama_governed_bench.cpp; test: tests/test_tok_estimate_cpp.py.
#pragma once
#include <algorithm>
#include <cmath>
#include <limits>
#include <vector>

namespace tokest {

constexpr int WINDOW = 8;

class TokenEstimate {
public:
    void push(double tok_ms, bool overlapped) {
        e_ = have_ ? 0.9 * e_ + 0.1 * tok_ms : tok_ms;
        have_ = true;
        if (!overlapped) {
            c_.push_back(tok_ms);
            if ((int)c_.size() > WINDOW) c_.erase(c_.begin());
        }
    }
    bool have() const { return have_; }
    double ewma() const { return have_ ? e_ : 0.0; }
    double clean() const {
        if (c_.empty()) return std::numeric_limits<double>::quiet_NaN();
        std::vector<double> s(c_);
        std::sort(s.begin(), s.end());
        size_t n = s.size();
        return n % 2 ? s[n / 2] : 0.5 * (s[n / 2 - 1] + s[n / 2]);
    }
    double value() const { return c_.empty() ? ewma() : clean(); }
private:
    bool have_ = false;
    double e_ = 0.0;
    std::vector<double> c_;
};

// A token that started against a finite next fg arrival overlapped a frame iff it ended after that arrival; one that started with no finite arrival (fg idle) overlapped iff the fg
// published during the token (pace_updated_ms >= t0_ms). All times in ms on the QPC timeline.
inline bool token_overlapped(double t1_ms, double next_at_start_ms, double t0_ms, bool pace_have, double pace_updated_ms) {
    if (std::isfinite(next_at_start_ms)) return t1_ms > next_at_start_ms;
    return pace_have && pace_updated_ms >= t0_ms;
}

}  // namespace tokest
