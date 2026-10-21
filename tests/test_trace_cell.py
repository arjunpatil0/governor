"""trace_cell.py ends on a fixed window and kills children that hang (incident: fg child wrote its output but never exited under nsys, journal 0018)."""
import subprocess
import sys
import time

import pytest

from trace_cell import wait_or_kill

HANG = "import sys,time; open(sys.argv[1],'w').write('x'); time.sleep(120)"
EXIT = "import sys; open(sys.argv[1],'w').write('x')"
SILENT = "import time; time.sleep(120)"


def _p(code, *args):
    return subprocess.Popen([sys.executable, "-c", code, *args])


def test_statuses_for_exited_hung_after_output_and_never_finished(tmp_path):
    outs = [tmp_path / "a", tmp_path / "b", tmp_path / "c"]
    procs = [_p(EXIT, str(outs[0])), _p(HANG, str(outs[1])), _p(SILENT)]
    t0 = time.time()
    st = wait_or_kill(procs, [outs[0], outs[1], outs[2]], deadline_s=6.0, grace_s=1.0)
    assert st == ["exited", "killed_after_output", "killed_deadline"]
    assert time.time() - t0 < 15 and all(p.poll() is not None for p in procs)
