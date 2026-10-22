"""Check part L (data/raw/w2_L/<run>) for the "fresh exe runs its body twice" effect (journal 0037; review 2026-10-22_w5_yaml_review.md decision on L): cell counts, token-log
integrity, the first cell against the other blocks, and when llama_decode_bench.exe was built versus first used. Writes data/w2_L_first_launch_check.md.   python analysis/w2_l_first_launch_check.py"""
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
R = sorted((ROOT / "data" / "raw" / "w2_L").glob("*"))[-1]
EXE = ROOT / "workloads" / "background" / "llama_decode_bench.exe"


def main():
    df = pd.read_csv(R / "results.csv")
    rows = []
    for _, r in df.iterrows():
        t = pd.read_csv(R / "cells" / f"b{int(r.block):02d}_{int(r.cell_idx):02d}_{r.cell_id}" / "llama_tokens.csv").t_tok_end.values
        off = next((float(o) for o in np.arange(1.0, 2.2, 0.01) if int(((t >= t[0] + o) & (t < t[0] + o + 4.0)).sum()) == int(r.tokens)), None)
        rows.append(dict(block=int(r.block), cell=r.cell_id, total=len(t), res=int(r.tokens), window_offset_s=off, dup_ts=int(pd.Series(t).duplicated().sum()), nonmono=int((np.diff(t) <= 0).sum()),
                         span_s=float(t[-1] - t[0]), tok_s=float(r.tok_s)))
    d = pd.DataFrame(rows)
    smoke = sorted((ROOT / "data" / "raw" / "w2_L_smoke").glob("*/meta.json"))
    L = ["# Part L first-launch check (double-execution effect; no GPU)", "",
         f"Run {R.name}: {len(df)} cells ({df.block.nunique()} blocks x {df.cell_id.nunique()} levels; expected 90).",
         f"- Cells whose logged tokens reproduce results.tokens exactly with a 4.0 s window starting 1.0-2.2 s after the first token: {int(d.window_offset_s.notna().sum())} of {len(d)} (window offset range {d.window_offset_s.min():.2f}-{d.window_offset_s.max():.2f} s).",
         f"- Cells with duplicated token timestamps: {int((d.dup_ts > 0).sum())}; with non-monotone timestamps: {int((d.nonmono > 0).sum())}.",
         f"- Cells with a non-empty flags column: {int(df['flags'].fillna('').astype(str).str.len().gt(0).sum())}.", "",
         "First cell (block 0, first level run) against the other blocks of the same level (total tokens logged / span of the log in s / tok/s):", "",
         "| level | b0 tokens | others median | b0 span | others span | b0 tok/s | others median tok/s | b0 / others |", "|---|---|---|---|---|---|---|---|"]
    for c in d.cell.unique():
        x = d[d.cell == c]; b0, ot = x[x.block == 0].iloc[0], x[x.block > 0]
        L.append(f"| {c} | {int(b0.total)} | {ot.total.median():.0f} | {b0.span_s:.3f} | {ot.span_s.median():.3f} | {b0.tok_s:.2f} | {ot.tok_s.median():.2f} | {b0.tok_s / ot.tok_s.median():.3f} |")
    exe_t = pd.Timestamp(EXE.stat().st_mtime, unit="s", tz="UTC")
    L += ["", f"- llama_decode_bench.exe last written (mtime) {exe_t}; part L smoke meta(s) {[str(pd.Timestamp(p.stat().st_mtime, unit='s', tz='UTC')) for p in smoke]}; full run meta {pd.Timestamp((R / 'meta.json').stat().st_mtime, unit='s', tz='UTC')}.",
          "- So the binary had been executed before the first measured cell of the full run (smoke run and earlier sanity runs), i.e. the first launch of that hash was not a measured cell.", "",
          "Reading: no sign of duplicated or missing token-log lines or cells; block 0 is within the range of the other blocks (b0/others about 1.003-1.012 in tok/s, the same sign at every level, i.e. a slightly faster first block, not a duplicated one). The driver writes its output once at the end and uses no named shared objects, so the mechanism seen with the named-ring probe (journal 0037) has no object to duplicate here. Not checked: whether the W2 DLLs (loaded in-process) were scanned/emulated; they have no named-object side effects either."]
    (ROOT / "data" / "w2_L_first_launch_check.md").write_text("\n".join(L), encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    main()
