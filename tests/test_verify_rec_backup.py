"""analysis/verify_rec_backup.py: check every file listed in a REC_MANIFEST.sha256 against a backup copy of the run folder.
Called by pytest and from the command line; requested by Arjun: "write a small script that verifies every rec file in my OneDrive backup against REC_MANIFEST.sha256"."""
import hashlib

from verify_rec_backup import verify


def _setup(tmp_path):
    run = tmp_path / "src" / "run"
    bak = tmp_path / "bak" / "run"
    for d in (run, bak):
        (d / "cells" / "c0").mkdir(parents=True)
    files = {"cells/c0/a_rec.npz": b"alpha", "cells/c0/b_rec.npz": b"beta"}
    lines = []
    for rel, data in files.items():
        (bak / rel).write_bytes(data)
        lines.append(f"{hashlib.sha256(data).hexdigest()} *{rel}")
    man = run / "REC_MANIFEST.sha256"
    man.write_text("\n".join(lines) + "\n")
    return man, bak


def test_all_files_match(tmp_path):
    man, bak = _setup(tmp_path)
    r = verify(man, bak)
    assert r["ok"] == 2 and not r["missing"] and not r["mismatch"]


def test_reports_missing_and_corrupt_files(tmp_path):
    man, bak = _setup(tmp_path)
    (bak / "cells/c0/a_rec.npz").write_bytes(b"corrupt")
    (bak / "cells/c0/b_rec.npz").unlink()
    r = verify(man, bak)
    assert r["ok"] == 0 and r["mismatch"] == ["cells/c0/a_rec.npz"] and r["missing"] == ["cells/c0/b_rec.npz"]
