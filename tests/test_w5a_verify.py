"""W5a completeness/flag verification (analysis/w5a_verify.py): every cell of the frozen list has exactly one cell.json in its session, no incidents or extra cells, manifests match the files,
sessions share armoury mode / exe hash / git head, and per-cell flags (clock_ok, full GPU offload, frame count, ring drops, SM clock vs requested, temperature) are reported.
Instruction (Arjun, 2026-10-23): "Verify all three sessions are complete against the frozen list (280 cells), check flags, manifests and any aborts"."""
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "analysis"))
from w5a_verify import verify  # noqa: E402

EXE = "bb87"


def make(tmp, drop=None, bad=None, extra=False, incident=False, tamper=False):
    cells = [dict(cell_id=f"c{i}", session=1 + i % 2, order=i // 2, clock=1200 if i % 3 else "unlocked") for i in range(4)]
    (tmp / "list.json").write_text(json.dumps(dict(cells=cells)))
    for s in (1, 2):
        sd = tmp / f"session{s}"; sd.mkdir()
        (sd / "meta.json").write_text(json.dumps(dict(armoury_mode="Performance", chrome_running=False, exe_sha256=EXE, git_head="h")))
        for c in cells:
            if c["session"] != s or c["cell_id"] == drop:
                continue
            d = sd / c["cell_id"]; d.mkdir()
            r = dict(c, frames=1800, abandoned=0, ring_dropped=0, clock_ok=True, exec_mode="EXEC_MODE cuda offloaded=17/17 n_layer=16 governed=1",
                     sm_mhz_median=1200.0 if c["clock"] != "unlocked" else 2400.0, temp_after_c=60)
            if bad == c["cell_id"]:
                r["clock_ok"] = False; r["ring_dropped"] = 3
            (d / "cell.json").write_text(json.dumps(r)); (d / "driver.csv").write_text("x")
        if extra and s == 1:
            (sd / "stray").mkdir(); (sd / "stray" / "cell.json").write_text("{}")
        if incident and s == 1:
            (sd / "c0" / "incident.json").write_text("{}")
        files = {str(p.relative_to(sd)).replace(chr(92), "/"): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(sd.rglob("*")) if p.is_file()}
        (sd / "manifest.json").write_text(json.dumps(files))
    if tamper:
        (tmp / "session2" / "c1" / "driver.csv").write_text("changed")


def test_complete_and_clean_passes(tmp_path):
    make(tmp_path)
    rep = verify(tmp_path / "list.json", tmp_path, [1, 2])
    assert rep["ok"] and rep["problems"] == [] and rep["cells"] == 4


def test_missing_extra_incident_and_tampered_files_are_problems(tmp_path):
    make(tmp_path, drop="c3", extra=True, incident=True, tamper=True)
    p = " | ".join(verify(tmp_path / "list.json", tmp_path, [1, 2])["problems"])
    assert "missing" in p and "c3" in p and "stray" in p and "incident" in p and "manifest" in p


def test_cell_flags_are_reported(tmp_path):
    make(tmp_path, bad="c2")
    rep = verify(tmp_path / "list.json", tmp_path, [1, 2])
    assert not rep["ok"] and any("c2" in f and "clock_ok" in f for f in rep["flags"]) and any("c2" in f and "ring_dropped" in f for f in rep["flags"])


def test_sessions_must_share_exe_and_armoury_mode(tmp_path):
    make(tmp_path)
    m = json.loads((tmp_path / "session2" / "meta.json").read_text()); m["exe_sha256"] = "other"; m["armoury_mode"] = "Turbo"
    (tmp_path / "session2" / "meta.json").write_text(json.dumps(m))
    p = " | ".join(verify(tmp_path / "list.json", tmp_path, [1, 2])["problems"])
    assert "exe_sha256" in p and "armoury_mode" in p
