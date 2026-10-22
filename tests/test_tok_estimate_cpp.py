"""Governed driver token estimate (workloads/background/tok_estimate.h, used by llama_governed_bench.cpp). Smoke 2 (journal 0041): the old estimate was an EWMA of ALL token
durations, so one token stretched by a frame (about 2x) lifted it and blocked tokens that would fit. New estimate = robust MEDIAN of the last 8 tokens NOT overlapped by a frame
(both the EWMA and the clean median are kept and logged); until a clean token exists the EWMA is used. Overlap rule: a token that started against a finite next arrival is overlapped
iff it ended after that arrival; one that started with no finite arrival (fg idle) is overlapped iff the fg published during the token. The C++ header is compiled with MSVC and
compared with the Python reference below on random sequences. No GPU.
Instruction (reviewer, 2026-10-22): "Yes to a clean-token estimate, implemented NOW (test-first) before smoke 3: robust median of recent tokens not overlapped by a frame, both estimates logged."
"""
import math
import subprocess

import numpy as np

from test_shm_cpp import ROOT, build

WINDOW = 8


def reference(seq):
    """seq: list of (tok_ms, overlapped). Returns per step (ewma, clean median or nan, value used)."""
    out, e, clean = [], None, []
    for ms, ov in seq:
        e = ms if e is None else 0.9 * e + 0.1 * ms
        if not ov:
            clean.append(ms)
        c = float(np.median(clean[-WINDOW:])) if clean else math.nan
        out.append((e, c, e if math.isnan(c) else c))
    return out


def overlapped_ref(t1_ms, next_start_ms, t0_ms, pace_have, pace_updated_ms):
    if math.isfinite(next_start_ms):
        return t1_ms > next_start_ms
    return bool(pace_have) and pace_updated_ms >= t0_ms


def run(tmp_path, lines):
    exe = tmp_path / "test_tok_estimate.exe"
    if not exe.exists():
        build(tmp_path, ROOT / "tests" / "cpp" / "test_tok_estimate.cpp", exe)
        subprocess.run([str(exe), str(tmp_path / "none.csv")], capture_output=True, timeout=120)          # warm the fresh exe (journal 0036)
    csv = tmp_path / "cases.csv"
    csv.write_text("\n".join(lines) + "\n")
    r = subprocess.run([str(exe), str(csv)], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stdout + r.stderr
    return r.stdout.strip().splitlines()


def test_estimates_match_the_python_reference_on_random_sequences(tmp_path):
    rng = np.random.default_rng(3)
    seq = []
    for _ in range(300):
        ov = bool(rng.random() < 0.3)
        seq.append((float(rng.normal(20.5, 0.8) if ov else rng.normal(10.1, 0.15)), ov))
    got = run(tmp_path, [f"T,{ms!r},{int(ov)}" for ms, ov in seq])
    want = reference(seq)
    assert len(got) == len(want)
    for g, w in zip(got, want):
        f = g.split()
        assert f[0] == "E"
        e, c, v = float(f[1]), float(f[2]), float(f[3])
        assert abs(e - w[0]) < 1e-9 and abs(v - w[2]) < 1e-9 and ((math.isnan(c) and math.isnan(w[1])) or abs(c - w[1]) < 1e-9)


def test_a_stretched_token_does_not_move_the_clean_estimate_but_does_move_the_ewma(tmp_path):
    seq = [(10.1, False)] * 10 + [(20.7, True)] * 3
    got = [line.split() for line in run(tmp_path, [f"T,{ms!r},{int(ov)}" for ms, ov in seq])]
    assert abs(float(got[-1][3]) - 10.1) < 1e-9                       # value used = clean median
    assert float(got[-1][1]) > 11.0                                   # the EWMA of all tokens was lifted
    assert abs(float(got[-1][2]) - 10.1) < 1e-9


def test_before_any_clean_token_the_ewma_is_used(tmp_path):
    got = [line.split() for line in run(tmp_path, ["T,20.5,1", "T,21.0,1"])]
    assert math.isnan(float(got[0][2])) and abs(float(got[0][3]) - 20.5) < 1e-9


def test_overlap_rule_matches_the_reference(tmp_path):
    rng = np.random.default_rng(4)
    rows, want = [], []
    for _ in range(300):
        t0 = rng.uniform(0, 1000); t1 = t0 + rng.uniform(5, 25)
        nxt = math.inf if rng.random() < 0.3 else t0 + rng.uniform(0, 30)
        have = int(rng.random() < 0.8); upd = t0 + rng.uniform(-30, 30)
        rows.append("O," + ",".join("inf" if math.isinf(v) else repr(float(v)) for v in (t1, nxt, t0)) + f",{have},{upd!r}")
        want.append(overlapped_ref(t1, nxt, t0, have, upd))
    got = run(tmp_path, rows)
    assert [g.split()[1] == "1" for g in got] == want
