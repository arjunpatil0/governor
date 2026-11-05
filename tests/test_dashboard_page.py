"""tools/dashboard/index.html: built from docs/dashboard_reference.html by tools/dashboard/build_index.py. Checks the committed page equals a fresh build, keeps the reference's own text and simulator, labels the mode
at all times, uses no external script and stays offline-safe. No browser here (the page was exercised in a real browser by hand; see the README Dashboard section).
Instruction (Arjun): "tools/dashboard/index.html built from docs/dashboard_reference.html ... The page labels which mode it is in, always ... Same light/dark theme handling. Works offline (fonts fall back)." """
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DASH = ROOT / "tools" / "dashboard"
sys.path.insert(0, str(DASH))
import build_index as bi  # noqa: E402

PAGE = (DASH / "index.html").read_text(encoding="utf-8")
REF = (ROOT / "docs" / "dashboard_reference.html").read_text(encoding="utf-8").replace("\r\n", "\n")


def test_the_committed_page_is_a_fresh_build_of_the_reference_plus_the_mode_layer():
    assert PAGE == bi.build()


def test_the_reference_is_untouched_in_text_wording_and_simulator():
    for needle in ("One graphics chip, two jobs", "Meet the app", "Squeeze it in anyway", "What the real laptop measured", "class Sim {", "function planGovernor(", "const STEPS = [", "Both want the chip, so they take turns"):
        assert needle in REF and needle in PAGE, needle
    ref_js = re.search(r"<script>(.*?)init\(\);\n</script>", REF, re.S).group(1)
    for line in ref_js.split("\n"):
        if line.strip().startswith(("const P =", "const FG =", "const BG =", "const SCENES")):
            assert line in PAGE, line                                                                       # the simulator's numbers are the reference's


def test_the_mode_is_labelled_in_three_places_and_all_three_modes_exist():
    for needle in ('id="modepill"', 'id="banner"', 'id="modeline"', 'id="mb-live"', 'id="mb-replay"', 'id="mb-sim"', "SIMULATOR", "REPLAY", "LIVE"):
        assert needle in PAGE, needle
    assert PAGE.count('data-mode="sim"') >= 2                                                              # the pill and the banner start in simulator mode


def test_every_mode_drives_the_same_strip_status_counters_power_and_thinking_box():
    for needle in ("class RealFeed", "sim = feed", "sim.thinkHtml", "sim.isActive", "new EventSource('/stream')", "/api/replay", "/api/source", "/api/cells", "paintOutcome", "renderRealCtlsNote"):
        assert needle in PAGE, needle
    assert "drawStrip()" in PAGE and "drawDom(false)" in PAGE


def test_tour_steps_stay_available_in_every_mode():
    assert "Try this step in the simulator" in PAGE and "function renderRealCtlsNote" in PAGE and "const STEPS = [" in PAGE
    assert "if (mode !== 'sim') cfg = realCfg(); else if (s.cfg)" in PAGE


def test_no_external_script_and_fonts_cannot_block_an_offline_page():
    assert not re.findall(r"<script[^>]+src=", PAGE)
    assert "media=\"print\" onload=\"this.media='all'\"" in PAGE and "system-ui" in PAGE and "Consolas" in PAGE            # the web fonts load without blocking; every stack has a system fallback
    assert not re.findall(r"https?://(?!fonts\.googleapis\.com|127\.0\.0\.1)", re.sub(r"<!--.*?-->", "", PAGE))


def test_light_and_dark_theme_handling_is_the_references():
    assert "prefers-color-scheme: dark" in PAGE and ':root[data-theme="dark"]' in PAGE and "color-scheme: dark" in PAGE and "--frame:" in PAGE
    assert ".modepill[data-mode=" in PAGE and "color-mix(in srgb" in PAGE and ".replaybar[hidden]" in PAGE


def test_the_canvas_height_fix_of_the_reference_is_in():
    assert "cv.dataset.h" in PAGE and "+cv.getAttribute('height');" not in PAGE


def test_a_patch_that_no_longer_matches_fails_the_build(monkeypatch, tmp_path):
    ref = tmp_path / "ref.html"
    ref.write_text(REF.replace("function restart() {", "function restart2() {"), encoding="utf-8")
    monkeypatch.setattr(bi, "REFERENCE", ref)
    with pytest.raises(SystemExit) as e:
        bi.build()
    assert "matched 0 times" in str(e.value)


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_the_page_script_parses(tmp_path):
    js = re.search(r"<script>(.*)</script>", PAGE, re.S).group(1)
    f = tmp_path / "page.js"
    f.write_text(js, encoding="utf-8")
    r = subprocess.run(["node", "--check", str(f)], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
