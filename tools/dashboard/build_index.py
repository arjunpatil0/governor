"""Builds tools/dashboard/index.html from docs/dashboard_reference.html (the design, tour text and JS simulator made separately; reused, not redesigned) plus the mode layer in tools/dashboard/parts/:
live.css (mode pill, mode bar, replay picker), modebar.html (inserted at the top of the stage), live.js (RealFeed, SSE client, pickers, mode switching). The reference is patched with EXACT-match replacements (each must match
exactly once, otherwise the build fails: the reference changed and the layer needs a look). The simulator, the guided tour, the results cards and the notes are the reference's own text.
   python tools/dashboard/build_index.py        (writes tools/dashboard/index.html; tests/test_dashboard_page.py checks the committed file equals a fresh build)"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
REFERENCE = ROOT / "docs" / "dashboard_reference.html"
PARTS = HERE / "parts"
OUT = HERE / "index.html"


def read(p):
    return Path(p).read_text(encoding="utf-8")


def patch(text, old, new, label):
    n = text.count(old)
    if n != 1:
        raise SystemExit(f"build_index: patch '{label}' matched {n} times (expected exactly 1): the reference changed")
    return text.replace(old, new)


def build():
    t = read(REFERENCE).replace("\r\n", "\n")
    t = patch(t, "<title>Co-Scheduler Lab</title>", '<!doctype html>\n<html lang="en">\n<meta charset="utf-8">\n<meta name="viewport" content="width=device-width, initial-scale=1">\n<title>Co-Scheduler Lab</title>', "head")
    t = patch(t, "display=swap\">", "display=swap\" media=\"print\" onload=\"this.media='all'\">", "fonts non-blocking (the page works offline: the font stacks fall back)")
    t = patch(t, "</style>", read(PARTS / "live.css") + "</style>", "css")
    t = patch(t, '<div class="brand">Co-Scheduler <span>Lab</span></div>', '<div class="brand">Co-Scheduler <span>Lab</span></div><span class="modepill" id="modepill" data-mode="sim">SIMULATOR</span>', "nav pill")
    t = patch(t, '<div class="status"><span class="light" id="light"></span>', read(PARTS / "modebar.html") + '      <div class="status"><span class="light" id="light"></span>', "mode bar")
    t = patch(t, '<div class="lbl">If these settings ran for 12 seconds:</div>', '<div class="lbl" id="o-lbl">If these settings ran for 12 seconds:</div>', "outcome label id")
    t = patch(t, "if (s.cfg) cfg = { ...BASE, ...s.cfg };", "if (mode !== 'sim') cfg = realCfg(); else if (s.cfg) cfg = { ...BASE, ...s.cfg };", "renderStep keeps the real config")
    t = patch(t, "  const box = $('stepctls'); box.innerHTML = '';\n  const list = ctlsFor(STEPS[step]);", "  const box = $('stepctls'); box.innerHTML = '';\n  if (mode !== 'sim') return renderRealCtlsNote();\n  const list = ctlsFor(STEPS[step]);", "tour controls note")
    t = patch(t, "function restart() {\n  sim = new Sim(", "function restart() {\n  if (mode !== 'sim') return restartReal();\n  sim = new Sim(", "restart guard")
    t = patch(t, "  const active = a => SCENES[cfg.scene].f(a / 1000) !== null;", "  const active = a => sim.isActive ? sim.isActive(a) : SCENES[cfg.scene].f(a / 1000) !== null;", "upcoming arrivals")
    t = patch(t, "need = tokMs(cfg.model, sim.clock) * (1 + cfg.estErr) + sim.cmd.guard;", "need = (sim.needMs ? sim.needMs() : tokMs(cfg.model, sim.clock) * (1 + cfg.estErr)) + sim.cmd.guard;", "piece length")
    t = patch(t, "  if (cfg.ctrl !== 'governor' || !sim.decision) { th.hidden = true; return; }", "  if (sim.thinkHtml) { th.hidden = false; th.innerHTML = sim.thinkHtml(); return; }\n  if (cfg.ctrl !== 'governor' || !sim.decision) { th.hidden = true; return; }", "thinking box")
    t = patch(t, "const dpr = window.devicePixelRatio || 1, w = cv.clientWidth, h = +cv.getAttribute('height');",
              "const dpr = window.devicePixelRatio || 1, w = cv.clientWidth, h = +(cv.dataset.h || (cv.dataset.h = cv.getAttribute('height')));          // FIX of the reference: setting cv.height rewrites the attribute, so with a device pixel ratio other than 1 the canvas grew every frame",
              "canvas height bug at devicePixelRatio != 1")
    t = patch(t, "init();\n</script>", read(PARTS / "live.js") + "\ninit();\nbootModes();\n</script>", "script")
    return t


def main():
    OUT.write_text(build(), encoding="utf-8", newline="\n")
    print(f"wrote {OUT} ({OUT.stat().st_size} bytes)")


if __name__ == "__main__":
    sys.exit(main())
