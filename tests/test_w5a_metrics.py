"""W5a per-cell metrics (experiments/w5a/w5a_metrics.py): a cell is 5 s warm-up + 30 s measured; frames scheduled before the window are dropped; miss = latency from the SCHEDULED arrival above
the 16.667 ms period; bg tok/s = tokens ending inside the window / window length; power = energy-counter delta over the window / window length; ctrl values follow the registered pacing configurations.
Instruction (Arjun, 2026-10-23): "give me the W5a session-1 commands" (the runner they call must be tested)."""
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "experiments" / "w5a"))
from w5a_metrics import ctrl_values, dirty_paths, summarise_cell  # noqa: E402

PERIOD = 1000.0 / 60.0


def frames(n, t0, lat_ms):
    return [dict(t_sched=t0 + k * PERIOD / 1000.0, lat_ms=float(lat_ms(k))) for k in range(n)]


def test_window_drops_warmup_and_counts_misses_from_the_scheduled_arrival():
    t0 = 100.0
    recs = frames(35 * 60, t0, lambda k: 30.0 if k < 5 * 60 else (20.0 if k % 100 == 0 else 6.0))        # warm-up frames are late but must not count
    tok_end = t0 + np.arange(0.0, 35.0, 0.02)                                                              # 50 tokens/s for 35 s
    s = summarise_cell(recs, tok_end, np.full(len(tok_end), 10.0), t0, 5.0, 30.0, e_start_mj=1_000_000.0, e_end_mj=1_000_000.0 + 30.0 * 55.0 * 1000.0, period_ms=PERIOD)
    assert s["frames"] == 30 * 60 and abs(s["miss_frac"] - 18 / 1800) < 1e-9 and abs(s["bg_tok_s"] - 50.0) < 0.1
    assert abs(s["power_w"] - 55.0) < 1e-9 and s["tok_ms_p50"] == 10.0


def test_no_tokens_in_the_window_gives_zero_rate_not_an_error():
    t0 = 0.0
    s = summarise_cell(frames(35 * 60, t0, lambda k: 5.0), np.array([1.0, 2.0]), np.array([10.0, 10.0]), t0, 5.0, 30.0, 0.0, 30000.0 * 40, PERIOD)
    assert s["bg_tok_s"] == 0.0 and np.isnan(s["tok_ms_p50"]) and s["miss_frac"] == 0.0


def test_ctrl_values_follow_the_pacing_configurations():
    assert ctrl_values(dict(mode="aligned", guard_ms=1.0, duty=0.25)) == [1.0, 0.25, 1.0]
    assert ctrl_values(dict(mode="unaligned", guard_ms=0.5, duty=0.1)) == [0.0, 0.1, 0.5]


def test_bad_window_arguments_are_refused():
    with pytest.raises(ValueError):
        summarise_cell([], np.array([]), np.array([]), 0.0, 5.0, 0.0, 0.0, 0.0, PERIOD)


def test_dirty_tree_rule_allows_untracked_data_outputs_only():
    nl = chr(10)
    por = nl.join([" M analysis/w5_analysis.py", "?? data/w5a/session1/", "?? scratch.txt", "A  docs/x.md"]) + nl
    assert dirty_paths(por) == ["analysis/w5_analysis.py", "scratch.txt", "docs/x.md"]
    assert dirty_paths("?? data/w5a/cell_list.json" + nl) == [] and dirty_paths("") == []


def test_session_refusals_cover_armoury_ac_hash_tree_and_chrome():
    sys.argv = ["x"]
    import importlib.util                                                # experiments/w5a/run.py (a plain 'import run' would find the W2 run.py)
    spec = importlib.util.spec_from_file_location('w5a_run', ROOT / 'experiments' / 'w5a' / 'run.py')
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    refusal = mod.refusal
    ok = dict(armoury_mode="Performance", plugged=True, listing_sha="a", expected_sha="a", porcelain="?? data/w5a/\n", chrome=False)
    assert refusal(**ok) is None
    assert "armoury" in refusal(**dict(ok, armoury_mode=None)).lower()
    assert "battery" in refusal(**dict(ok, plugged=False))
    assert "frozen" in refusal(**dict(ok, expected_sha="b"))
    assert "clean" in refusal(**dict(ok, porcelain=" M a.py\n"))
    assert "Chrome" in refusal(**dict(ok, chrome=True))
