"""tools/readme_numbers.py regenerates the README numbers block from the logged v2 data; the committed README must match it."""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_readme_block_matches_data():
    r = subprocess.run([sys.executable, str(ROOT / "tools/readme_numbers.py"), "--check", str(ROOT / "README.md")], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


def test_key_values():
    sys.path.insert(0, str(ROOT / "tools"))
    import readme_numbers as rn
    n = rn.compute()
    assert round(n["exp1.G14_gate.tok"][0], 1) == 44.6
    assert round(n["ladder.2.excess"][0], 2) == 1.71
    assert round(n["s1.3b.G14.overhead"][0], 1) == 2.2
    assert round(n["s1.8b.G14.overhead"][0], 1) == 1.4
    assert round(n["s1.8b.G14.longest_ms"][0], 2) == 3.61
    assert round(n["exp3.S1.g14.tok"][0], 1) == 47.9
    assert round(n["exp3.S5.whole.tok"][0], 1) == 0.0
    assert n["exp3.cells"][0] == 12 and n["exp3.max_late"][0] == 0.0
    assert n["exp1.G1_gate.bg_tokens"][0] == 0
    assert len(n["ladder.9.excess_reps"][0]) == 3 and len(n["ladder.2.excess_reps"][0]) == 2


def test_prose_sentences_are_generated():
    sys.path.insert(0, str(ROOT / "tools"))
    import readme_numbers as rn
    P = rn.prose(rn.compute())
    assert "17.5 tok/s against 0 for whole-token gating" in P["lead"]
    assert "+1.71 pp (reps +2.28 and +1.14)" in P["sprint4"]
    assert "19.95 tok/s in S1 (3B) and 0.0 in S5 (8B)" in P["handover"]
