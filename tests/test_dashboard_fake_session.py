"""tools/dashboard/fake_session.py: the synthetic live session (no GPU) publishes frames, tokens, control and decision blocks that the LIVE source reads, labels itself synthetic and cleans up its registry.
Instruction (Arjun): "LIVE: attach to a running governed session and show real frames, tokens, clock, power and the governor's decisions as they happen" (exercised here without hardware, honestly labelled synthetic)."""
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DASH = ROOT / "tools" / "dashboard"
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(DASH))
import sources as src  # noqa: E402


class Poller:
    def read(self):
        return 48.0, 1800.0


def test_the_live_source_reads_a_synthetic_session_end_to_end_and_the_registry_is_removed(tmp_path):
    reg = tmp_path / "session.json"
    p = subprocess.Popen([sys.executable, str(DASH / "fake_session.py"), "--seconds", "6", "--session-file", str(reg)], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        t0 = time.time()
        while not reg.exists() and time.time() - t0 < 60 and p.poll() is None:
            time.sleep(0.1)
        s = src.read_session(reg)
        assert s is not None and s["synthetic"] is True and s["controller"] == "d'B"
        live = src.LiveSource(s, poller=Poller())
        assert live.meta()["synthetic"] is True and live.meta()["manager"] == "Governor"
        time.sleep(0.4)
        msgs = []
        t_end = time.time() + 3.0
        while time.time() < t_end:
            msgs.append(live.tick(0.05))
            time.sleep(0.05)
        frames = sum(len(m["events"]["frames"]) for m in msgs)
        tokens = sum(len(m["events"]["tokens"]) for m in msgs)
        decs = [d for m in msgs for d in m["events"]["decisions"]]
        ctrl = [c for m in msgs for c in m["events"]["ctrl"]]
        assert 120 <= frames <= 220, frames                                                                    # about 60 Hz for 3 s
        assert tokens > 60 and len(decs) >= 15 and ctrl and msgs[-1]["pace"] is not None
        assert decs[-1]["clock_mhz"] > 0 and decs[-1]["limit_ms"] > 0 and decs[-1]["options_checked"] >= decs[-1]["options_safe"]
        assert msgs[-1]["stats"]["frames"] >= frames and msgs[-1]["stats"]["power_w"] == 48.0
    finally:
        p.wait(timeout=30)
    assert not reg.exists() and p.returncode == 0
