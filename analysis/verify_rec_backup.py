"""Verify every file listed in a REC_MANIFEST.sha256 against a backup copy of the run folder (SHA-256, streamed).
Usage (PowerShell, from C:\\Users\\arjun\\governor):
  python analysis/verify_rec_backup.py --backup C:\\Users\\arjun\\OneDrive\\governor_backup\\w2_G\\20261022T062433Z
Exit code 0 only if every manifest entry exists in the backup with the same hash."""
import argparse
import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "data" / "raw" / "w2_G" / "20261022T062433Z" / "REC_MANIFEST.sha256"


def sha256(path, chunk=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                return h.hexdigest()
            h.update(b)


def verify(manifest, backup_run_dir):
    ok, missing, mismatch = 0, [], []
    for line in Path(manifest).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        want, rel = line.split(" *", 1)
        p = Path(backup_run_dir) / rel
        if not p.exists():
            missing.append(rel)
        elif sha256(p) != want.lower():
            mismatch.append(rel)
        else:
            ok += 1
    return dict(ok=ok, missing=missing, mismatch=mismatch)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--backup", required=True, help="the backup copy of the run folder (contains cells/)")
    ap.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    a = ap.parse_args()
    r = verify(a.manifest, a.backup)
    total = r["ok"] + len(r["missing"]) + len(r["mismatch"])
    print(f"manifest {a.manifest}\nbackup   {a.backup}\nOK {r['ok']} / {total}; missing {len(r['missing'])}; hash mismatch {len(r['mismatch'])}")
    for rel in r["missing"][:20]:
        print("MISSING ", rel)
    for rel in r["mismatch"][:20]:
        print("MISMATCH", rel)
    sys.exit(0 if r["ok"] == total and total > 0 else 1)


if __name__ == "__main__":
    main()
