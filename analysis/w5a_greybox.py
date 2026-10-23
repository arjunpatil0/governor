"""Grey-box cell-level predictor G of the registered W5a model-selection protocol (docs/W5A_MODEL_SELECTION_PROTOCOL.md section 4; tests/test_w5a_greybox.py).
Analytic steady state of the plant of sim/plant.py for one 30 s cell (no simulation loop): fg frame time F, clean token time tau(f), time-slice share S, pacing (aligned slack test + duty,
unaligned duty), time-weighted power. Three scalars are calibrated online from the adaptation cells: the token-time curve (controllers.tokmodel.TokenTimeModel), the fg scale alpha, the power offset delta.
Also: the design-based adaptation-cell rule (section 3), the cell -> input mapping and the 70-setting grid used for the latency test."""
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from controllers.tokmodel import TokenTimeModel  # noqa: E402

PERIOD_MS = 1000.0 / 60.0
ALPHA_PRIOR = 0.745                                   # indicative measured/nominal fg frame time (smoke 3, journal 0043)
STEPS = (1.0, 0.7, 1.3, 0.7, 1.0, 1.3)               # the varying condition (w5a_design.STEPS)
CLOCKS = (900.0, 1050.0, 1200.0, 1350.0, 1500.0, 1800.0, None)      # None = unlocked


@dataclass
class Calib:
    alpha: float
    delta: float
    tok_model: TokenTimeModel

    @classmethod
    def prior(cls, P):
        return cls(ALPHA_PRIOR, 0.0, TokenTimeModel(P, forget=1.0, prior_var=1.0))


def cell_inputs(P, cells):
    """Registered model inputs of cell dicts (cell_list / cell.json fields)."""
    f = np.array([P.UNLOCKED_MHZ if c["clock"] == "unlocked" else float(c["clock"]) for c in cells])
    cost = np.array([float(c["condition"].replace("var", "").replace("c", "")) for c in cells])
    return dict(f=f, aligned=np.array([c["mode"] == "aligned" for c in cells]), guard=np.array([float(c["guard_ms"]) for c in cells]),
                duty=np.array([float(c["duty"]) for c in cells]), c=cost, varying=np.array([c["condition"].startswith("var") for c in cells]))


def grid70(cost_ms, P=None):
    """The 70 settings (7 clocks x 10 pacing configurations) of one state, for the latency test."""
    if P is None:
        from sim.params import load_params
        P = load_params()
    pac = [(True, g, d) for g in (0.0, 1.0) for d in (0.25, 0.5, 1.0)] + [(False, 0.5, d) for d in (0.1, 0.25, 0.5, 1.0)]
    rows = [(P.UNLOCKED_MHZ if c is None else c, a, g, d) for c in CLOCKS for (a, g, d) in pac]
    return dict(f=np.array([r[0] for r in rows]), aligned=np.array([r[1] for r in rows]), guard=np.array([r[2] for r in rows]), duty=np.array([r[3] for r in rows]),
                c=np.full(len(rows), float(cost_ms)), varying=np.zeros(len(rows), dtype=bool))


def _per_clock(f, fn):
    u = np.unique(f)
    m = {x: fn(float(x)) for x in u}
    return np.array([m[x] for x in f])


def _core(P, cal, f, aligned, guard, duty, cost):
    S, T, idle = P.share_divisor, PERIOD_MS, P.p_idle_w
    ratio = _per_clock(f, P.fg_ratio)
    fgp = _per_clock(f, P.fg_power_w)
    bgp = _per_clock(f, P.bg_power_w) + cal.delta
    tau = _per_clock(f, cal.tok_model.predict)
    F = cal.alpha * cost * ratio
    # ---- aligned: tokens only inside the slack after the frame
    W = T - F - guard
    n = np.where(W < tau, 0.0, np.floor((W - tau) * duty / tau) + 1.0)
    tok_a = np.minimum(60.0 * n, 1000.0 * duty / tau)
    over_a = F > T
    u_a = np.minimum(F / T, 1.0)
    b_a = np.minimum(tok_a * tau / 1000.0, 1.0)
    # ---- unaligned: duty-cycled background, time-sliced with the frames
    beta = duty
    Feff = F * ((1.0 - beta) + beta * S)
    over_u = Feff > T
    u_u = np.minimum(Feff / T, 1.0)
    taueff = tau * ((1.0 - u_u) + u_u * S)
    tok_u = 1000.0 * beta / taueff
    xs = (T - F) / (S - 1.0)
    m = np.minimum(F, taueff)
    pm = np.where(xs >= m, 0.0, beta * (1.0 - xs / m))
    miss_u = np.where(over_u, 1.0, np.clip(pm, 0.0, 1.0))
    p99_u = np.where(beta > 0.01, F + (S - 1.0) * m, F)
    over = np.where(aligned, over_a, over_u)
    u = np.where(over, 1.0, np.where(aligned, u_a, u_u))
    b = np.where(aligned, b_a, beta)
    o = u * b
    power = idle + (u - o) * (fgp - idle) + (b - o) * (bgp - idle) + o * ((fgp + bgp) / 2.0 - idle)
    return dict(miss=np.where(aligned, np.where(over_a, 1.0, 0.0), miss_u), tok_s=np.where(aligned, tok_a, tok_u), power_w=power,
                p99=np.where(over, np.nan, np.where(aligned, F, p99_u)), overload=over)


def predict(P, cal, X):
    """Vectorised steady-state prediction for the rows of X (dict of arrays f, aligned, guard, duty, c, varying). Returns miss, tok_s, power_w, p99 (nan when overloaded), overload."""
    args = (np.asarray(X["f"], float), np.asarray(X["aligned"], bool), np.asarray(X["guard"], float), np.asarray(X["duty"], float))
    cost, var = np.asarray(X["c"], float), np.asarray(X["varying"], bool)
    one = _core(P, cal, *args, cost)
    if not var.any():
        return one
    ph = [_core(P, cal, *args, cost * m) for m in STEPS]
    out = {k: np.where(var, np.mean([p[k] for p in ph], axis=0), one[k]) for k in ("miss", "tok_s", "power_w")}
    out["p99"] = np.where(var, np.max([p["p99"] for p in ph], axis=0), one["p99"])
    out["overload"] = np.where(var, np.any([p["overload"] for p in ph], axis=0), one["overload"])
    return out


def _finite(x):
    return x is not None and np.isfinite(x)


def calibrate(P, cells):
    """Calibrate the three scalars from adaptation cells (dicts with the cell.json outcome fields), in the registered order: token-time curve, fg scale alpha, power offset delta.
    Quantities a cell cannot give (no tokens, overloaded) are skipped. Priors: alpha = ALPHA_PRIOR with weight 1, delta = 0 with weight 1."""
    cal = Calib.prior(P)
    S = P.share_divisor
    if not cells:
        return cal
    X = cell_inputs(P, cells)
    ratio = np.array([P.fg_ratio(f) for f in X["f"]])
    F0 = ALPHA_PRIOR * X["c"] * ratio
    beta = np.where(X["aligned"], 0.0, X["duty"])
    Feff = F0 * ((1.0 - beta) + beta * S)
    u = np.minimum(Feff / PERIOD_MS, 1.0)
    dil = np.where(X["aligned"], 1.0, (1.0 - u) + u * S)
    for i, c in enumerate(cells):                                                     # 1. token-time curve (clean token time = observed / contention dilation)
        if _finite(c.get("tok_ms_p50")) and c.get("bg_tok_s", 0.0) > 0:
            cal.tok_model.update(float(X["f"][i]), float(c["tok_ms_p50"]) / float(dil[i]))
    logs = []
    for i, c in enumerate(cells):                                                     # 2. fg scale from the median frame latency of cells that were not overloaded
        if c.get("abandoned", 0) == 0 and _finite(c.get("fg_p50_ms")) and c["fg_p50_ms"] > 0:
            pred = F0[i] * (1.0 + (S - 1.0) * beta[i])
            logs.append(np.log(c["fg_p50_ms"] / pred))
    if logs:
        cal.alpha = ALPHA_PRIOR * float(np.exp(np.sum(logs) / (len(logs) + 1.0)))
    res = []
    pred_p = predict(P, cal, X)["power_w"]                                            # 3. power offset (delta is 0 here)
    for i, c in enumerate(cells):
        if _finite(c.get("power_w")):
            res.append(c["power_w"] - pred_p[i])
    if res:
        cal.delta = float(np.sum(res) / (len(res) + 1.0))
    return cal


def select_adaptation(cells, k):
    """Design-based adaptation cells (protocol section 3): unaligned, duty >= 0.5, first cell of each not-yet-taken clock label in (session, order) order, then fill with the next eligible cells."""
    elig = sorted([c for c in cells if c["mode"] == "unaligned" and c["duty"] >= 0.5], key=lambda c: (c["session"], c["order"]))
    chosen, seen = [], set()
    for c in elig:
        if len(chosen) == k:
            break
        if str(c["clock"]) not in seen:
            chosen.append(c); seen.add(str(c["clock"]))
    for c in elig:
        if len(chosen) == k:
            break
        if c not in chosen:
            chosen.append(c)
    return chosen
