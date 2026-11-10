import json
import subprocess
from pathlib import Path

import pytest

import rg_synth
from tools.realgame import analyze as a
from tools.realgame import run as rg_run

GOLDEN = Path(__file__).parent / "data" / "golden_summary.json"


def approx_equal(x, y, path=""):
    if isinstance(x, dict):
        assert isinstance(y, dict) and set(x) == set(y), f"{path}: keys {sorted(set(x) ^ set(y))}"
        for k in x:
            approx_equal(x[k], y[k], f"{path}/{k}")
    elif isinstance(x, list):
        assert isinstance(y, list) and len(x) == len(y), path
        for i, (p, q) in enumerate(zip(x, y)):
            approx_equal(p, q, f"{path}[{i}]")
    elif isinstance(x, float) or isinstance(y, float):
        assert x == pytest.approx(y, rel=1e-9, abs=1e-9), f"{path}: {x} != {y}"
    else:
        assert x == y, f"{path}: {x!r} != {y!r}"


@pytest.fixture()
def tree(tmp_path):
    root = tmp_path / "run"
    order = rg_synth.build_tree(root)
    return root, order


def test_reproduces_golden_summary(tree, tmp_path):
    root, _ = tree
    out = tmp_path / "out"
    a.run_analysis(root, out, plots=False)
    got = json.loads((out / "summary.json").read_text())
    approx_equal(json.loads(GOLDEN.read_text()), got)


def test_cell_summary_matches_independent_computation(tree):
    import numpy as np
    root, order = tree
    d = rg_run.cell_dir(root, 1, 1, 0, "SOLO")
    s = a.cell_summary(d)
    res = json.loads((d / "result.json").read_text())
    rows = [line.split(",") for line in (d / "frames.csv").read_text().splitlines()[1:]]
    sel = [float(x[10]) for x in rows if x[2] == "0x1" and res["t_open"] <= int(x[9]) / 1e7 < res["t_close"]]
    assert s["n_frames"] == len(sel)
    assert s["p99"] == pytest.approx(float(np.percentile(sel, 99)))
    assert s["hitch_share"] == pytest.approx(100.0 * sum(v > 25.0 for v in sel) / len(sel))
    assert s["p50"] == pytest.approx(float(np.median(sel)))


def test_only_final_attempt_is_used_and_attempts_reported(tree, tmp_path):
    root, order = tree
    out = tmp_path / "o"
    summ = a.run_analysis(root, out, plots=False)
    assert all(c["attempt"] == 2 for c in summ["cells"] if c["rep"] == 0)
    assert all(c["attempt"] == 1 for c in summ["cells"] if c["rep"] != 0)
    assert summ["attempts"]["0"]["failed_attempts"] == [1] and summ["attempts"]["1"]["failed_attempts"] == []


def test_decision_and_predictability_sections(tree, tmp_path):
    root, _ = tree
    summ = a.run_analysis(root, tmp_path / "o", plots=False)
    assert summ["decision"]["branch"] in {"NO_PROBLEM", "SIMPLE_FIX", "FIX_TOO_SLOW", "BUILD_THE_GATE", "OPEN", "VOID"}
    assert summ["decision"]["arms"]["UNGATED"]["harmful"] is True
    assert summ["predictability"]["solo"]["primary"]["N"] == 8 and summ["predictability"]["ungated"]["informational"] is True
    assert set(summ["predictability"]["solo"]["sensitivity"]) == {"4", "16"}
    root_order = rg_synth.rg_run.make_order(11, 3)
    pg = summ["flags"]["paging"]
    assert len(pg) == 1 and pg[0]["rep"] == 1 and pg[0]["arm"] == "DUTY50" and pg[0]["pos"] == root_order[1].index("DUTY50")
    assert pg[0]["excess_mb"] == pytest.approx(100.0)


def test_prio_idle_void_readback_flows_into_decision(tmp_path):
    root = tmp_path / "run"
    rg_synth.build_tree(root, prio_readbacks=(0, 2))
    s = a.run_analysis(root, tmp_path / "o", plots=False)
    assert s["decision"]["prio_idle_valid"] is False


def test_refuses_non_empty_out(tree, tmp_path):
    root, _ = tree
    out = tmp_path / "out"
    out.mkdir()
    (out / "x.txt").write_text("keep")
    with pytest.raises(a.OutputRefused, match="not empty"):
        a.run_analysis(root, out, plots=False)
    assert (out / "x.txt").read_text() == "keep" and not (out / "summary.json").exists()
    out2 = tmp_path / "out2"
    a.run_analysis(root, out2, plots=False)
    with pytest.raises(a.OutputRefused):
        a.run_analysis(root, out2, plots=False)


def test_refuses_git_tracked_target(tree, tmp_path):
    root, _ = tree
    repo = tmp_path / "repo"
    (repo / "out").mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    (repo / "out" / "summary.json").write_text("{}")
    subprocess.run(["git", "-C", str(repo), "add", "out/summary.json"], check=True)
    (repo / "out" / "summary.json").unlink()                       # out is now empty, but the target path is tracked
    assert a.is_tracked(repo / "out" / "summary.json") is True
    assert a.is_tracked(repo / "out" / "other.json") is False
    with pytest.raises(a.OutputRefused, match="tracked"):
        a.run_analysis(root, repo / "out", plots=False)
    assert not (repo / "out" / "summary.json").exists()


def test_main_requires_run_dir_and_out(tree, tmp_path, capsys):
    root, _ = tree
    with pytest.raises(SystemExit):
        a.main(["--run-dir", str(root)])
    with pytest.raises(SystemExit):
        a.main(["--out", str(tmp_path / "x")])
    assert a.main(["--run-dir", str(root), "--out", str(tmp_path / "ok"), "--no-plots"]) == 0
    assert a.main(["--run-dir", str(root), "--out", str(tmp_path / "ok"), "--no-plots"]) != 0
    assert "not empty" in capsys.readouterr().err


def test_plots_written_with_agg(tree, tmp_path):
    pytest.importorskip("matplotlib")
    root, _ = tree
    out = tmp_path / "o"
    a.run_analysis(root, out, plots=True)
    pngs = sorted(p.name for p in out.glob("*.png"))
    assert pngs and all((out / p).stat().st_size > 0 for p in pngs)


def test_missing_cell_result_fails_loudly(tree, tmp_path):
    root, order = tree
    (rg_run.cell_dir(root, 2, 1, 0, "SOLO") / "result.json").unlink()
    with pytest.raises(ValueError, match="rep 2"):
        a.run_analysis(root, tmp_path / "o", plots=False)


def test_igpu_dropped_summary_states_igpu_not_tested(tmp_path):
    root = tmp_path / "run"
    rg_synth.build_tree(root, arms=("UNGATED", "PRIO_IDLE", "DUTY50"))
    out = tmp_path / "out"
    summ = a.run_analysis(root, out, plots=False)
    assert summ["decision"]["igpu_tested"] is False
    assert "IGPU option not tested" in (out / "summary.md").read_text()


def test_igpu_measured_summary_has_no_not_tested_sentence(tree, tmp_path):
    root, _ = tree
    out = tmp_path / "out"
    summ = a.run_analysis(root, out, plots=False)
    assert summ["decision"]["igpu_tested"] is True
    assert "not tested" not in (out / "summary.md").read_text()
