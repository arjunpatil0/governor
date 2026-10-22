"""Plant parameters for the governor simulator. Every number is PARSED from a committed result file at load time (no typed constants);
the few values that live in prose are read from an exact quoted sentence (CONSTANT_SOURCES), and a test checks the quote exists.
Sources: data/w1_downclock_results.md (fg speed and power vs clock), data/w2_L_results.md (llama.cpp decode tok/s, power),
data/w2_G_results.md (q, s), data/w2_A_secondary_results.md SA4 (anchor rows for the plant tests), journal/0011 (idle power)."""
import re
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]

CONSTANT_SOURCES = {
    "p_idle_w": ("journal/0011_2026-10-21_w2-pilot.md", "The GPU idles at 210 MHz / 5 W"),
}

_W1_ROW = re.compile(r"^\| fma \| (\w+) \| \d+ \| (\d+) \| [\d.]+ \S+ \| ([\d.]+) \[[^\]]*\] \| ([\d.]+) \|", re.M)
_L_ROW = re.compile(r"^\s*(\d+|unlocked)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s*$", re.M)
_SA4_ROW = re.compile(r"^\s*(\S+)\s+([\d.]+)\s+(\d+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+(True|False)\s*$", re.M)


def _read(root, rel):
    return (Path(root) / rel).read_text(encoding="utf-8")


@dataclass
class Params:
    UNLOCKED_MHZ: float
    _fg_x: np.ndarray            # clock MHz, ascending
    _fg_rel: np.ndarray          # fma relative throughput (W1)
    _fg_p: np.ndarray            # fma power W (W1 counter)
    _bg_x: np.ndarray
    _bg_tok: np.ndarray
    _bg_p: np.ndarray
    rel_thr_L: dict
    q_ms: float
    s_ms: float
    p_idle_w: float
    sa4: dict
    CONSTANT_SOURCES: dict = field(default_factory=lambda: dict(CONSTANT_SOURCES))
    levels: tuple = ()

    @property
    def share_divisor(self):
        """Time-sliced co-run: each context progresses at 1/S of its solo speed, S = 2 + 2s/q (journal 0033; slowdown of a long fg with an always-on bg)."""
        return 2 + 2 * self.s_ms / self.q_ms

    def _check(self, f):
        if not (self._fg_x[0] - 1e-9 <= f <= self.UNLOCKED_MHZ + 1e-9):
            raise ValueError(f"clock {f} MHz outside the measured range [{self._fg_x[0]}, {self.UNLOCKED_MHZ}]")

    def fg_ratio(self, f):
        """fg service time at clock f relative to 1800 MHz (compute-bound FMA frame): rel(1800) / rel(f) with rel linear in MHz between W1 levels."""
        self._check(f)
        return float(np.interp(1800.0, self._fg_x, self._fg_rel) / np.interp(f, self._fg_x, self._fg_rel))

    def fg_power_w(self, f):
        self._check(f)
        return float(np.interp(f, self._fg_x, self._fg_p))

    def tok_s(self, f):
        self._check(f)
        return float(np.interp(f, self._bg_x, self._bg_tok))

    def bg_power_w(self, f):
        self._check(f)
        return float(np.interp(f, self._bg_x, self._bg_p))


def load_params(root=ROOT):
    w1 = _read(root, "data/w1_downclock_results.md")
    rows = _W1_ROW.findall(w1)
    assert rows, "no fma rows parsed from W1 results"
    unlocked = None
    fx, fr, fp = [], [], []
    for lab, sm, rel, pw in rows:
        x = float(sm)
        if lab == "unlocked":
            unlocked = x
        fx.append(x); fr.append(float(rel)); fp.append(float(pw))
    assert unlocked is not None
    o = np.argsort(fx)
    fx, fr, fp = np.array(fx)[o], np.array(fr)[o], np.array(fp)[o]

    L = _read(root, "data/w2_L_results.md")
    sect = L.split("## Throughput, board power and J/token by level", 1)[1]
    sect = sect.split("\n\n##", 1)[0]
    lrows = _L_ROW.findall(sect)
    assert lrows, "no rows parsed from L throughput table"
    bx, bt, bp, rel_l = [], [], [], {}
    for lab, tok, pw, rel, _j in lrows:
        x = unlocked if lab == "unlocked" else float(lab)
        bx.append(x); bt.append(float(tok)); bp.append(float(pw))
        rel_l["unlocked" if lab == "unlocked" else int(lab)] = float(rel)
    o = np.argsort(bx)

    G = _read(root, "data/w2_G_results.md")
    q = float(re.search(r"pooled over all cells: q = ([\d.]+) ms", G).group(1))
    s = float(re.search(r"pooled s = ([\d.]+) ms", G).group(1))

    A = _read(root, "data/w2_A_secondary_results.md")
    blk = A.split("## SA4 foreground size and duty cycle", 1)[1].split("Cells with frac_completed", 1)[0]
    sa4 = {}
    for cid, fgms, m, duty, lm, l99, frac, gpu50, slow, ovl in _SA4_ROW.findall(blk):
        sa4[cid] = dict(fg_ms=float(fgms), m_ms=float(m), duty=float(duty), lat_mean_ms=float(lm), lat_p99_ms=float(l99), frac_completed=float(frac),
                        fg_gpu_p50_ms=float(gpu50), slowdown=float(slow), overloaded=(ovl == "True"))
    assert sa4, "no SA4 rows parsed"

    path, quote = CONSTANT_SOURCES["p_idle_w"]
    m = re.search(r"idles at 210 MHz / ([\d.]+) W", quote)
    assert quote in _read(root, path)
    p_idle = float(m.group(1))

    lv = tuple(sorted(int(k) for k in rel_l if k != "unlocked")) + (unlocked,)
    return Params(UNLOCKED_MHZ=unlocked, _fg_x=fx, _fg_rel=fr, _fg_p=fp, _bg_x=np.array(bx)[o], _bg_tok=np.array(bt)[o], _bg_p=np.array(bp)[o],
                  rel_thr_L=rel_l, q_ms=q, s_ms=s, p_idle_w=p_idle, sa4=sa4, levels=lv)
