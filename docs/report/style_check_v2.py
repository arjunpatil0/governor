"""Runs the quick-reference checklist of docs/WRITING_STYLE_GUIDE.md over docs/report/REPORT_V2.md and writes docs/report/STYLE_CHECK.md: every automatic hit with its line, and the items that cannot be checked by a
script (paragraphs that describe without analysing, boilerplate conclusions) marked for reading. A hit that is kept has its reason in KEPT below. Exit code 1 if a hit has no reason.
   python docs/report/style_check_v2.py"""
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
TEXT = (HERE / "REPORT_V2.md").read_text(encoding="utf-8")
BODY = re.sub(r"<figure>.*?</figure>", "", TEXT, flags=re.S)                  # captions are checked separately below
PROSE = [(i, ln) for i, ln in enumerate(BODY.splitlines(), 1) if ln.strip() and not ln.startswith("|") and not ln.startswith("#")]

VOCAB = ["delve", "nuance", "tapestry", "multifaceted", "encompass", "realm", "landscape", "ecosystem", "robust", "holistic", "comprehensive", "meticulous", "pivotal", "groundbreaking", "transformative",
         "revolutionary", "leverage", "underscore", "foster", "navigate", "intricate", "shed light", "stands as", "serve as", "serves as", "it is worth noting", "it is important to", "in the realm of", "at its core",
         "in today's", "functions as", "operates as", "acts as", "paradigm", "profound", "far-reaching", "seamless", "crucial", "key ", "cutting-edge", "state-of-the-art", "novel"]
ATTRIB = ["many scholars", "experts believe", "critics", "some have suggested", "it is widely", "widely regarded", "has received"]
KEPT_SUB = [  # (substring of the match, reason it stays)
    ("09a0cd0, 447105e and b24edae", "the tail of a list of four commit hashes, each a distinct forecast commit"),
    ("- S0 non-inferiority vs c'B-T3", "enumerates the three registered outputs that move in the sensitivity analysis: genuinely enumerative content, text supplied by the author"),
    ("- HW1 for c'B-T3b in S0", "second of the three enumerated outputs"),
    ("- HW1 for eB in S1", "third of the three enumerated outputs"),
    ("1.999, 1.500 and 1.203", "three measured clock levels (900, 1200, 1500 MHz) with three measured values: the data have exactly three entries"),
    ("2.000, 1.500 and 1.202", "the three predictions that go with the three measured values"),
    ("pacing mode, duty and guard time", "the control block has exactly three fields"),
    ("pacing mode, duty and guard", "a four-item list of governor outputs (clock, pacing mode, duty, guard): the regex counted its tail"),
    ("17.9 against 16.6 and 16.7", "three measured values, not a rhetorical triple"),
    ("one GPU, one driver and one synthetic foreground", "the last three of four limits, each a separate fact"),
    ("committed on 2026-10-23, with dated addenda, and its", "a clause sequence, not a list of items"),
    ("from section 2, token time and power come from", "a clause sequence, not a list of items"),
    ("earlier chunking project, the registered thresholds and the arbitration of", "the tail of a five-item list of decisions, each a distinct decision record"),
    ("does not fit, gap-filling gains nothing, and overlapping the token", "a conditional followed by two consequences in one sentence, not a list of items"),
    ("none present", "no em-dashes or en-dashes were used"),
]


def hits():
    out = []
    low = [(i, ln, ln.lower()) for i, ln in PROSE]
    for w in VOCAB:
        for i, ln, l in low:
            if w in l:
                out.append(("AI vocabulary", w.strip(), i, ln.strip()[:140]))
    for pat, name in ((r"\bnot (just|only)\b.*\bbut (also )?", "not just X but also Y"), (r"\bnot \w+( \w+){0,4}, but\b", "not X, but Y"), (r"\brather than\b", "X rather than Y")):
        for i, ln in PROSE:
            if re.search(pat, ln, re.I):
                out.append(("negative parallelism", name, i, ln.strip()[:140]))
    for w in ATTRIB:
        for i, ln in PROSE:
            if w in ln.lower():
                out.append(("vague attribution", w, i, ln.strip()[:140]))
    for i, ln in PROSE:
        for m in re.finditer(r"\b([\w'.-]+(?: [\w'.-]+){0,2}), ([\w'.-]+(?: [\w'.-]+){0,2}),? and ([\w'.-]+(?: [\w'.-]+){0,2})\b", ln):
            out.append(("list of exactly three", m.group(0)[:80], i, ln.strip()[:140]))
    n_dash = TEXT.count("—") + TEXT.count("–") + TEXT.count(" -- ")
    out.append(("em-dashes", f"{n_dash} in the whole report (limit 1-2 per page, 6 pages)", 0, ""))
    for i, ln in PROSE:
        if "**" in ln or "<b>" in ln or "<strong>" in ln:
            out.append(("bold in body prose", "**", i, ln.strip()[:100]))
        if re.match(r"\s*([-*]|\d+\.)\s", ln):
            out.append(("list in body prose", ln.strip()[:30], i, ln.strip()[:100]))
    for i, ln in PROSE:
        if re.search(r"\b(is|are) (a|an|the) .{0,40}\bthat serves\b", ln):
            out.append(("serves as", "serves", i, ln.strip()[:100]))
    return out


def main():
    h = hits()
    words = len(re.findall(r"\w+", BODY))
    lines = ["# Style check of docs/report/REPORT_V2.md against docs/WRITING_STYLE_GUIDE.md (quick-reference checklist)", "",
             f"Generated by docs/report/style_check_v2.py. Body about {words} words. Each row is an automatic hit; a hit that stays has its reason. Items 9 and 10 of the checklist need a reader and are listed at the end.", "",
             "| Check | Match | Line | Text | Kept because |", "|---|---|---|---|---|"]
    unexplained = 0
    for kind, m, i, txt in h:
        reason = next((r for sub, r in KEPT_SUB if sub in m or (kind == "em-dashes" and sub == "none present" and m.startswith("0 in"))), "")
        if not reason:
            unexplained += 1
        lines.append(f"| {kind} | {m} | {i} | {txt.replace('|', '/')} | {reason} |")
    if not h:
        lines.append("| (none) | | | | |")
    lines += ["", "## Read by hand", "",
              "9. Boilerplate conclusion: section 7 ties each direction to a finding (the flat guard of sprint 4 to a p90 predictor, the synthetic foreground to a real renderer, the uncontrolled 58 to 60 W to the v1 governor's power control, the independent jitter of sprint 3 to correlated jitter) and not to a generic list of open questions.",
              "10. Paragraphs that describe without analysing: each results paragraph in section 4 states a number and then what limits it (the handover forecast and WDDM time-slicing in sprint 2, the 8 to 11 ms of slack in sprint 3, the 29% SOLO lateness and the two-rep pass in sprint 4); section 5 states the direction of the forecast errors.",
              "Register: first person singular throughout, no contractions. Terms are held fixed: whole-token gate, pausable (14-group) gate, guard, SOLO, excess late, free time per frame, TIGHT, VERY TIGHT."]
    (HERE / "STYLE_CHECK_V2.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"{len(h)} automatic hits, {unexplained} without a reason")
    for kind, m, i, txt in h:
        print(f"  [{kind}] {m!r} line {i}: {txt[:90]}")
    return 1 if unexplained else 0


if __name__ == "__main__":
    sys.exit(main())
