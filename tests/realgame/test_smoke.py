"""--smoke ARM: one short cell (5 s warm-up, 20 s window) through the normal cell.run_cell path, written under <run-dir>/smoke/<ARM>_<n>/."""
import json
from pathlib import Path

import pytest

import rg_synth
from test_cell import SAMPLE_HEADER, Clock, FakeProbes, FakeSampler, make_cfg, make_deps
from tools.realgame import analyze as a
from tools.realgame import cell as c
from tools.realgame import presentmon
from tools.realgame import run as r


class SmokeCapture:
    """60 fps (or `fps`) frames for 32 s from the start of capture; busy 6..10 ms (median 8), one 30 ms frame per 200 (hitch share 0.5 %)."""
    fps = 60.0
    instances = []

    def __init__(self, clock, out_csv, fps=None):
        self.clock, self.out_csv, self.started, self.fps = clock, out_csv, False, fps or SmokeCapture.fps
        SmokeCapture.instances.append(self)

    def start(self):
        self.started, self.t0 = True, self.clock.now()

    def stop(self, timeout=10.0):
        if not self.started:
            return
        rows = [SAMPLE_HEADER]
        for i in range(int(32 * self.fps)):
            t = self.t0 + i / self.fps
            ft = 30.0 if i % 200 == 199 else 16.667
            busy = 6.0 + (i % 5)
            rows.append(f"G.exe,1,0xA,D3D11,1,0,0,Hardware: Independent Flip,Application,{int(t * 1e7)},{ft},3,13,1.0,{busy + 0.2},{busy},1,0,20,16.7,0,0,0,NA,NA,NA")
        Path(self.out_csv).write_text("\n".join(rows) + "\n")


def smoke_deps(clock, fps=None, **kw):
    d, box = make_deps(make_cfg(Path(".")), clock, **kw)
    d.make_capture = lambda cfg, out_csv, session: (kw.get("order") is not None and kw["order"].append(("capture", session)), SmokeCapture(clock, out_csv, fps))[1]

    def sampler(nv):
        sm = FakeSampler(clock)
        sm.limit = [95.0] * len(sm.t)
        sm.sm = [1500 if i % 2 else 1600 for i in range(len(sm.t))]       # a varying clock: a constant one is refused as locked
        return sm
    d.make_sampler = sampler
    return d, box


def prepare(tmp_path):
    run = tmp_path / "run"
    r.write_clock_check(run, "passed", {"max_sm_mhz": 2100}, [])
    return run


def argv(tmp_path, arm, extra=()):
    return ["--smoke", arm, "--run-dir", str(tmp_path / "run"), "--armoury-mode", "Turbo", "--llm-exe", "a", "--model", "b", "--prompt", "c", "--presentmon", "d",
            "--game-process", "g.exe", "--n-prompt", "64", "--llama-dir", str(tmp_path / "llama.cpp"), "--repo-root", str(tmp_path), *extra]


def smoke(tmp_path, arm, probes=None, deps=None, **kw):
    prepare(tmp_path) if not (tmp_path / "run" / "clock_check.json").exists() else None
    clock = Clock()
    d, box = (deps, None) if deps else smoke_deps(clock)
    code = r.main(argv(tmp_path, arm), probes=probes or FakeProbes(), deps=d, **kw)
    return code, d, box


def test_constants():
    assert r.SMOKE_WARM_S == 5.0 and r.SMOKE_WINDOW_S == 20.0


@pytest.mark.parametrize("arm", ["PRIO_IDLE", "DUTY50", "IGPU", "LLM_ALONE", "solo", ""])
def test_rejects_other_arm_names(tmp_path, arm):
    with pytest.raises(SystemExit):
        r.main(argv(tmp_path, arm), probes=FakeProbes())
    assert not (tmp_path / "run" / "smoke").exists()


def test_solo_smoke_writes_numbered_dirs_never_overwrites(tmp_path, capsys):
    assert smoke(tmp_path, "SOLO")[0] == 0
    first = tmp_path / "run" / "smoke" / "SOLO_1"
    assert (first / "result.json").exists() and (first / "meta.json").exists()
    stamp = (first / "result.json").read_text()
    assert smoke(tmp_path, "SOLO")[0] == 0
    assert (tmp_path / "run" / "smoke" / "SOLO_2" / "result.json").exists() and (first / "result.json").read_text() == stamp
    assert smoke(tmp_path, "UNGATED")[0] == 0
    assert (tmp_path / "run" / "smoke" / "UNGATED_1" / "result.json").exists()
    assert not (tmp_path / "run" / "run_meta.json").exists() and not list((tmp_path / "run").glob("rep*"))


def test_smoke_dir_gap_is_not_reused(tmp_path):
    (tmp_path / "run" / "smoke" / "SOLO_3").mkdir(parents=True)
    smoke(tmp_path, "SOLO")
    assert (tmp_path / "run" / "smoke" / "SOLO_4" / "result.json").exists() and not (tmp_path / "run" / "smoke" / "SOLO_1").exists()


def test_window_and_warmup_passed_through_and_recorded(tmp_path):
    seen = []

    def runner(arm, rep, out_dir, cfg, **kw):
        seen.append((arm, kw))
        return {}
    prepare(tmp_path)
    r.main(argv(tmp_path, "SOLO"), probes=FakeProbes(), runner=runner)
    assert seen == [("SOLO", {"warmup_s": 5.0, "window_s": 20.0, "smoke": True})]
    smoke(tmp_path, "SOLO")
    d = tmp_path / "run" / "smoke" / "SOLO_2"
    for f in ("result.json", "meta.json"):
        doc = json.loads((d / f).read_text())
        assert doc["smoke"] is True and doc["warmup_s"] == 5.0 and doc["window_s"] == 20.0, f
    res = json.loads((d / "result.json").read_text())
    assert res["t_close"] - res["t_open"] == pytest.approx(20.0)


def test_run_cell_explicit_window_overrides_config_and_default_has_no_smoke_key(tmp_path):
    clock = Clock()
    d, _ = smoke_deps(clock)
    res = c.run_cell("SOLO", 0, tmp_path / "x", make_cfg(tmp_path), d, warmup_s=5.0, window_s=20.0, smoke=True)
    assert res["warmup_s"] == 5.0 and res["window_s"] == 20.0 and res["smoke"] is True
    d2, _ = make_deps(make_cfg(tmp_path), Clock())
    assert "smoke" not in c.run_cell("SOLO", 0, tmp_path / "y", make_cfg(tmp_path), d2)


def test_frame_count_threshold_uses_the_20s_window(tmp_path):
    # 1200 frames in 20 s pass 0.95 x 60 x 20 = 1140 (they would fail the 60 s rule of 3420); 55 fps = 1100 frames fail
    assert smoke(tmp_path, "SOLO")[0] == 0
    clock = Clock()
    d, _ = smoke_deps(clock, fps=55.0)
    with pytest.raises(presentmon.PresentMonGapError, match="1140"):
        c.run_cell("SOLO", 0, tmp_path / "bad", make_cfg(tmp_path), d, warmup_s=5.0, window_s=20.0, smoke=True)
    assert not (tmp_path / "bad" / "result.json").exists()


FIELDS_ANY = ["arm: ", "frames in window: ", "achieved fps", "frame time ms p50 / p99 / max", "1% low fps", "hitch share (> 25.0 ms)", "GPU busy per frame ms median / p95",
              "idle per frame ms (frame - GPU busy) median", "PresentMode seen", "dominant swapchain", "any frame dropped", "PresentMon CSV header: ", "VRAM MiB start / end",
              "idle VRAM MiB", "temperature C start / end", "enforced power limit W start / end / min / max", "SM clock median MHz", "throttle masks", "power W (energy counter)",
              "power_rejected"]


def summary_of(tmp_path, arm, n=1):
    d = tmp_path / "run" / "smoke" / f"{arm}_{n}"
    return (d / "smoke_summary.txt").read_text(), d


@pytest.mark.parametrize("arm", ["SOLO", "UNGATED"])
def test_summary_has_each_field_printed_and_saved(tmp_path, capsys, arm):
    assert smoke(tmp_path, arm)[0] == 0
    text, d = summary_of(tmp_path, arm)
    out = capsys.readouterr().out
    assert text.strip() in out
    for f in FIELDS_ANY:
        assert f in text, f
    assert f"arm: {arm}" in text and "frames in window: 1200" in text and "achieved fps (frames / window_s): 60.00" in text
    assert "Hardware: Independent Flip" in text and "any frame dropped: no" in text and SAMPLE_HEADER in text
    assert "frame time ms p50 / p99 / max: 16.67 / " in text and "/ 30.00" in text
    assert "GPU busy per frame ms median / p95: 8.00 / 10.00" in text and "idle per frame ms (frame - GPU busy) median: 8.67" in text
    assert "hitch share (> 25.0 ms): 0.50 %" in text
    assert "VRAM MiB start / end: 2048.0 / 2048.0" in text and "idle VRAM MiB: 2048.0" in text and "temperature C start / end: 61.0 / 61.0" in text
    assert "enforced power limit W start / end / min / max: 95.0 / 95.0 / 95.0 / 95.0" in text and "SM clock median MHz: 1550" in text
    assert "power W (energy counter): 90.00" in text and "power_rejected: 0" in text
    if arm == "UNGATED":
        assert "tok/s in window: 100." in text and "LLM exec line: EXEC_MODE cuda" in text and "preset acceptance" not in text
    else:
        assert "tok/s" not in text and "LLM exec line" not in text
        assert "preset acceptance (prereg): GPU busy median in 6 to 10 ms: yes; hitch share below 1%: yes; fps >= 59: yes" in text
        assert "information only" in text.lower() and "decides nothing" in text
    assert (d / "real_header.csv").read_text() == SAMPLE_HEADER + "\n"


def test_preset_acceptance_line_thresholds():
    from tools.realgame import smoke as sm
    line = sm.preset_acceptance_line
    assert line({"gpu_busy_median": 11.0, "hitch_share": 2.0, "fps": 58.0}).endswith("GPU busy median in 6 to 10 ms: no; hitch share below 1%: no; fps >= 59: no")
    assert "6 to 10 ms: yes; hitch share below 1%: yes; fps >= 59: yes" in line({"gpu_busy_median": 6.0, "hitch_share": 0.99, "fps": 59.0})
    assert "6 to 10 ms: yes" in line({"gpu_busy_median": 10.0, "hitch_share": 1.0, "fps": 59.0}) and "below 1%: no" in line({"gpu_busy_median": 10.0, "hitch_share": 1.0, "fps": 59.0})
    assert "6 to 10 ms: no" in line({"gpu_busy_median": 5.99, "hitch_share": 0.0, "fps": 60.0})


def test_ungated_smoke_spawns_llm_and_solo_does_not(tmp_path):
    order = []
    clock = Clock()
    d, box = smoke_deps(clock, order=order)
    assert smoke(tmp_path, "SOLO", deps=d)[0] == 0 and [o[0] for o in order] == ["capture"]
    order.clear()
    assert smoke(tmp_path, "UNGATED", deps=d)[0] == 0
    assert order[0] == ("spawn", "cuda", "0") and order[1][0] == "capture" and box["l"].sent[0].startswith("GO ")


def test_no_rest_noise_or_rep_logic(tmp_path):
    smoke(tmp_path, "SOLO")
    run = tmp_path / "run"
    assert not (run / "rest_log.jsonl").exists() and not list(run.rglob("NOISE_OK.json")) and not list(run.rglob("FAILED.json"))


# ---------------------------------------------------------------- preflight refusals are the sweep's
def test_refuses_dirty_tree(tmp_path, capsys):
    code, d, _ = smoke(tmp_path, "SOLO", probes=FakeProbes(dirty=[" M x"]))
    assert code == 2 and "dirty" in capsys.readouterr().err and not (tmp_path / "run" / "smoke").exists()


def test_refuses_game_absent(tmp_path, capsys):
    assert smoke(tmp_path, "UNGATED", probes=FakeProbes(game=False))[0] == 2
    assert "game process" in capsys.readouterr().err


def test_refuses_without_or_with_failed_clock_check(tmp_path, capsys):
    clock = Clock()
    d, _ = smoke_deps(clock)
    assert r.main(argv(tmp_path, "SOLO"), probes=FakeProbes(), deps=d) == 2
    assert "clock check refused" in capsys.readouterr().err
    r.write_clock_check(tmp_path / "run", "refused", {}, ["x"])
    assert r.main(argv(tmp_path, "SOLO"), probes=FakeProbes(), deps=d) == 2
    assert "clock check refused" in capsys.readouterr().err and not (tmp_path / "run" / "smoke").exists()


def test_refuses_pm_hash_mismatch_and_missing_dll_dir(tmp_path, capsys):
    prepare(tmp_path)
    clock = Clock()
    d, _ = smoke_deps(clock)
    a_ = argv(tmp_path, "SOLO")
    a_[a_.index("--presentmon") + 1] = "pm_other.exe"
    assert r.main(a_, probes=FakeProbes(), deps=d) == 2
    assert "sha256" in capsys.readouterr().err.lower() or "presentmon" in capsys.readouterr().err.lower()


def test_power_static_mismatch_refuses_the_smoke_cell(tmp_path):
    prepare(tmp_path)
    clock = Clock()
    d, _ = smoke_deps(clock)

    class Drift(FakeProbes):                  # the cell-start read differs from the sweep-start reference taken from the main probes
        def nvml_power_static(self):
            return dict(super().nvml_power_static(), max_power_limit_w=150.0)
    d.probes = Drift()
    with pytest.raises(RuntimeError, match="power refused"):
        r.main(argv(tmp_path, "SOLO"), probes=FakeProbes(), deps=d)
    assert not list((tmp_path / "run" / "smoke").rglob("result.json"))


def test_elevation_recorded_in_meta_and_result(tmp_path):
    smoke(tmp_path, "SOLO")
    d = tmp_path / "run" / "smoke" / "SOLO_1"
    assert "elevated" in json.loads((d / "meta.json").read_text()) and "elevated" in json.loads((d / "result.json").read_text())


def test_smoke_with_llm_alone_is_rejected(tmp_path):
    with pytest.raises(SystemExit):
        r.main(argv(tmp_path, "SOLO", ["--llm-alone"]), probes=FakeProbes())


# ---------------------------------------------------------------- analyze ignores smoke
def test_analyze_ignores_smoke_dir(tmp_path):
    root = tmp_path / "run"
    order = rg_synth.build_tree(root)
    before = a.run_analysis(root, tmp_path / "o1", plots=False)
    fa = r.final_attempts(root, order)
    for arm, n in (("SOLO", 1), ("UNGATED", 1), ("SOLO", 2)):
        sd = root / "smoke" / f"{arm}_{n}"
        sd.mkdir(parents=True)
        (sd / "result.json").write_text(json.dumps({"arm": arm, "smoke": True, "garbage": True}))
        (sd / "FAILED.json").write_text("{}")
        (sd / "NOISE_OK.json").write_text("{}")
    (root / "smoke" / "run_meta.json").write_text("not json")
    after = a.run_analysis(root, tmp_path / "o2", plots=False)
    assert before == after and r.final_attempts(root, order) == fa
    assert json.loads((tmp_path / "o1" / "summary.json").read_text()) == json.loads((tmp_path / "o2" / "summary.json").read_text())
    assert r.failed_attempts(root, order) == r.failed_attempts(root, order) and r._any_cell_ran(root)
