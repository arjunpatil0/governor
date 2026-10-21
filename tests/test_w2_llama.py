"""Part L (llama.cpp validation addendum 2026-10-21): cell list, execution-mode check, window extraction, HL1-HL3 summaries."""
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import yaml

from design import build_cells, cell_seed

ROOT = Path(__file__).resolve().parents[1]
CFG = yaml.safe_load((ROOT / "experiments" / "w2_colocation.yaml").read_text(encoding="utf-8"))
LEVELS = [600, 750, 900, 1050, 1200, 1350, 1500, 1800, "unlocked"]


def test_part_L_is_nine_levels_with_memory_locked_and_no_synthetic_workloads():
    cells = build_cells(CFG, "L")
    assert [c["sm_mhz"] for c in cells] == LEVELS
    assert len({c["cell_id"] for c in cells}) == 9
    assert all(c["mem_mhz"] == 8001 and c["fg"] is None and c["bg"] is None and c["part"] == "L" for c in cells)
    assert all(c["llama"]["model"] == "Llama-3.2-3B-Instruct-Q4_K_M.gguf" and c["llama"]["n_prompt"] == 512 for c in cells)


def test_exec_mode_requires_every_layer_offloaded():
    from llama_cell import parse_exec_mode
    assert parse_exec_mode("load...\nEXEC_MODE cuda offloaded=29/29 n_layer=28 model_size=2019377696\n")["ok"]
    assert not parse_exec_mode("EXEC_MODE cuda offloaded=20/29 n_layer=28 model_size=1\n")["ok"]
    assert not parse_exec_mode("EXEC_MODE cpu offloaded=0/29 n_layer=28 model_size=1\n")["ok"]
    assert not parse_exec_mode("nothing useful")["ok"]


def test_window_tokens_counts_only_tokens_ending_inside_the_window_and_flags_late_start():
    from llama_cell import window_tokens
    t = np.array([0.5, 1.0, 1.4, 2.0, 2.9, 3.1])
    n, late = window_tokens(t, 1.0, 3.0)
    assert n == 4 and not late                                  # 1.0, 1.4, 2.0, 2.9 (end-exclusive)
    n2, late2 = window_tokens(np.array([1.2, 2.0]), 1.0, 3.0)
    assert n2 == 2 and late2                                    # first token ended after the window opened: decode had not started (as part C)
    n3, late3 = window_tokens(np.array([]), 1.0, 3.0)
    assert n3 == 0 and late3


def test_hl3_token_sequences_must_agree_on_their_common_prefix_within_a_block():
    from w2_analysis import hl3_sequences
    long = list(range(100))
    ok = hl3_sequences({("b0", 600): long[:70], ("b0", 1800): long, ("b1", 600): [9, 8], ("b1", 1800): [9, 8, 7]})
    assert ok["bad_blocks"] == [] and ok["inconclusive_blocks"] == ["b1"]       # b1: shared prefix 2 < 64 tokens -> does not count
    assert ok["shared_prefix"][("b0", 600)] == 70 and ok["shared_prefix"][("b0", 1800)] == 100
    bad = hl3_sequences({("b0", 600): long[:80], ("b0", 1800): long[:40] + [999] + long[41:]})
    assert bad["bad_blocks"] == ["b0"] and bad["shared_prefix"][("b0", 600)] == 40      # reference = the block's longest sequence


def test_l_rel_thr_and_j_per_token():
    from w2_analysis import l_rel_thr
    df = pd.DataFrame(dict(block=[0, 0, 1, 1], sm_mhz=[1200, "unlocked", 1200, "unlocked"], tok_s=[50.0, 100.0, 60.0, 100.0],
                           energy_j=[100.0, 200.0, 120.0, 200.0], tokens=[200, 400, 240, 400]))
    d = l_rel_thr(df)
    assert d.rel_thr.round(3).tolist() == [0.5, 1.0, 0.6, 1.0]
    assert d.j_per_token.round(3).tolist() == [0.5, 0.5, 0.5, 0.5]


@pytest.mark.parametrize("knee,label", [(900, "fp16-proxy-like"), (1200, "fp16-proxy-like"), (1350, "intermediate"), (1800, "intermediate"),
                                         ("unlocked", "int4-proxy-like"), (None, "int4-proxy-like")])
def test_hl1_classification_boundaries(knee, label):
    from w2_analysis import classify_llama_knee
    assert classify_llama_knee(knee) == label


def test_hl1_knee_and_block_bootstrap_ci():
    from w2_analysis import l_knee
    rows = []
    for b in range(10):
        for lv, r in [(600, .3), (900, .6), (1200, .96), (1500, .99), (1800, 1.0), ("unlocked", 1.0)]:
            rows.append(dict(block=b, level=lv, rel_thr=r, j_per_token=1.0))
    k = l_knee(pd.DataFrame(rows))
    assert k["knee"] == 1200 and k["ci_lo"] == 1200 and k["ci_hi"] == 1200


def test_report_L_end_to_end_on_a_synthetic_run_dir(tmp_path):
    import json
    from w2_analysis import report_L
    meta = dict(utc="x", admin=True, ac_plugged=True, ambient_c=25, gpu="g", driver="d", yaml_sha="y", dll_sha="d", git_head="abcdefgh1234",
                hags=dict(line="Enabled:True"), execution_mode="llama")
    (tmp_path / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
    rel = {600: .4, 750: .55, 900: .7, 1050: .8, 1200: .93, 1350: .97, 1500: .99, 1800: 1.0, "unlocked": 1.0}
    rows = []
    for b in range(3):
        for i, lv in enumerate(LEVELS):
            tok = int(400 * rel[lv])
            cdir = tmp_path / "cells" / f"b{b:02d}_{i:02d}_llama_{lv}"
            cdir.mkdir(parents=True)
            pd.DataFrame(dict(t_tok_end=np.arange(tok) * 0.01, token=[7, 8, 9, 10] * (tok // 4) + [1] * (tok % 4))).to_csv(cdir / "llama_tokens.csv", index=False)
            rows.append(dict(block=b, cell_idx=i, cell_id=f"llama_{lv}", sm_mhz=lv, tok_s=tok / 4.0, tokens=tok, energy_j=tok * 0.2, power_counter_w=50.0, flags=""))
    pd.DataFrame(rows).to_csv(tmp_path / "results.csv", index=False)
    lines, tag = report_L(tmp_path)
    text = "\n".join(lines)
    assert tag == "L" and "knee 1350 MHz" in text and "intermediate" in text and "blocks with differing sequences: none" in text


def test_report_L_has_power_and_tok_s_table_and_proxy_lesson(tmp_path):
    test_report_L_end_to_end_on_a_synthetic_run_dir(tmp_path)
    from w2_analysis import report_L
    text = chr(10).join(report_L(tmp_path)[0])
    assert "tok_s_median" in text and "power_w_median" in text
    assert "Proxy lesson" in text and "measured on the actual workload" in text
    assert "Reliability" in text and "resolved" in text
