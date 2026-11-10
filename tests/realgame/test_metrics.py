import numpy as np
import pytest

from tools.realgame import metrics as m
from tools.realgame.presentmon import Frame

P = 1000 / 60


def test_constant_frames():
    r = m.frame_metrics([P] * 100)
    assert r["p50"] == pytest.approx(P) and r["p99"] == pytest.approx(P)
    assert r["hitch_share"] == 0.0 and r["n"] == 100 and r["low1_fps"] == pytest.approx(60.0)


def test_one_hitch_in_100_is_exactly_one_percent():
    r = m.frame_metrics([P] * 99 + [30.0])
    assert r["hitch_share"] == 1.0
    assert r["low1_fps"] == pytest.approx(1000 / 30.0)       # slowest 1% of 100 = 1 frame


def test_hitch_threshold_strict():
    assert m.frame_metrics([25.0] * 10)["hitch_share"] == 0.0
    assert m.frame_metrics([25.01] * 10)["hitch_share"] == 100.0
    assert m.HITCH_MS == 25.0


def test_p99_is_linear_interpolation():
    xs = list(range(1, 101))
    assert m.frame_metrics(xs)["p99"] == pytest.approx(float(np.percentile(xs, 99, method="linear")))
    assert m.PERCENTILE_METHOD == "linear"


def test_low1_uses_ceil_of_one_percent_and_at_least_one():
    xs = [10.0] * 197 + [40.0, 50.0, 60.0]       # n=200 -> 2 slowest frames (50,60)
    assert m.frame_metrics(xs)["low1_fps"] == pytest.approx(1000 / 55.0)
    assert m.frame_metrics([20.0, 40.0])["low1_fps"] == pytest.approx(25.0)   # at least 1 frame
    ys = [10.0] * 693 + [100.0] * 7             # 700 frames: 1% is 7, float 700*0.01 would give 8
    assert m.frame_metrics(ys)["low1_fps"] == pytest.approx(10.0)


def test_frame_metrics_rejects_bad_input():
    for bad in ([], [float("nan")], [-1.0]):
        with pytest.raises(ValueError):
            m.frame_metrics(bad)


def TOK(rows):
    return "t_tok_end_s,dur_ms,kind\n" + "\n".join(rows) + "\n"


def test_token_rate_window_edges_and_kind():
    txt = TOK(["9.999,10,token", "10.0,10,token", "15.0,10,reset", "19.999,10,token", "20.0,10,token", "25,10,token"])
    assert m.count_tokens(txt, 10.0, 20.0) == 2
    assert m.token_rate(txt, 10.0, 20.0) == pytest.approx(0.2)
    assert m.token_rate(TOK([]), 0, 1) == 0.0


def test_token_rate_errors(tmp_path):
    with pytest.raises(ValueError):
        m.token_rate(TOK([]), 5, 5)
    with pytest.raises(ValueError):
        m.token_rate("a,b\n1,2\n", 0, 1)
    p = tmp_path / "t.csv"
    p.write_text(TOK(["1.0,10,token"]))
    assert m.token_rate(p, 0, 2) == 0.5


HZ = 1e7


def frames(starts_s, busy=8.0, lat=1.0, frame_ms=P):
    return [Frame(t_cpu_start=s * HZ, frame_ms=frame_ms, gpu_busy_ms=busy, gpu_latency_ms=lat, displayed=True, swapchain="a", present_mode="x") for s in starts_s]


def test_predictability_perfect_cadence_passes():
    r = m.predictability(frames([i * P / 1000 for i in range(40)]), N=8, qpc_hz=HZ)
    assert r["N"] == 8 and r["n_predictions"] == 32
    assert r["start"]["p95"] == pytest.approx(0.0, abs=1e-6) and r["end"]["p95"] == pytest.approx(0.0, abs=1e-6)
    assert r["idle"]["p50"] == pytest.approx(P - 8.0)
    assert r["pass"] is True
    assert r["baseline_start"]["p50"] == pytest.approx(abs(P - 16.67), abs=1e-6)


def test_predictability_fails_on_jitter_and_on_idle():
    rng = np.random.default_rng(3)
    starts = np.cumsum(P / 1000 + rng.uniform(-0.004, 0.004, 200))
    assert m.predictability(frames(starts), N=8, qpc_hz=HZ)["pass"] is False
    good = frames([i * P / 1000 for i in range(40)], busy=15.0)
    r = m.predictability(good, N=8, qpc_hz=HZ)
    assert r["idle"]["p50"] < 3 and r["pass"] is False


def test_predictability_needs_n_plus_one_frames():
    with pytest.raises(ValueError):
        m.predictability(frames([i * P / 1000 for i in range(8)]), N=8, qpc_hz=HZ)
    assert m.predictability(frames([i * P / 1000 for i in range(9)]), N=8, qpc_hz=HZ)["n_predictions"] == 1
    with pytest.raises(ValueError):
        m.predictability(frames([0, 1]), N=1, qpc_hz=HZ)


def test_predictability_known_error():
    # steady 16 ms intervals except frame 8, which is 3 ms late; the N=8 prediction of frame 8 is s7 + 16
    s = [i * 16.0 for i in range(9)]
    s[8] += 3.0
    fr = [Frame(t_cpu_start=x / 1000 * HZ, frame_ms=16.0, gpu_busy_ms=5.0, gpu_latency_ms=0.0, displayed=True, swapchain="a", present_mode="x") for x in s]
    r = m.predictability(fr, N=8, qpc_hz=HZ)
    assert r["start"]["p50"] == pytest.approx(3.0, abs=1e-6)
    assert r["baseline_start"]["p50"] == pytest.approx(abs(19.0 - 16.67), abs=1e-6)


def test_predictability_report_sensitivity_and_pooling():
    fr = frames([i * P / 1000 for i in range(60)])
    rep = m.predictability_report([fr, fr], qpc_hz=HZ)
    assert rep["primary"]["N"] == 8 and set(rep["sensitivity"]) == {4, 16}
    assert rep["primary"]["n_predictions"] == 2 * 52
    assert rep["sensitivity"][16]["n_predictions"] == 2 * 44
