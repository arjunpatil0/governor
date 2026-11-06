"""Builds docs/report/REPORT.pdf from docs/report/REPORT.md. Pandoc and LaTeX are not installed on this machine, so the Markdown is converted to a print-styled HTML page (python-markdown) and rendered to PDF with the
installed Chrome (headless print-to-pdf). Figures come from docs/report/figs (python docs/report/make_figures.py) and data/w5b/eval_miss_vs_toks.png (analysis/w5b_descriptive.py).
   python docs/report/build_report.py        writes REPORT.html (intermediate) and REPORT.pdf and prints the page count"""
import re
import shutil
import subprocess
import sys
from pathlib import Path

import markdown

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
CHROME = [p for p in ("C:/Program Files/Google/Chrome/Application/chrome.exe", "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe") if Path(p).exists()]

CSS = """
@page { size: A4; margin: 15mm 17mm 16mm 17mm }
html { font-size: 9.6pt }
body { font-family: Georgia, 'Times New Roman', serif; line-height: 1.36; color: #15202a; margin: 0; text-align: left; hyphens: auto }
h1 { font-family: 'Segoe UI', Arial, sans-serif; font-size: 17pt; line-height: 1.15; margin: 0 0 4pt }
h2 { font-family: 'Segoe UI', Arial, sans-serif; font-size: 11.2pt; margin: 11pt 0 3pt; break-after: avoid }
p { margin: 0 0 5.5pt }
body > p:first-of-type { color: #4a5a66; font-size: 9pt }
table { border-collapse: collapse; width: 100%; font-family: 'Segoe UI', Arial, sans-serif; font-size: 7.4pt; margin: 4pt 0 2pt; break-inside: avoid }
th, td { border-bottom: 0.5pt solid #b9c3cb; padding: 2pt 3pt; text-align: left; vertical-align: top }
th { border-bottom: 0.9pt solid #15202a }
figure { margin: 6pt 0 8pt; text-align: center; break-inside: avoid }
figure img { max-width: 100%; max-height: 82mm }
figcaption { font-family: 'Segoe UI', Arial, sans-serif; font-size: 8pt; color: #3a4954; text-align: left; margin-top: 2pt }
code { font-family: Consolas, 'Courier New', monospace; font-size: 8.4pt }
"""


def build():
    md = (HERE / "REPORT.md").read_text(encoding="utf-8")
    body = markdown.markdown(md, extensions=["tables"])
    body = body.replace('src="figs/eval_miss_vs_toks.png"', 'src="../../data/w5b/eval_miss_vs_toks.png"')
    html = f'<!doctype html><html lang="en"><meta charset="utf-8"><title>A toolkit for sharing one laptop GPU between a 60 fps application and a local language model</title><style>{CSS}</style><body>{body}</body></html>'
    (HERE / "REPORT.html").write_text(html, encoding="utf-8")
    if not CHROME:
        sys.exit("no Chrome or Edge found to render the PDF")
    pdf = HERE / "REPORT.pdf"
    if pdf.exists():
        pdf.unlink()
    r = subprocess.run([CHROME[0], "--headless=new", "--disable-gpu", "--no-pdf-header-footer", "--allow-file-access-from-files", f"--print-to-pdf={pdf}", (HERE / "REPORT.html").as_uri()],
                       capture_output=True, text=True, timeout=180)
    if not pdf.exists():
        sys.exit("PDF not produced: " + r.stderr[-600:])
    return page_count(pdf)


def page_count(pdf):
    data = Path(pdf).read_bytes()
    n = len(re.findall(rb"/Type\s*/Page(?![s\w])", data))
    return n


if __name__ == "__main__":
    print("pages:", build())
