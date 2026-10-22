"""sim/pacing.py: the pure pacing decisions shared by the plant, the governed llama driver (C++ mirror in workloads/background/pacing.h) and the golden-case test."""
import math

import pytest

from sim.pacing import aligned_may_start, unaligned_wake


def test_unaligned_wake_inserts_a_gap_from_the_measured_token_time():
    assert unaligned_wake(100.0, 110.0, 0.5) == pytest.approx(120.0)           # 10 ms token, duty 0.5 -> 10 ms gap
    assert unaligned_wake(100.0, 110.0, 0.25) == pytest.approx(140.0)
    assert unaligned_wake(100.0, 110.0, 1.0) == 110.0


def test_unaligned_wake_with_zero_duty_never_wakes():
    assert math.isinf(unaligned_wake(0.0, 10.0, 0.0))


def test_aligned_starts_only_with_an_empty_fg_queue_and_a_token_that_fits_with_the_guard():
    assert aligned_may_start(now=3.0, fg_busy=False, tok_est=10.0, guard=0.5, next_arrival=16.6667)
    assert not aligned_may_start(now=3.0, fg_busy=True, tok_est=10.0, guard=0.5, next_arrival=16.6667)
    assert not aligned_may_start(now=7.0, fg_busy=False, tok_est=10.0, guard=0.5, next_arrival=16.6667)
    assert aligned_may_start(now=7.0, fg_busy=False, tok_est=10.0, guard=-3.0, next_arrival=16.6667)      # negative guard releases a token that does not fit
    assert aligned_may_start(now=7.0, fg_busy=False, tok_est=10.0, guard=0.5, next_arrival=math.inf)       # fg idle: free running
