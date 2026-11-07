"""v2 bench (tools/bench.py): the pure parts that turn a run into table numbers: control block per setup, token and power windows, glitch filtering, aggregation, table, preflight failure. No GPU.
Instruction (Arjun, 2026-11-07): "tools/bench.py: one command that runs a named setup N times (default 3 x 60 s) and prints a small table of late frames %, frame p99, tok/s, mean power, VRAM per process." """
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import bench  # noqa: E402


def test_setups_map_to_the_v1_driver_modes():
    assert bench.ctrl_values("free", 0.5) == [0.0, 1.0, 0.5]              # unaligned, duty 1: back-to-back tokens
    assert bench.ctrl_values("paced", 0.5) == [1.0, 1.0, 0.5]             # aligned slack filling, duty 1
    assert set(bench.SETUPS) == {"yolo-alone", "yolo-3b-free", "yolo-3b-paced", "yolo-8b-free", "yolo-8b-paced"}
    assert bench.SETUPS["yolo-alone"] == (None, None) and bench.SETUPS["yolo-8b-paced"] == ("8b", "paced")


def test_token_rate_counts_only_the_window():
    ends = [1.0, 2.0, 2.5, 3.0, 5.0, 7.5]
    assert bench.tokens_per_s(ends, 2.0, 6.0) == pytest.approx(4 / 4.0)   # 2.0, 2.5, 3.0, 5.0; both edges inclusive
    assert bench.tokens_per_s([], 0.0, 10.0) == 0.0


def test_power_mean_drops_and_counts_the_590_w_glitch():
    s = [(0.5, 40.0), (1.0, 50.0), (1.5, 590.006), (2.0, 60.0), (2.5, -3.0), (9.0, 70.0)]
    mean_w, used, dropped = bench.power_mean(s, 1.0, 3.0)
    assert (mean_w, used, dropped) == (pytest.approx(55.0), 2, 2)         # 50 and 60 kept; 590 W and the negative reading dropped; outside the window ignored
    assert bench.power_mean([(5.0, 1.0)], 0.0, 1.0) == (None, 0, 0)


def run(late, p99, tok, w, vy, vl, full=False):
    return dict(late_pct=late, lat_p99_ms=p99, tok_s=tok, power_w=w, vram_mib=dict(yolo=vy, llama=vl), near_full=full)


def test_aggregate_means_and_missing_values():
    agg = bench.aggregate([run(1.0, 30.0, 50.0, 60.0, 400.0, 2600.0), run(3.0, 40.0, 54.0, 62.0, 420.0, 2700.0, full=True)])
    assert agg["runs"] == 2 and agg["late_pct"] == pytest.approx(2.0) and agg["lat_p99_ms"] == pytest.approx(35.0) and agg["tok_s"] == pytest.approx(52.0)
    assert agg["vram_yolo_mib"] == pytest.approx(410.0) and agg["vram_llama_mib"] == pytest.approx(2650.0) and agg["near_full"] is True
    alone = bench.aggregate([run(0.0, 12.0, None, 30.0, 400.0, None)])
    assert alone["tok_s"] is None and alone["vram_llama_mib"] is None


def test_table_has_every_column_marks_near_full_and_names_a_skipped_setup():
    runs = [run(0.5, 20.0, 55.0, 61.0, 400.0, 2600.0, full=True)]
    t = bench.format_table([("yolo-3b-paced", bench.aggregate(runs), runs), ("yolo-alone", bench.aggregate([run(0.0, 12.0, None, 30.0, 400.0, None)]), []), ("yolo-8b-free", "does not fit in VRAM", [])])
    lines = t.splitlines()
    assert lines[0].split()[:2] == ["setup", "runs"] and "VRAM" in lines[0] and "p99" in lines[0] and "tok/s" in lines[0]
    assert "0.50" in lines[2] and "55.0" in lines[2] and "2600*" in lines[2]
    assert "n/a" in lines[3]                                              # yolo-alone has no tok/s and no llama VRAM
    assert "does not fit in VRAM" in lines[4]
    assert "run 1" in bench.format_table([("x", bench.aggregate(runs), runs)], per_run=True)


def test_preflight_fails_loudly_on_a_missing_video():
    with pytest.raises(SystemExit) as e:
        bench.main(["yolo-alone", "--check", "--video", str(Path(__file__).parent / "no_such_video.mp4")])
    assert "video not found" in str(e.value)
