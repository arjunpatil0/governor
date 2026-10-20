"""GPU integration test of the W2 kernels DLL (skipped when the DLL is not built or CUDA is unavailable; never falls back to CPU)."""
import pytest

from loadgen import residual_wait
from w2lib import DLL


@pytest.fixture(scope="module")
def w():
    if not DLL.exists():
        pytest.skip("w2_kernels.dll not built")
    from w2lib import W2
    try:
        return W2()
    except SystemExit as e:
        pytest.skip(str(e))


def _run(w, duty, seconds=0.6, units=20000):
    ts, te, _ = w.bg_until(1, [units], w.now() + seconds, duty=duty)
    return residual_wait(ts[2:], te[2:])


def test_duty_one_saturates_the_gpu(w):
    assert _run(w, 1.0)["rho"] > 0.99


@pytest.mark.parametrize("duty", [0.25, 0.5, 0.75])
def test_duty_cycle_option_hits_the_requested_utilisation(w, duty):
    r = _run(w, duty)
    assert r["rho"] == pytest.approx(duty, abs=0.04)
    assert r["gap_mean_s"] > 0


def test_bg_slices_are_timestamped_in_order(w):
    ts, te, g = w.bg_until(1, [4000], w.now() + 0.2)
    assert len(ts) > 10 and (te > ts).all() and (ts[1:] >= te[:-1]).all() and (g > 0).all()
