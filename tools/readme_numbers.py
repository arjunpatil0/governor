"""Regenerates the numbers block of README.md from the logged v2 data and checks the README against it.
   python tools/readme_numbers.py                  print the markdown block (tables), the generated prose sentences and the source of every number
   python tools/readme_numbers.py --check README.md   exit 1 if the block between <!-- numbers:begin --> and <!-- numbers:end --> differs,
                                                      or if a generated prose sentence (see prose()) is missing from the README
Reads only data/v2/s1_pause/*, data/v2/s2/summary.json, data/v2/s2/*Z_exp1_handover/G1_gate_rep*/result.json,
data/v2/s3/*/summary.json (+ the SOLO frames.npz of the moderate level for the free time) and data/v2/s4/*/summary.json.
Free time per frame = 16.67 ms minus the SOLO median frame time (launch to completion, after a 5 s warm-up), as in tools/v2_figure.py."""
import argparse
import csv
import json
import re
import statistics as st
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PERIOD_MS = 1000.0 / 60.0
WARM_S = 5.0
BEGIN, END = "<!-- numbers:begin -->", "<!-- numbers:end -->"
S1_3B = ROOT / "data/v2/s1_pause/20261107T213459Z"
S1_8B = ROOT / "data/v2/s1_pause/20261107T220932Z"
S2 = ROOT / "data/v2/s2/summary.json"
S3 = next((ROOT / "data/v2/s3").glob("*_jitter"))
S4 = next((ROOT / "data/v2/s4").glob("*_slack"))


def rel(p):
    return Path(p).resolve().relative_to(ROOT).as_posix()


def load(p):
    return json.loads(Path(p).read_text())


def token_ids_identical(d, cfg="G14"):
    ids = []
    for f in sorted(Path(d).glob(f"{cfg}_rep*_tokens.csv")):
        with open(f, newline="", encoding="utf-8") as fh:
            ids.append([r["token_id"] for r in csv.DictReader(fh) if r["warm"] == "0"])
    return len(ids) > 1 and all(x == ids[0] for x in ids)


def solo_median_ms(cells):
    import numpy as np
    v = []
    for c in cells:
        r = load(c / "result.json")
        f = np.load(c / "frames.npz")
        keep = f["t_sched"] >= r["t0"] + WARM_S
        v.append((f["t_end"][keep] - f["t_start"][keep]) * 1e3)
    return float(np.median(np.concatenate(v)))


def compute():
    n = {}   # name -> (value, source)
    s2 = load(S2)
    for arm in ("G1_free", "G14_free", "G1_gate", "G14_gate"):
        e = s2["exp1"][arm]
        n[f"exp1.{arm}.tok"] = (e["tok_s_median"], f"{rel(S2)} exp1.{arm}.tok_s_median")
        n[f"exp1.{arm}.late"] = (e["late_pct_median"], f"{rel(S2)} exp1.{arm}.late_pct_median")
    g1g = sorted(S2.parent.glob("*Z_exp1_handover/G1_gate_rep*/result.json"))
    n["exp1.G1_gate.bg_tokens"] = (sum(load(f)["bg_tokens"] for f in g1g), f"sum of bg_tokens over {len(g1g)} G1_gate reps in {rel(S2.parent)}/*Z_exp1_handover/")
    all_late = []
    for sc in ("S1", "S5"):
        for arm in ("whole", "g14"):
            e = s2["exp3"][sc][arm]
            key = f"exp3.{sc}.{arm}"
            n[key + ".tok"] = (st.median(e["tok"]), f"{rel(S2)} exp3.{sc}.{arm}.tok (median of reps)")
            n[key + ".tok_reps"] = (list(e["tok"]), f"{rel(S2)} exp3.{sc}.{arm}.tok")
            n[key + ".late"] = (max(e["late"]), f"{rel(S2)} exp3.{sc}.{arm}.late (max over reps)")
            n[key + ".power"] = (st.median(e["power"]), f"{rel(S2)} exp3.{sc}.{arm}.power (median of reps)")
            all_late += e["late"]
    n["exp3.cells"] = (len(all_late), f"count of scene x arm x rep in {rel(S2)} exp3")
    n["exp3.reps"] = (len(s2["exp3"]["S1"]["whole"]["tok"]), f"{rel(S2)} exp3.S1.whole.tok length")
    n["exp3.max_late"] = (max(all_late), f"{rel(S2)} exp3 max late over all cells")
    n["s1.8b.G14.overhead"] = (s2["exp2"]["G14"]["overhead_pct"], f"{rel(S2)} exp2.G14.overhead_pct (8B, from {rel(S1_8B)})")
    n["s1.8b.G14.longest_ms"] = (s2["exp2"]["G14"]["longest_group_ms"], f"{rel(S2)} exp2.G14.longest_group_ms")
    n["s1.8b.G14.longest_p99_ms"] = (s2["exp2"]["G14"]["longest_group_p99_ms"], f"{rel(S2)} exp2.G14.longest_group_p99_ms")
    n["s1.8b.identical"] = (token_ids_identical(S1_8B), f"{rel(S1_8B)}/G14_rep*_tokens.csv token_id")
    s1 = load(S1_3B / "summary.json")["results"]["G14"]
    n["s1.3b.G14.overhead"] = (s1["overhead_pct"], f"{rel(S1_3B)}/summary.json results.G14.overhead_pct")
    n["s1.3b.G14.longest_ms"] = (s1["longest_group_ms_median"], f"{rel(S1_3B)}/summary.json results.G14.longest_group_ms_median")
    n["s1.3b.identical"] = (s1["token_ids_identical_across_reps"], f"{rel(S1_3B)}/summary.json results.G14.token_ids_identical_across_reps")
    t3 = load(S3 / "summary.json")["table"]
    free3 = PERIOD_MS - solo_median_ms(sorted(S3.glob("moderate_solo_rep*")))
    n["ladder.9.free"] = (free3, f"{rel(S3)}/moderate_solo_rep*/frames.npz (16.67 - SOLO median frame time)")
    n["ladder.9.whole"] = (t3["moderate|3b_whole"]["tok"], f"{rel(S3)}/summary.json table['moderate|3b_whole'].tok")
    n["ladder.9.g14"] = (t3["moderate|3b_g14"]["tok"], f"{rel(S3)}/summary.json table['moderate|3b_g14'].tok")
    g9 = t3["moderate|3b_g14"]
    n["ladder.9.excess"] = (g9["excess"], f"{rel(S3)}/summary.json table['moderate|3b_g14'].excess")
    n["ladder.9.excess_reps"] = ([r["excess"] for r in g9["rows"]], f"{rel(S3)}/summary.json table['moderate|3b_g14'].rows[*].excess")
    n["ladder.9.solo_late"] = (t3["moderate|solo"]["late"], f"{rel(S3)}/summary.json table['moderate|solo'].late")
    t4 = load(S4 / "summary.json")["table"]
    for lv, tag in (("tight", "4"), ("very_tight", "2")):
        w, g, s = t4[f"{lv}|3b_whole"], t4[f"{lv}|3b_g14_m0"], t4[f"{lv}|solo"]
        src = f"{rel(S4)}/summary.json table['{lv}|..']"
        n[f"ladder.{tag}.free"] = (PERIOD_MS - s["solo_med_ms"], f"{src}.solo_med_ms (16.67 minus)")
        n[f"ladder.{tag}.whole"] = (w["tok"], f"{src} 3b_whole.tok")
        n[f"ladder.{tag}.g14"] = (g["tok"], f"{src} 3b_g14_m0.tok")
        n[f"ladder.{tag}.excess"] = (g["excess"], f"{src} 3b_g14_m0.excess")
        n[f"ladder.{tag}.excess_reps"] = ([r["excess"] for r in g["rows"]], f"{src} 3b_g14_m0.rows[*].excess")
        n[f"ladder.{tag}.solo_late"] = (s["late"], f"{src} solo.late")
    return n


def block(n):
    v = lambda k: n[k][0]
    bg = f"{v('exp1.G1_gate.bg_tokens'):.0f}"
    L = [BEGIN, "",
         "Handover-latency cells, Llama-3.2-3B, 60 s, scene S0 (constant 7 ms frame), a marker kernel before every frame, 2 reps, no SOLO baseline, 1800 MHz lock, 60 fps (sprint 2, experiment 1). Late-frame rates here are not comparable with the end-to-end cells below. There are four rows: the two ungated arms (G1 is a whole token, G14 is 14 groups) and the two gated arms.", "",
         "| decode arm | tok/s | late frames |", "|---|---|---|"]
    for arm, name in (("G1_free", "ungated, whole token (G1)"), ("G14_free", "ungated, 14 groups (G14)"), ("G1_gate", "whole-token gate"), ("G14_gate", "group gate (14 groups)")):
        L.append(f"| {name} | {v(f'exp1.{arm}.tok'):.1f} | {v(f'exp1.{arm}.late'):.2f}% |")
    L += ["", f"The {v('exp1.G1_gate.late'):.2f}% for the whole-token gate is the foreground's own lateness, because that arm decoded {bg} tokens (bg_tokens={bg}).", "",
          f"End-to-end cells, sprint 2 (experiment 3): scenes S1 and S5 of the v1 evaluation, {v('exp3.reps'):.0f} reps of 60 s per cell, 1800 MHz lock, guard 0. Throughput is the median of the reps (each rep in brackets), power the median of the reps:", "",
          "| scene, model | gate | tok/s | late frames | power |", "|---|---|---|---|---|"]
    for sc, mdl in (("S1", "3B"), ("S5", "8B")):
        for arm, name in (("whole", "whole-token gate"), ("g14", "14-group gate")):
            k = f"exp3.{sc}.{arm}"
            reps = ", ".join(f"{x:.2f}" for x in v(k + ".tok_reps"))
            L.append(f"| {sc}, {mdl} | {name} | {v(k + '.tok'):.2f} [{reps}] | {v(k + '.late'):.2f}% | {v(k + '.power'):.1f} W |")
    L += ["", "Decode throughput against free GPU time per frame, Llama-3.2-3B, moderate frame-cost jitter (lognormal frame cost with a coefficient of variation of 0.15, submit time within plus or minus 1 ms, 5% unannounced bursts), gate guard 0. Free time is 16.67 ms minus the median frame time of the foreground alone. The 9.7 ms row is sprint 3 (median over 3 reps, foreground S1); the 4.0 and 2.0 ms rows are sprint 4 (mean over 2 reps, a calibrated constant-cost S0 foreground). The foregrounds differ, so the rows show a trend, not one measured curve:", "",
          "| free ms per frame | whole-token gate, tok/s | 14-group gate, tok/s | late frames added by 14-group decode, pp: aggregate (each rep) | foreground alone misses |",
          "|---|---|---|---|---|"]
    for tag in ("9", "4", "2"):
        reps = ", ".join(f"{x:+.2f}" for x in v(f"ladder.{tag}.excess_reps"))
        ex = f"{v(f'ladder.{tag}.excess'):+.2f} ({reps})"
        sl = f"{v(f'ladder.{tag}.solo_late'):.1f}%"
        L.append(f"| {v(f'ladder.{tag}.free'):.1f} | {v(f'ladder.{tag}.whole'):.1f} | {v(f'ladder.{tag}.g14'):.1f} | {ex} | {sl} |")
    L += ["", "Cost of pausing at 14 groups against one piece per token, no foreground, 1500 MHz (sprint 1; the 8B longest piece is from the sprint 2 summary):", "",
          "| model | overhead per token | longest uninterruptible piece | output |", "|---|---|---|---|",
          f"| Llama-3.2-3B | {v('s1.3b.G14.overhead'):.1f}% | {v('s1.3b.G14.longest_ms'):.2f} ms | {'token-identical' if v('s1.3b.identical') else 'DIFFERS'} |",
          f"| Llama-3.1-8B | {v('s1.8b.G14.overhead'):.1f}% | {v('s1.8b.G14.longest_ms'):.2f} ms (p99 {v('s1.8b.G14.longest_p99_ms'):.2f}) | {'token-identical' if v('s1.8b.identical') else 'DIFFERS'} |",
          "", END]
    return "\n".join(L)


def prose(n):
    """Sentences with numbers that the README repeats outside the generated block; --check requires each one verbatim."""
    v = lambda k: n[k][0]
    cells = f"{v('exp3.cells'):.0f}"
    if v("exp3.max_late") == 0:
        late = f"{v('exp3.max_late'):.2f}% late frames in all {cells} cells"
    else:
        late = f"at most {v('exp3.max_late'):.2f}% late frames in the {cells} cells"
    r4, r2 = v("ladder.4.excess_reps"), v("ladder.2.excess_reps")
    P = {}
    P["lead"] = (f"On one RTX 4070 Laptop GPU, with a synthetic CUDA foreground at 60 fps and the clock locked at 1800 MHz, gating llama.cpp between layer groups lets decode use gaps shorter than a token. "
                 f"At 4 ms of free GPU time per frame the 3B produced {v('ladder.4.g14'):.1f} tok/s against {v('ladder.4.whole'):.0f} for whole-token gating, with no detectable added lateness; "
                 f"at 2 ms it produced {v('ladder.2.g14'):.1f} tok/s at {v('ladder.2.excess'):+.1f} pp late frames. "
                 f"Splitting a token into 14 groups costs {v('s1.8b.G14.overhead'):.1f}% (8B) to {v('s1.3b.G14.overhead'):.1f}% (3B) per token, measured without a foreground.")
    P["pause"] = (f"Pausing makes a token {v('s1.8b.G14.overhead'):.1f}% (Llama-3.1-8B) to {v('s1.3b.G14.overhead'):.1f}% (Llama-3.2-3B) slower at 14 groups, with token-identical output. "
                  f"The longest uninterruptible piece is {v('s1.3b.G14.longest_ms'):.2f} ms for the 3B and {v('s1.8b.G14.longest_ms'):.2f} ms for the 8B (p99 {v('s1.8b.G14.longest_p99_ms'):.2f} ms). "
                  f"The 8B piece is above the 2.5 ms group limit of sprint 1 (the 3B meets it), and at about 2 ms of free time per frame it is longer than the whole gap, which is why the 8B collapses there.")
    P["handover"] = (f"With the gate on, the whole-token gate gave {v('exp3.S1.whole.tok'):.2f} tok/s in S1 (3B) and {v('exp3.S5.whole.tok'):.1f} in S5 (8B); "
                     f"the 14-group gate gave {v('exp3.S1.g14.tok'):.1f} and {v('exp3.S5.g14.tok'):.1f}, with {late} ({v('exp3.reps'):.0f} reps). "
                     f"Without a gate every frame was late in the handover cells (S0), at {v('exp1.G1_free.tok'):.1f} tok/s for whole tokens and {v('exp1.G14_free.tok'):.1f} for 14 groups.")
    P["ladder"] = (f"As the free time per frame shrinks from {v('ladder.9.free'):.1f} ms to {v('ladder.2.free'):.1f} ms, the 14-group gate keeps a share of the throughput "
                   f"({v('ladder.9.g14'):.1f}, {v('ladder.4.g14'):.1f} and {v('ladder.2.g14'):.1f} tok/s), while the whole-token gate gives {v('ladder.9.whole'):.1f} tok/s at {v('ladder.9.free'):.1f} ms and {v('ladder.4.whole'):.1f} at {v('ladder.4.free'):.1f} ms and below.")
    P["sprint4"] = (f"At 4 ms free the excess over the foreground alone is {v('ladder.4.excess'):+.2f} pp (reps {r4[0]:+.2f} and {r4[1]:+.2f}), inside the +/-0.3 pp noise band of this design (REPORT_V2.md), so no added lateness was detected. "
                    f"At 2 ms free it is {v('ladder.2.excess'):+.2f} pp (reps {r2[0]:+.2f} and {r2[1]:+.2f}); rep 1 is above the sprint's 2 pp pass limit and the pass rests on the mean of two reps. "
                    f"The foreground alone misses {v('ladder.4.solo_late'):.1f}% and {v('ladder.2.solo_late'):.1f}% of its own frames at those levels.")
    return P


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--check", metavar="README")
    a = ap.parse_args()
    n = compute()
    text = block(n)
    if a.check:
        s = Path(a.check).read_text(encoding="utf-8").replace("\r\n", "\n")
        m = re.search(re.escape(BEGIN) + r".*?" + re.escape(END), s, re.S)
        if not m:
            print("no numbers block in", a.check)
            return 1
        if m.group(0) != text:
            print("README numbers block differs from the regenerated text; regenerate with: python tools/readme_numbers.py")
            return 1
        flat = " ".join(s.split())
        missing = [k for k, t in prose(n).items() if " ".join(t.split()) not in flat]
        if missing:
            print("README is missing generated prose sentences:", ", ".join(missing), "; print them with: python tools/readme_numbers.py")
            return 1
        print("README numbers block and prose numbers match the data")
        return 0
    print(text)
    print("\nProse sentences (must appear verbatim in the README):")
    for k, t in prose(n).items():
        print(f"  [{k}] {t}")
    print("\nSources:")
    for k, (val, src) in n.items():
        print(f"  {k} = {val if not isinstance(val, float) else round(val, 4)}  <- {src}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
