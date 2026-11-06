"""Vector figures of docs/report/REPORT.md. Every plotted number is read from a committed file:
  characterisation.svg : data/w2_L_results.md (throughput and board power by SM clock level, llama.cpp Llama-3.2-3B Q4_K_M)
  slack_cliff.svg      : data/w45_smoke/smoke3_report.md (aligned runs at three frame costs), data/w5b/eval/block04/cells/ev04_S0_gB_60/cell.json (the evaluation S0 cell), and the rule of
                         docs/SPEC_FRAME_SLACK_HINTS.md section 6.3 with the clean 3B token of 10.1 ms (journal 0042)
  architecture.svg     : drawn here (no data)
   python docs/report/make_figures.py"""
import json
import re
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent / "figs"
plt.rcParams.update({"svg.fonttype": "none", "font.family": "sans-serif", "font.sans-serif": ["Arial", "Segoe UI", "DejaVu Sans"], "font.size": 9, "axes.spines.top": False, "axes.spines.right": False})
INK, MUTED, ACCENT, WARN = "#1b2630", "#6b7a86", "#0e7469", "#b4472f"
PERIOD_MS, TOKEN_MS = 1000.0 / 60.0, 10.1


def clock_sweep():
    rows = []
    for ln in (ROOT / "data" / "w2_L_results.md").read_text(encoding="utf-8").splitlines():
        m = re.match(r"\s*(\d+|unlocked)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s*$", ln)
        if m:
            rows.append((m.group(1), float(m.group(2)), float(m.group(3))))
    assert len(rows) == 9, rows
    return rows


def characterisation():
    rows = clock_sweep()
    x = [int(r[0]) if r[0] != "unlocked" else 2460 for r in rows]
    fig, ax = plt.subplots(figsize=(6.2, 2.5))
    ax2 = ax.twinx()
    ax2.spines["right"].set_visible(True)
    ax.plot(x, [r[1] for r in rows], "o-", color=ACCENT, lw=1.6, ms=4, label="throughput (tok/s)")
    ax2.plot(x, [r[2] for r in rows], "s--", color=WARN, lw=1.4, ms=3.5, label="board power (W)")
    ax.set_xlabel("SM clock lock (MHz); the last point is the unlocked clock, drawn at 2460")
    ax.set_ylabel("decode throughput (tok/s)", color=ACCENT)
    ax2.set_ylabel("board power (W)", color=WARN)
    ax.set_ylim(50, 110); ax2.set_ylim(30, 100)
    ax.axvline(1500, color=MUTED, lw=0.8, ls=":")
    ax.annotate("1500 MHz: 97.25 tok/s at 56.3 W", (1500, 97.25), (780, 104), fontsize=8, color=INK, arrowprops=dict(arrowstyle="-", color=MUTED, lw=0.7))
    h1, l1 = ax.get_legend_handles_labels(); h2, l2 = ax2.get_legend_handles_labels()
    ax.legend(h1 + h2, l1 + l2, loc="lower right", frameon=False, fontsize=8)
    fig.tight_layout()
    fig.savefig(OUT / "characterisation.svg")
    plt.close(fig)


def smoke3_points():
    pts = []
    for ln in (ROOT / "data" / "w45_smoke" / "smoke3_report.md").read_text(encoding="utf-8").splitlines():
        if ln.startswith("| aligned_g0_d1_cost4") or ln.startswith("| aligned_g0_d1_cost7") or ln.startswith("| aligned_g1_d1_cost9"):
            c = [x.strip() for x in ln.strip("|").split("|")]
            pts.append((float(c[5].split("/")[0]), float(c[3])))                     # fg p50 ms, tok/s in the measured window
    assert len(pts) == 3, pts
    return pts


def slack_cliff():
    pts = smoke3_points()
    cell = json.loads((ROOT / "data" / "w5b" / "eval" / "block04" / "cells" / "ev04_S0_gB_60" / "cell.json").read_text(encoding="utf-8"))["metrics"]
    s0 = (cell["fg_p50_ms"], cell["tok_s"])
    thr = PERIOD_MS - TOKEN_MS
    fig, ax = plt.subplots(figsize=(6.2, 2.9))
    ax.step([2.5, thr, thr, 9.0], [60, 60, 0, 0], where="post", color=MUTED, lw=1.6, label="rule: one token per frame, only while the frame leaves 10.1 ms of slack")
    ax.plot(*zip(*pts), "o", color=ACCENT, ms=6, label="measured, smoke 3 (aligned pacing, three frame costs)")
    ax.plot(*s0, "D", color=WARN, ms=6, label="measured, evaluation S0 (best fixed setting, cell ev04_S0_gB_60)")
    ax.axvline(thr, color=MUTED, lw=0.8, ls=":")
    ax.text(thr - 0.08, 30, f"slack = token\n{thr:.2f} ms", ha="right", fontsize=8, color=INK)
    ax.set_xlim(2.5, 9.0); ax.set_ylim(-4, 70)
    ax.set_xlabel("frame time alone, median (ms); the deadline is 16.67 ms")
    ax.set_ylabel("background tok/s")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.27), frameon=False, fontsize=7.5)
    fig.tight_layout()
    fig.savefig(OUT / "slack_cliff.svg")
    plt.close(fig)


def box(parts, x, y, w, h, title, sub="", fill="#f4f6f7", bold=False):
    parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="5" fill="{fill}" stroke="#1b2630" stroke-width="1.1"/>')
    parts.append(f'<text x="{x + w / 2}" y="{y + 18}" text-anchor="middle" font-size="11.5" font-weight="{600 if bold else 500}" fill="#1b2630">{title}</text>')
    for i, line in enumerate(sub.split("\n") if sub else []):
        parts.append(f'<text x="{x + w / 2}" y="{y + 34 + 13 * i}" text-anchor="middle" font-size="9.3" fill="#4a5a66">{line}</text>')


def arrow(parts, x1, y1, x2, y2, label="", dash=False, lx=None, ly=None, anchor="middle"):
    d = ' stroke-dasharray="4 3"' if dash else ""
    parts.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="#1b2630" stroke-width="1.1"{d} marker-end="url(#a)"/>')
    if label:
        parts.append(f'<text x="{lx if lx is not None else (x1 + x2) / 2}" y="{ly if ly is not None else (y1 + y2) / 2 - 4}" text-anchor="{anchor}" font-size="9" fill="#0e7469">{label}</text>')


def architecture():
    p = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 640 330" font-family="Arial, Segoe UI, sans-serif">',
         '<defs><marker id="a" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8 z" fill="#1b2630"/></marker></defs>']
    box(p, 10, 12, 190, 60, "Foreground app", "60 Hz frame loop\nframe ring: arrival, start, end", bold=True)
    box(p, 225, 12, 190, 60, "Slack hints", "40-byte seqlock record: busy flag,\nnext deadline, update time", fill="#e1f0ed", bold=True)
    box(p, 440, 12, 190, 60, "Gated llama.cpp driver", "starts a token only if it fits;\nclean-token estimate, token ring", bold=True)
    arrow(p, 200, 42, 225, 42)
    arrow(p, 415, 42, 440, 42)
    box(p, 225, 128, 190, 66, "Governor, 10 Hz", "grey-box model, online calibration,\nsafety margin, power headroom,\npacing-mode hysteresis, fail-safe", fill="#e1f0ed", bold=True)
    arrow(p, 105, 72, 270, 128, "frame latencies", lx=118, ly=108, anchor="start")
    arrow(p, 535, 72, 380, 128, "token durations", lx=522, ly=108, anchor="end")
    arrow(p, 320, 128, 535, 76, "control block: mode, duty, guard", lx=470, ly=150, anchor="middle", dash=True)
    box(p, 10, 128, 190, 66, "NVML sampled power", "250 Hz power and SM clock;\nthe energy counter is read twice\nper 60 s window, never in the loop")
    arrow(p, 200, 161, 225, 161)
    box(p, 225, 248, 190, 62, "Clock service (elevated)", "named pipe; allowlisted lock values;\nrate limit 1 s; watchdog 3 s", fill="#fbeee9", bold=True)
    arrow(p, 320, 194, 320, 248, "lock / reset SM clock", lx=330, ly=224, anchor="start")
    box(p, 440, 248, 190, 62, "GPU (RTX 4070 Laptop, WDDM)", "time-sliced between the two processes")
    arrow(p, 415, 279, 440, 279)
    p.append('<text x="10" y="236" font-size="9" fill="#4a5a66">test harness: pre-registered cell lists, preflight,</text>')
    p.append('<text x="10" y="249" font-size="9" fill="#4a5a66">per-cell integrity checks, session integrity report</text>')
    p.append("</svg>")
    (OUT / "architecture.svg").write_text("\n".join(p), encoding="utf-8")


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    characterisation(); slack_cliff(); architecture()
    print("wrote", sorted(f.name for f in OUT.glob("*.svg")))
