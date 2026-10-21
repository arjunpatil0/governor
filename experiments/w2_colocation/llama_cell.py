"""Pure helpers for part L (llama.cpp validation): driver execution-mode check and token-window extraction."""
import re

import numpy as np

_EXEC = re.compile(r"EXEC_MODE\s+(\w+)\s+offloaded=(\d+)/(\d+)")


def parse_exec_mode(log_text):
    """ok iff the driver reported CUDA with every layer offloaded (no CPU fallback; addendum 'fail loudly')."""
    m = _EXEC.search(log_text)
    if not m:
        return dict(ok=False, detail="no EXEC_MODE line in the driver log")
    mode, off, tot = m.group(1), int(m.group(2)), int(m.group(3))
    return dict(ok=(mode == "cuda" and tot > 0 and off == tot), detail=f"{mode} offloaded {off}/{tot}")


def window_tokens(t_tok_end, t_win0, t_win1):
    """(number of tokens ending in [t_win0, t_win1), decode-started-late flag as in part C: no token yet when the window opened)."""
    t = np.asarray(t_tok_end, float)
    n = int(((t >= t_win0) & (t < t_win1)).sum())
    return n, bool(len(t) == 0 or t[0] > t_win0)
