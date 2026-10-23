"""Plant parameters for the governor simulator. Every number is PARSED from a committed result file at load time (no typed constants);
the few values that live in prose are read from an exact quoted sentence (CONSTANT_SOURCES), and a test checks the quote exists.
Sources: data/w1_downclock_results.md (fg speed and power vs clock), data/w2_L_results.md (llama.cpp decode tok/s, power),
data/w2_G_results.md (q, s), data/w2_A_secondary_results.md SA4 (anchor rows for the plant tests), journal/0011 (idle power)."""
import json
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
    clock_latency_ms: float = 0.0
    share_override: float = None
    token_jitter: np.ndarray = None
    profiles: dict = field(default_factory=dict)       # alternative bg profiles {name: (x_mhz, tok_s, power_w)} for the unseen-workload scene S5
    CONSTANT_SOURCES: dict = field(default_factory=lambda: dict(CONSTANT_SOURCES))
    levels: tuple = ()

    @property
    def share_divisor_G(self):
        """G-derived: S = 2 + 2s/q (journal 0033; slowdown of a long fg with an always-on bg). Independent of the A2 anchors."""
        return 2 + 2 * self.s_ms / self.q_ms

    @property
    def share_divisor(self):
        """Time-sliced co-run: each context progresses at 1/S of its solo speed. S is fitted to the A2 SA4 anchors (sim/calibrate.py -> data/sim_calibration.json); the G value is the sensitivity setting."""
        return self.share_override if self.share_override is not None else self.share_divisor_G

    def clamp_clock(self, f):
        """A LIVE clock reading mapped into the measured range [lowest W1 clock, unlocked median]: the unlocked GPU reads above the W1 median (2475 vs 2460 MHz, trial 2026-10-23) and an idle GPU below 600."""
        return float(min(max(float(f), float(self._fg_x[0])), float(self.UNLOCKED_MHZ)))

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

    def tok_s(self, f, profile=None):
        self._check(f)
        x, t, _p = (self._bg_x, self._bg_tok, self._bg_p) if profile is None else self.profiles[profile]
        return float(np.interp(f, x, t))

    def bg_power_w(self, f, profile=None):
        self._check(f)
        x, _t, p = (self._bg_x, self._bg_tok, self._bg_p) if profile is None else self.profiles[profile]
        return float(np.interp(f, x, p))


def load_token_jitter(root):
    """Empirical bg token-time jitter from the L run per-token logs (data/raw/w2_L/<run>/cells/*llama_*/llama_tokens.csv): inter-token intervals of each cell
    divided by that cell median (first 5 intervals dropped), pooled, rescaled to mean 1 so the L throughput anchor is preserved."""
    run = sorted((Path(root) / "data" / "raw" / "w2_L").glob("*/cells"))[-1]
    xs = []
    for f in sorted(run.glob("*llama_*/llama_tokens.csv")):
        t = np.loadtxt(f, delimiter=",", skiprows=1, usecols=0)
        d = np.diff(t)[5:]
        if len(d) > 20:
            xs.append(d / np.median(d))
    x = np.concatenate(xs)
    return x / x.mean()


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

    audit = json.loads(_read(root, "data/capability_audit.json"))
    rows_a = audit if isinstance(audit, list) else audit.get("rows", audit)
    lat = [r["latency_ms"] for r in rows_a if r["item"].startswith("nvidia-smi -lgc")]
    assert lat and lat[0], "no clock-lock latency in capability audit"

    cal = Path(root) / "data" / "sim_calibration.json"
    share = json.loads(cal.read_text(encoding="utf-8"))["share_divisor_fit"] if cal.exists() else None

    C = _read(root, "data/w2_C_results.md")
    crows = re.findall(r"^\s*fp16\s+True\s+(\d+|unlocked)\s+([\d.]+)\s+([\d.]+)\s*$", C, re.M)
    assert crows, "no fp16 graph rows parsed from C results"
    cx, crel, cj = [], [], []
    for lab, rel, jpt in crows:
        cx.append(unlocked if lab == "unlocked" else float(lab)); crel.append(float(rel)); cj.append(float(jpt))
    oc = np.argsort(cx)
    cx, crel, cj = np.array(cx)[oc], np.array(crel)[oc], np.array(cj)[oc]
    tok_ref = float(np.array(bt)[np.array(bx) == unlocked][0])                # absolute scale: the L unlocked rate; only the SHAPE (knee 1050) comes from C
    alt = {"fp16": (cx, tok_ref * crel, cj * tok_ref * crel)}

    lv = tuple(sorted(int(k) for k in rel_l if k != "unlocked")) + (unlocked,)
    return Params(UNLOCKED_MHZ=unlocked, _fg_x=fx, _fg_rel=fr, _fg_p=fp, _bg_x=np.array(bx)[o], _bg_tok=np.array(bt)[o], _bg_p=np.array(bp)[o],
                  rel_thr_L=rel_l, q_ms=q, s_ms=s, p_idle_w=p_idle, sa4=sa4, clock_latency_ms=float(lat[0]), share_override=share, token_jitter=load_token_jitter(root), profiles=alt, levels=lv)
