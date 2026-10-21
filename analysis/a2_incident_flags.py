#!/usr/bin/env python3
"""Writes <A2 run dir>/incident_flags.csv from cell file times (journal 0023). Raw results.csv is never edited.
Cell time span = earliest file creation time to latest modification time in the cell directory (UTC).
  user_activity_contamination: cell span overlaps Arjun's reported Chrome window, 23:52:00-23:54:59 local (UTC+5:30) = 18:22:00-18:24:59 UTC on 2026-10-21.
  post_stall_first_cell: first cell after an idle gap > 120 s between consecutive cells (console QuickEdit stalls)."""
import csv
import datetime as dt
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "analysis"))
from w2_analysis import cells_overlapping  # noqa: E402

UTC = dt.timezone.utc
WIN = (dt.datetime(2026, 10, 21, 18, 22, 0, tzinfo=UTC).timestamp(), dt.datetime(2026, 10, 21, 18, 24, 59, tzinfo=UTC).timestamp())
GAP_S = 120


def spans(run_dir):
    out = {}
    for d in sorted((run_dir / "cells").iterdir()):
        fs = list(d.iterdir())
        out[d.name] = (min(f.stat().st_ctime for f in fs), max(f.stat().st_mtime for f in fs))
    return out


def main(run_dir):
    sp = spans(run_dir); rows = []
    for name in cells_overlapping(sp, *WIN):
        rows.append((name, "user_activity_contamination", "span overlaps reported Chrome window 18:22:00-18:24:59 UTC"))
    ordered = sorted(sp.items(), key=lambda kv: kv[1][0])
    for (n0, (a0, b0)), (n1, (a1, b1)) in zip(ordered, ordered[1:]):
        if a1 - b0 > GAP_S:
            rows.append((n1, "post_stall_first_cell", f"idle gap {a1 - b0:.0f} s after {n0}"))
    with open(run_dir / "incident_flags.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(["cell_dir", "flag", "detail"]); w.writerows(rows)
    for r in rows:
        print(*r, sep=" | ")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
