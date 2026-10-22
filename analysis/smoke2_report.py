"""Report for smoke 2 (data/w45_smoke/smoke2; DIAGNOSTIC, not a result; journal 0041): token durations, where tokens start relative to the fg arrivals, and whether the driver's own
fit test (now + tok_est + guard <= next arrival, tok_est = the driver's 0.9/0.1 EWMA of its token durations) could have admitted those starts.
Throughput is tokens / (t_last - t_first) from the driver's DONE line (the smoke's own bg_tok_s divides by the window and is wrong when the driver stops early at the context limit).
Writes data/w45_smoke/<run>_report.md.   Run: python analysis/smoke2_report.py [data/w45_smoke/smoke2]"""
import json
import re
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
D = (ROOT / sys.argv[1]) if len(sys.argv) > 1 else ROOT / "data" / "w45_smoke" / "smoke2"      # run directory with overrun.json
LONG_MS = 15.0          # a token this long was stretched by a frame sharing the GPU (clean tokens are about 10 ms)


def ewma_before(tok_ms):
    est, e = np.zeros(len(tok_ms)), None
    for k, t in enumerate(tok_ms):
        est[k] = 0.0 if e is None else e
        e = t if e is None else 0.9 * e + 0.1 * t
    return est


def q(x, p):
    return float(np.percentile(x, p)) if len(x) else float("nan")


def main():
    runs = json.loads((D / "overrun.json").read_text(encoding="utf-8"))
    L = ["# W4-5 hardware smoke 2: token durations and overrun (DIAGNOSTIC, not a registered result; journal 0041)", "",
         f"Source: {D.relative_to(ROOT).as_posix()}/overrun.json and overrun_raw_*.json. Long token = tok_ms > {LONG_MS:.0f} ms. 'fit test would admit' = the driver's rule now + EWMA estimate + guard <= next arrival, "
         "evaluated at the logged token start with the estimate reconstructed from the logged durations (the driver's own 0.9/0.1 EWMA).", "",
         "| run | cost ms | tokens | true tok/s (DONE line) | fg p50 / p99 ms | fg miss | long tokens | clean tok_ms p50 | long tok_ms p50 | start phase after arrival, clean p50 [p10, p90] | long p50 | fit test would admit |", "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in runs:
        raw = json.loads((D / f"overrun_raw_{r['label']}.json").read_text(encoding="utf-8"))
        te, tm, a = np.array(raw["tok_end"]), np.array(raw["tok_ms"]), np.array(raw["arrivals"])
        done = next(x for x in r["driver_output_tail"] if x.startswith("DONE"))
        n, t_first, t_last = (float(v) for v in re.findall(r"=([\d.]+)", done)[:3])
        tok_s = n / (t_last - t_first)
        lng = tm > LONG_MS
        if len(a):
            st = te - tm / 1000.0
            prev = np.maximum(np.searchsorted(a, st, side="right") - 1, 0)
            nxt = np.minimum(np.searchsorted(a, st, side="right"), len(a) - 1)
            ph, tn = (st - a[prev]) * 1000.0, (a[nxt] - st) * 1000.0
            guard = r["ctrl"][2] if r["ctrl"][0] >= 0.5 else None
            est = ewma_before(tm)
            admit = f"{100 * float(((est + (guard or 0.0)) <= tn)[1:].mean()):.1f}%" if guard is not None else "n/a (unaligned)"
            ph_s = f"{q(ph[~lng], 50):.2f} [{q(ph[~lng], 10):.2f}, {q(ph[~lng], 90):.2f}]" if (~lng).any() else "-"
            ph_l = f"{q(ph[lng], 50):.2f}" if lng.any() else "-"
        else:
            ph_s = ph_l = admit = "-"
        fg = "-" if not r["frames"] else f"{r['fg_p50_ms']:.2f} / {r['fg_p99_ms']:.2f}"
        L.append(f"| {r['label']} | {r.get('cost_ms', 'S0 (7)')} | {int(n)} | {tok_s:.1f} | {fg} | {r['fg_miss_frac']:.3f} | {100 * float(lng.mean()):.0f}% | {q(tm[~lng], 50):.2f} | {q(tm[lng], 50):.2f} | {ph_s} | {ph_l} | {admit} |")
    L += ["", "Reading: see journal 0041. The table is produced by analysis/smoke2_report.py from the files above; nothing in it is estimated."]
    (D.parent / f"{D.name}_report.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    main()
