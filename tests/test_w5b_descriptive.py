"""Post hoc descriptive tables (analysis/w5b_descriptive.py): feasibility counts and final pacing mode per scene and controller. Not a registered test."""
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "analysis"))
import w5b_descriptive as wd  # noqa: E402


def frame():
    rows = [
        dict(block=1, scene="S0", controller="d'B", budget_w=60.0, bg_tok_s=17.0, miss_frac=0.0, power_w=58.0, final_pacing_mode="unaligned"),
        dict(block=2, scene="S0", controller="d'B", budget_w=60.0, bg_tok_s=16.0, miss_frac=0.02, power_w=58.0, final_pacing_mode="aligned"),
        dict(block=1, scene="S0", controller="g'B", budget_w=60.0, bg_tok_s=0.0, miss_frac=0.0, power_w=61.0, final_pacing_mode="aligned"),
    ]
    return pd.DataFrame(rows)


def test_feasibility_split_and_modes():
    t = wd.table(frame(), 60.0).set_index("controller")
    assert t.loc["d'B", "n"] == 2 and t.loc["d'B", "miss_ok"] == 1 and t.loc["d'B", "power_ok"] == 2 and t.loc["d'B", "feasible"] == 1
    assert t.loc["d'B", "final_pacing_mode"] == "aligned 1, unaligned 1"
    assert t.loc["g'B", "power_ok"] == 0 and t.loc["g'B", "feasible"] == 0


def test_scatter_writes_a_png(tmp_path):
    png = tmp_path / "s.png"
    wd.scatter(frame(), str(png))
    assert png.exists() and png.stat().st_size > 1000


def test_dbp_modes_groups_by_final_mode():
    g = wd.dbp_modes(frame())
    assert set(g.index.get_level_values("final_pacing_mode")) == {"aligned", "unaligned"}
