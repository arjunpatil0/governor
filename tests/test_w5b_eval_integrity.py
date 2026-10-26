"""Session integrity check of evaluation blocks (experiments/w5b/eval_integrity.py): block completeness, constants hash, incidents, gov_reads, counter vs sampled power, full offload, per-tick logging and power trace.
It reads no outcome (no miss, no tok/s). Instruction (Arjun, 2026-10-26): "Integrity check only - NO outcome analysis until all 10 blocks are done ... Report pass/fail only, plus any cell failing a check."""
import hashlib
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "experiments" / "w5b")); sys.path.insert(0, str(ROOT / "experiments" / "w5a"))
import eval_integrity as ei  # noqa: E402
import eval_lib as el  # noqa: E402
import evaluate  # noqa: E402

G60 = dict(sid="1800_a_g0_d1", clock=1800, mode="aligned", guard_ms=0.0, duty=1.0)
G35 = dict(sid="1500_a_g0_d1", clock=1500, mode="aligned", guard_ms=0.0, duty=1.0)
CONST = dict(c0=7, g_b={"60": G60, "35": G35}, c_b_t3b=dict(target=0.5, ki=0.15), c_b_t3c=dict(target=0.2, ki=0.15), d_b=dict(margin=0.3), power_source="sampled")


def make_world(tmp_path, blocks=(9,), **bad):
    """Constants file + session meta + complete blocks of good cells (the faults in `bad` are applied to the cell ids they name)."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    cp = tmp_path / "constants.json"; cp.write_text(json.dumps(CONST))
    sha = hashlib.sha256(cp.read_bytes()).hexdigest()
    out = tmp_path / "eval"
    sd = out / "sessions" / "20261025T201221Z"; sd.mkdir(parents=True)
    (sd / "meta.json").write_text(json.dumps(dict(blocks=list(blocks), as_blocks=list(blocks), constants_sha256=sha, power_source="sampled")))
    for b in blocks:
        for spec in el.block_cells(b, CONST):
            d = out / f"block{b:02d}" / "cells" / spec["id"]
            d.mkdir(parents=True)
            governed = spec["kind"] in ("cB", "dB", "eB")
            m = dict(miss=0.0, tok_s=10.0, power_w=40.0, power_sampled_w=40.5, gov_reads=0 if governed else None, power_source="sampled" if governed else None,
                     exec_mode="EXEC_MODE cuda offloaded=29/29 n_layer=28 governed=1")
            m.update(bad.get(spec["id"], {}).get("metrics", {}))
            (d / "cell.json").write_text(json.dumps(dict(id=spec["id"], spec=spec, metrics=m, executor="hw")))
            if governed and not bad.get(spec["id"], {}).get("no_frames"):
                g = np.zeros((650, 7)); g[:, 5] = 1.0; g[:, 6] = 40.0
                np.savez_compressed(d / "frames.npz", gov_log=g, pw_trace_t=0.5 * (np.arange(130) + 0.5), pw_trace_w=np.full(130, 40.0))
            elif not governed:
                np.savez_compressed(d / "frames.npz", gov_log=np.zeros((0, 7)))
            if bad.get(spec["id"], {}).get("incident"):
                (d / "incident.json").write_text("{}")
        (out / f"block{b:02d}" / "block.json").write_text("{}")
    evaluate.export_results(out)
    return out, cp, sha


def test_a_good_session_passes_and_reports_the_cell_count(tmp_path):
    out, cp, sha = make_world(tmp_path, blocks=(4, 9))
    r = ei.check_session(out, [4, 9], cp, sha)
    assert r["ok"] is True and r["problems"] == [] and r["n_cells"] == 55 + 30


def test_each_integrity_fault_is_reported_with_the_failing_cell(tmp_path):
    ids = {s["kind"] + s["controller"] + s["scene"]: s["id"] for s in el.block_cells(9, CONST)}
    cb, db, gb = ids["cBc'B-T3bS0"], ids["dBd'BS1"], ids["staticg'BS2"]
    eb, cc = ids["eBeBS0"], ids["cBc'B-T3cS1"]
    out, cp, sha = make_world(tmp_path, blocks=(9,), **{
        cb: dict(metrics=dict(gov_reads=300)), db: dict(no_frames=True), gb: dict(metrics=dict(power_w=90.0), incident=True),
        eb: dict(metrics=dict(exec_mode="EXEC_MODE cuda offloaded=10/29 n_layer=28 governed=1")), cc: dict(metrics=dict(power_source="energy"))})
    r = ei.check_session(out, [9], cp, sha)
    assert r["ok"] is False
    for cid, why in ((cb, "energy counter"), (db, "frames.npz"), (gb, "differ"), (gb, "incident"), (eb, "offload"), (cc, "sampled")):
        assert any(cid in line and why in line for line in r["problems"]), (cid, why, r["problems"])


def test_a_wrong_constants_hash_a_missing_cell_an_unfinished_block_a_session_meta_mismatch_and_a_discarded_block_fail(tmp_path):
    out, cp, sha = make_world(tmp_path, blocks=(9,))
    assert any("constants" in x for x in ei.check_session(out, [9], cp, "0" * 64)["problems"])
    victim = next((out / "block09" / "cells").iterdir())
    (victim / "cell.json").unlink()
    assert any("missing" in x and victim.name in x for x in ei.check_session(out, [9], cp, sha)["problems"])
    (out / "block09" / "block.json").unlink()
    assert any("not complete" in x for x in ei.check_session(out, [9], cp, sha)["problems"])
    out2, cp2, sha2 = make_world(tmp_path / "b", blocks=(9,))
    meta = next((out2 / "sessions").iterdir()) / "meta.json"
    meta.write_text(json.dumps(dict(blocks=[9], constants_sha256="f" * 64)))
    assert any("session meta" in x for x in ei.check_session(out2, [9], cp2, sha2)["problems"])
    (out2 / "discarded" / "block09_x").mkdir(parents=True)
    assert any("discarded" in x for x in ei.check_session(out2, [9], cp2, sha2)["problems"])


def test_the_check_reads_no_outcome():
    src = (ROOT / "experiments" / "w5b" / "eval_integrity.py").read_text(encoding="utf-8")
    assert '"miss"' not in src and '"tok_s"' not in src and "bg_tok_s" not in src
