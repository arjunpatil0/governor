"""Runs the quick-reference checklist of docs/WRITING_STYLE_GUIDE.md over docs/report/REPORT.md and writes docs/report/STYLE_CHECK.md: every automatic hit with its line, and the items that cannot be checked by a
script (paragraphs that describe without analysing, boilerplate conclusions) marked for reading. A hit that is kept has its reason in KEPT below. Exit code 1 if a hit has no reason.
   python docs/report/style_check.py"""
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
TEXT = (HERE / "REPORT.md").read_text(encoding="utf-8")
BODY = re.sub(r"<figure>.*?</figure>", "", TEXT, flags=re.S)                  # captions are checked separately below
PROSE = [(i, ln) for i, ln in enumerate(BODY.splitlines(), 1) if ln.strip() and not ln.startswith("|") and not ln.startswith("#")]

VOCAB = ["delve", "nuance", "tapestry", "multifaceted", "encompass", "realm", "landscape", "ecosystem", "robust", "holistic", "comprehensive", "meticulous", "pivotal", "groundbreaking", "transformative",
         "revolutionary", "leverage", "underscore", "foster", "navigate", "intricate", "shed light", "stands as", "serve as", "serves as", "it is worth noting", "it is important to", "in the realm of", "at its core",
         "in today's", "functions as", "operates as", "acts as", "paradigm", "profound", "far-reaching", "seamless", "crucial", "key ", "cutting-edge", "state-of-the-art", "novel"]
ATTRIB = ["many scholars", "experts believe", "critics", "some have suggested", "it is widely", "widely regarded", "has received"]
KEPT_SUB = [  # (substring of the match, reason it stays)
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
    lines = ["# Style check of docs/report/REPORT.md against docs/WRITING_STYLE_GUIDE.md (quick-reference checklist)", "",
             f"Generated by docs/report/style_check.py. Body about {words} words. Each row is an automatic hit; a hit that stays has its reason. Items 9 and 10 of the checklist need a reader and are listed at the end.", "",
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
              "9. Boilerplate conclusion (challenge 1, challenge 2, future direction 1, future direction 2): section 7 ties each limit to a finding of section 5 or 6 (work-unit size against slack, the missing no-hint comparison, the unanalysed estimate staleness, the synthetic foreground) and proposes one experiment that follows from the slack finding; there is no generic list of open questions.",
              "10. Paragraphs that describe without analysing: each results paragraph states a number and then what limits it (section 5), and section 6 states what each defect changed in the design.",
              "Register: first person singular throughout, no contractions. Terms are held fixed: slack hints, gated driver, governor, clock service, test harness, best fixed setting, fixed setting with idle rule, reactive controller, uncontrolled."]
    (HERE / "STYLE_CHECK.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"{len(h)} automatic hits, {unexplained} without a reason")
    for kind, m, i, txt in h:
        print(f"  [{kind}] {m!r} line {i}: {txt[:90]}")
    return 1 if unexplained else 0


if __name__ == "__main__":
    sys.exit(main())
