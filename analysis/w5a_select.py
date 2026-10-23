"""W5a model selection EXACTLY as registered (plan addendum L; docs/W5A_MODEL_SELECTION_PROTOCOL.md; tests/test_w5a_select.py, tests/test_w5a_greybox.py).
   python analysis/w5a_select.py --out data/w5a/selection          (writes selection.json and selection.md; deterministic, seeds fixed)
Candidates G (grey-box + RLS), HGB (scikit-learn HistGradientBoosting on the grey-box residual + online residual), GP (subset-of-data Gaussian process), MLP (5 x (32, 32)).
Folds: LOWO (K = 3 primary, K = 1 sensitivity) and leave-one-condition-out (reported only). Implementation details the protocol leaves implicit are listed in IMPLEMENTATION_NOTES."""
import argparse
import json
import sys
import time
import warnings
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "analysis"))

BUDGET_W, SLO_MISS, Z = 60.0, 0.01, 1.96
ORDER = ["G", "HGB", "GP", "MLP"]
IMPLEMENTATION_NOTES = [
    "Where G predicts an overloaded cell its p99 is undefined (nan); for residuals, features and scoring it is replaced by the 16.667 ms period (the lowest latency an overloaded frame can have).",
    "The online residual bias of the learned candidates is the mean (n/(n+1) shrunk) of (y - G - g) over the workload's adaptation cells, per target; targets without a defined value in a cell skip that cell.",
    "sigma_hat of every candidate is the RMS of its out-of-fold residuals (inner leave-one-workload-out among the training workloads, with the same calibration and bias) per target; GP std and ensemble spread are not used.",
    "Residual models are fit on all training cells (adaptation cells included); p99 residual models only on non-overloaded cells.",
    "Latency is measured on one fitted model per candidate (the fold that holds out llama32_3b, K = 3): grey-box + features + 4 residual predictions + bias + intervals + decision for the 70 settings of condition c9.",
]


# ---------------------------------------------------------------- scoring (tested)
def pick_and_score(obs_tok, obs_miss, obs_power, pred_tok, pred_miss, pred_power, sigma_power):
    """One stratum: the model's pick among its candidate cells and the REGRET / FALSE-FEASIBLE outcome (protocol section 5)."""
    obs_tok, obs_miss, obs_power = (np.asarray(a, float) for a in (obs_tok, obs_miss, obs_power))
    pred_tok, pred_miss, pred_power = (np.asarray(a, float) for a in (pred_tok, pred_miss, pred_power))
    obs_ok = (obs_miss <= SLO_MISS) & (obs_power <= BUDGET_W)
    best = float(obs_tok[obs_ok].max()) if obs_ok.any() else 0.0
    best = best if best >= 1.0 else 0.0
    ok = (pred_miss <= SLO_MISS) & (pred_power + Z * sigma_power <= BUDGET_W) & (pred_tok >= 1.0)
    if not ok.any():
        return dict(pick=None, best=best, regret=best, false_feasible=None)
    i = int(np.argmax(np.where(ok, pred_tok, -np.inf)))
    if not obs_ok[i]:
        return dict(pick=i, best=best, regret=best, false_feasible=True)
    return dict(pick=i, best=best, regret=max(best - float(obs_tok[i]), 0.0), false_feasible=False)


def classify(pred_ok, obs_ok):
    pred_ok, obs_ok = np.asarray(pred_ok, bool), np.asarray(obs_ok, bool)
    ff, fi = int(np.sum(pred_ok & ~obs_ok)), int(np.sum(~pred_ok & obs_ok))
    n = int(len(pred_ok))
    return dict(n=n, false_feasible=ff, false_infeasible=fi, false_feasible_share_of_all=ff / n if n else float("nan"), false_infeasible_share_of_all=fi / n if n else float("nan"),
                false_feasible_of_predicted_feasible=ff / pred_ok.sum() if pred_ok.any() else float("nan"), false_infeasible_of_observed_feasible=fi / obs_ok.sum() if obs_ok.any() else float("nan"))


def coverage(y, lo, hi):
    y, lo, hi = np.asarray(y, float), np.asarray(lo, float), np.asarray(hi, float)
    return float(np.mean((y >= lo) & (y <= hi))) if len(y) else float("nan")


def select(ms, order):
    """Protocol section 6: hard gates G1-G3, then the 10%-of-best rule (+0.10 absolute on REGRET_REL) among the passing candidates; the simplest qualifying candidate wins."""
    failed, passing = {}, []
    for m in ms:
        why = []
        ff = m["false_feasible_rate"]
        if np.isfinite(ff) and ff > 0.05:
            why.append(f"G1 false-feasible {ff * 100:.1f}% > 5%")
        for t, c in m["coverage"].items():
            if not (0.90 <= c <= 0.98):
                why.append(f"G2 coverage {t} {c * 100:.1f}% outside 90-98%")
        if not m["latency_p99_s"] < 1e-3:
            why.append(f"G3 latency p99 {m['latency_p99_s'] * 1e3:.2f} ms >= 1 ms")
        (failed.__setitem__(m["name"], why) if why else passing.append(m))
    if not passing:
        return dict(selected=None, failed_gates=failed, qualifying=[], note="no candidate passes G1-G3")
    best = {k: min(m[k] for m in passing) for k in ("p99_err", "tok_mae", "power_mae")}
    best_reg = min(m["regret_rel"] for m in passing)
    qual = [m["name"] for m in passing if all(m[k] <= 1.10 * best[k] + 1e-12 for k in best) and m["regret_rel"] <= best_reg + 0.10 + 1e-12]
    sel = next((n for n in order if n in qual), None)
    return dict(selected=sel, failed_gates=failed, qualifying=qual, best_errors=best, best_regret_rel=best_reg)


# ---------------------------------------------------------------- data
def load_cells():
    lst = json.loads((ROOT / "data" / "w5a" / "cell_list.json").read_text(encoding="utf-8"))["cells"]
    out = []
    for c in lst:
        r = json.loads((ROOT / "data" / "w5a" / f"session{c['session']}" / c["cell_id"] / "cell.json").read_text(encoding="utf-8"))
        d = dict(r)
        d["overloaded"] = r["abandoned"] > 0
        d["y_miss"], d["y_tok_s"], d["y_power_w"] = r["miss_frac_incl_abandoned"], r["bg_tok_s"], r["power_w"]
        d["y_p99"] = float("nan") if d["overloaded"] else r["fg_p99_ms"]
        out.append(d)
    return out


TARGETS = ("miss", "tok_s", "power_w", "p99")
PERIOD = 1000.0 / 60.0


class Ctx:
    def __init__(self):
        from sim.params import load_params
        self.P = load_params()


def g_predict(ctx, cals, cells):
    """Grey-box predictions for cells, each with its workload's calibration; the nan p99 of predicted overloads becomes the period."""
    from w5a_greybox import cell_inputs, predict
    n = len(cells)
    out = {t: np.zeros(n) for t in TARGETS}
    over = np.zeros(n, bool)
    for w in sorted({c["workload"] for c in cells}):
        idx = [i for i, c in enumerate(cells) if c["workload"] == w]
        r = predict(ctx.P, cals[w], cell_inputs(ctx.P, [cells[i] for i in idx]))
        for t in TARGETS:
            out[t][idx] = r[t]
        over[idx] = r["overload"]
    out["p99"] = np.where(np.isnan(out["p99"]), PERIOD, out["p99"])
    return out, over


def descriptors(ctx, cal):
    tm = cal.tok_model
    return [cal.alpha, cal.delta, float(np.log(tm.predict(900.0) / tm.prior_ms(900.0))), float(np.log(tm.predict(1800.0) / tm.prior_ms(1800.0)))]


def feature_matrix(ctx, cals, cells, gp):
    from w5a_greybox import cell_inputs
    X = cell_inputs(ctx.P, cells)
    desc = np.array([descriptors(ctx, cals[c["workload"]]) for c in cells])
    return np.column_stack([X["f"], X["aligned"].astype(float), X["guard"], X["duty"], X["c"], X["varying"].astype(float), gp["miss"], gp["tok_s"], gp["power_w"], gp["p99"], desc])


def targets(cells):
    return {"miss": np.array([c["y_miss"] for c in cells]), "tok_s": np.array([c["y_tok_s"] for c in cells]), "power_w": np.array([c["y_power_w"] for c in cells]),
            "p99": np.array([c["y_p99"] for c in cells])}


# ---------------------------------------------------------------- candidates
class Resid:
    """Residual model g_t(x) per target (None = G itself)."""

    def __init__(self, kind):
        self.kind, self.m = kind, {}

    def fit(self, Xf, R):
        if self.kind == "G":
            return self
        from sklearn.preprocessing import StandardScaler
        self.sc = StandardScaler().fit(Xf)
        Z_ = self.sc.transform(Xf)
        for t in TARGETS:
            ok = np.isfinite(R[t])
            if ok.sum() < 8:
                self.m[t] = None
                continue
            y = R[t][ok]
            if self.kind == "HGB":
                from sklearn.ensemble import HistGradientBoostingRegressor
                self.m[t] = HistGradientBoostingRegressor(max_depth=3, max_iter=100, learning_rate=0.1, min_samples_leaf=10, random_state=0).fit(Xf[ok], y)
            elif self.kind == "GP":
                from sklearn.gaussian_process import GaussianProcessRegressor
                from sklearn.gaussian_process.kernels import ConstantKernel, Matern, WhiteKernel
                idx = np.flatnonzero(ok)
                if len(idx) > 150:
                    idx = np.sort(np.random.default_rng(0).choice(idx, 150, replace=False))
                mu, sd = R[t][idx].mean(), R[t][idx].std() + 1e-9
                k = ConstantKernel(1.0) * Matern(length_scale=np.ones(Xf.shape[1]), nu=2.5) + WhiteKernel(0.1)
                self.m[t] = (GaussianProcessRegressor(kernel=k, random_state=0).fit(Z_[idx], (R[t][idx] - mu) / sd), mu, sd)
            elif self.kind == "MLP":
                from sklearn.neural_network import MLPRegressor
                mu, sd = y.mean(), y.std() + 1e-9
                self.m[t] = ([MLPRegressor((32, 32), alpha=1e-3, max_iter=1500, random_state=s).fit(Z_[ok], (y - mu) / sd) for s in range(5)], mu, sd)
        return self

    def predict(self, Xf):
        n = len(Xf)
        if self.kind == "G":
            return {t: np.zeros(n) for t in TARGETS}
        Z_ = self.sc.transform(Xf)
        out = {}
        for t in TARGETS:
            m = self.m.get(t)
            if m is None:
                out[t] = np.zeros(n)
            elif self.kind == "HGB":
                out[t] = m.predict(Xf)
            elif self.kind == "GP":
                out[t] = m[0].predict(Z_) * m[2] + m[1]
            else:
                out[t] = np.mean([net.predict(Z_) for net in m[0]], axis=0) * m[2] + m[1]
        return out


def clip(t, v):
    return np.clip(v, 0.0, 1.0) if t == "miss" else np.maximum(v, 0.0)


def bias_from(ctx, kind_model, cals, adapt_cells):
    """Shrunk mean residual of (y - G - g) over the adaptation cells of ONE workload, per target."""
    if not adapt_cells:
        return {t: 0.0 for t in TARGETS}
    gp, _ = g_predict(ctx, cals, adapt_cells)
    Xf = feature_matrix(ctx, cals, adapt_cells, gp)
    g = kind_model.predict(Xf)
    y = targets(adapt_cells)
    out = {}
    for t in TARGETS:
        r = y[t] - clip(t, gp[t] + g[t])
        r = r[np.isfinite(r)]
        out[t] = float(r.sum() / (len(r) + 1.0)) if len(r) else 0.0
    return out


def predict_cells(ctx, kind_model, cals, cells, bias_by_w):
    gp, _ = g_predict(ctx, cals, cells)
    Xf = feature_matrix(ctx, cals, cells, gp)
    g = kind_model.predict(Xf)
    out = {}
    for t in TARGETS:
        b = np.array([bias_by_w[c["workload"]][t] for c in cells])
        out[t] = clip(t, gp[t] + g[t] + b)
    return out


def calibrations(ctx, pool, k):
    """Per workload: its design-based adaptation cells (from `pool`) and the calibrated grey-box."""
    from w5a_greybox import calibrate, select_adaptation
    A, cals = {}, {}
    for w in sorted({c["workload"] for c in pool}):
        A[w] = select_adaptation([c for c in pool if c["workload"] == w], k)
        cals[w] = calibrate(ctx.P, A[w])
    return A, cals


def fit_candidate(ctx, kind, train, cals):
    gp, _ = g_predict(ctx, cals, train)
    Xf = feature_matrix(ctx, cals, train, gp)
    y = targets(train)
    R = {t: y[t] - gp[t] for t in TARGETS}
    return Resid(kind).fit(Xf, R)


def sigma_inner(ctx, kind, train, k):
    """RMS out-of-fold residual per target: leave one training workload out, same calibration and bias."""
    res = {t: [] for t in TARGETS}
    ws = sorted({c["workload"] for c in train})
    for w in ws:
        sub = [c for c in train if c["workload"] != w]
        held = [c for c in train if c["workload"] == w]
        Asub, cal_sub = calibrations(ctx, sub, k)
        Ah, cal_h = calibrations(ctx, held, k)
        cals = dict(cal_sub, **cal_h)
        model = fit_candidate(ctx, kind, sub, cals)
        bias = {w: bias_from(ctx, model, cals, Ah[w])}
        test = [c for c in held if c not in Ah[w]]
        pred = predict_cells(ctx, model, cals, test, bias)
        y = targets(test)
        for t in TARGETS:
            r = y[t] - pred[t]
            res[t].extend(r[np.isfinite(r)].tolist())
    return {t: float(np.sqrt(np.mean(np.square(res[t])))) if res[t] else float("nan") for t in TARGETS}


def run_fold(ctx, kind, train, test_pool, k, adapt_pool_for_test):
    """Fit on `train`, calibrate each workload from its design-based cells, score on the cells of test_pool that are not adaptation cells."""
    A_tr, cal_tr = calibrations(ctx, train, k)
    A_te, cal_te = calibrations(ctx, adapt_pool_for_test, k)
    cals = dict(cal_tr, **cal_te)
    model = fit_candidate(ctx, kind, train, cals)
    bias = {w: bias_from(ctx, model, cals, A_te[w]) for w in A_te}
    test = [c for c in test_pool if all(c is not a for a in A_te.get(c["workload"], []))]
    pred = predict_cells(ctx, model, cals, test, bias)
    sig = sigma_inner(ctx, kind, train, k)
    return dict(test=test, pred=pred, sigma=sig, model=model, cals=cals, bias=bias)


def fold_metrics(folds):
    """Pool the folds' test cells; per-target errors, classification, coverage, decision metrics."""
    cells = [c for f in folds for c in f["test"]]
    pred = {t: np.concatenate([f["pred"][t] for f in folds]) for t in TARGETS}
    sigma = {t: np.concatenate([np.full(len(f["test"]), f["sigma"][t]) for f in folds]) for t in TARGETS}
    y = targets(cells)
    m = {}
    ok99 = np.isfinite(y["p99"])
    m["n_test"], m["n_p99"], m["n_overloaded_excluded_from_p99"] = len(cells), int(ok99.sum()), int((~ok99).sum())
    m["p99_err"] = float(np.percentile(np.abs(pred["p99"][ok99] - y["p99"][ok99]), 99)) if ok99.any() else float("nan")
    m["p99_mae"] = float(np.mean(np.abs(pred["p99"][ok99] - y["p99"][ok99]))) if ok99.any() else float("nan")
    m["tok_mae"] = float(np.mean(np.abs(pred["tok_s"] - y["tok_s"])))
    m["power_mae"] = float(np.mean(np.abs(pred["power_w"] - y["power_w"])))
    m["miss_mae"] = float(np.mean(np.abs(pred["miss"] - y["miss"])))
    m["miss_class"] = classify(pred["miss"] <= SLO_MISS, y["miss"] <= SLO_MISS)
    m["power_class"] = classify(pred["power_w"] <= BUDGET_W, y["power_w"] <= BUDGET_W)
    m["zero_token_class"] = classify(pred["tok_s"] >= 1.0, y["tok_s"] >= 1.0)
    cov = {}
    for t, sel in (("tok_s", np.ones(len(cells), bool)), ("power_w", np.ones(len(cells), bool)), ("p99", ok99)):
        lo = pred[t] - Z * sigma[t]
        lo = np.maximum(lo, 0.0) if t == "tok_s" else lo
        cov[t] = coverage(y[t][sel], lo[sel], (pred[t] + Z * sigma[t])[sel])
    m["coverage"] = cov
    # decision metrics per held-out stratum (workload x condition)
    regs, bests, picks, ffs = [], [], 0, 0
    for key in sorted({(c["workload"], c["condition"]) for c in cells}):
        idx = [i for i, c in enumerate(cells) if (c["workload"], c["condition"]) == key]
        r = pick_and_score(y["tok_s"][idx], y["miss"][idx], y["power_w"][idx], pred["tok_s"][idx], pred["miss"][idx], pred["power_w"][idx], sigma["power_w"][idx][0])
        regs.append(r["regret"]); bests.append(r["best"])
        picks += r["pick"] is not None
        ffs += bool(r["false_feasible"])
    m["strata"], m["strata_with_feasible_best"] = len(regs), int(sum(b > 0 for b in bests))
    m["picks"], m["false_feasible_picks"] = picks, ffs
    m["false_feasible_rate"] = ffs / picks if picks else float("nan")
    m["regret_sum"], m["best_sum"] = float(sum(regs)), float(sum(bests))
    m["regret_rel"] = float(sum(regs) / sum(bests)) if sum(bests) > 0 else float("nan")
    m["sigma_hat_mean"] = {t: float(np.mean(sigma[t])) for t in TARGETS}
    return m


def latency_p99(ctx, kind, fold):
    """Predict + decide for the 70 settings (4 targets, intervals, decision), p99 over 300 repetitions after 50 warm-ups."""
    from w5a_greybox import grid70, predict
    w = "llama32_3b"
    cal = fold["cals"][w]
    bias, sig, model = fold["bias"][w], fold["sigma"], fold["model"]
    X = grid70(9.0, ctx.P)
    desc = np.array(descriptors(ctx, cal))

    def once():
        g = predict(ctx.P, cal, X)
        gp = {t: (np.where(np.isnan(g[t]), PERIOD, g[t]) if t == "p99" else g[t]) for t in TARGETS}
        Xf = np.column_stack([X["f"], X["aligned"].astype(float), X["guard"], X["duty"], X["c"], X["varying"].astype(float), gp["miss"], gp["tok_s"], gp["power_w"], gp["p99"], np.tile(desc, (len(X["f"]), 1))])
        r = model.predict(Xf)
        pred = {t: clip(t, gp[t] + r[t] + bias[t]) for t in TARGETS}
        ok = (pred["miss"] <= SLO_MISS) & (pred["power_w"] + Z * sig["power_w"] <= BUDGET_W) & (pred["tok_s"] >= 1.0)
        return int(np.argmax(np.where(ok, pred["tok_s"], -np.inf))) if ok.any() else None
    for _ in range(50):
        once()
    t = []
    for _ in range(300):
        t0 = time.perf_counter(); once(); t.append(time.perf_counter() - t0)
    return float(np.percentile(t, 99))


def lowo(ctx, kind, cells, k):
    folds = []
    for w in sorted({c["workload"] for c in cells}):
        train = [c for c in cells if c["workload"] != w]
        held = [c for c in cells if c["workload"] == w]
        f = run_fold(ctx, kind, train, held, k, held)
        f["held_out"] = w
        folds.append(f)
    return folds


def loco(ctx, kind, cells, k):
    folds = []
    for cond in sorted({c["condition"] for c in cells}, key=lambda s: (s.startswith("var"), int(s.replace("var", "").replace("c", "")))):
        train = [c for c in cells if c["condition"] != cond]
        held = [c for c in cells if c["condition"] == cond]
        f = run_fold(ctx, kind, train, held, k, train)          # calibration cells come from the TRAINING conditions of each workload; the held-out condition is not adapted on
        f["held_out"] = cond
        folds.append(f)
    return folds


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--kinds", default=",".join(ORDER))
    a = ap.parse_args()
    warnings.filterwarnings("ignore")
    ctx = Ctx()
    cells = load_cells()
    res = dict(notes=IMPLEMENTATION_NOTES, candidates={})
    for kind in a.kinds.split(","):
        t0 = time.time()
        r = {}
        for k in (3, 1):
            folds = lowo(ctx, kind, cells, k)
            r[f"lowo_k{k}"] = dict(pooled=fold_metrics(folds), per_fold={f["held_out"]: fold_metrics([f]) for f in folds})
            if k == 3:
                r["latency_p99_s"] = latency_p99(ctx, kind, next(f for f in folds if f["held_out"] == "llama32_3b"))
        lf = loco(ctx, kind, cells, 3)
        r["loco_k3"] = dict(pooled=fold_metrics(lf), per_condition={f["held_out"]: fold_metrics([f]) for f in lf})
        r["seconds"] = round(time.time() - t0, 1)
        res["candidates"][kind] = r
        print(kind, "done in", r["seconds"], "s", flush=True)
    ms = []
    for kind, r in res["candidates"].items():
        p = r["lowo_k3"]["pooled"]
        ms.append(dict(name=kind, false_feasible_rate=p["false_feasible_rate"], coverage=p["coverage"], latency_p99_s=r["latency_p99_s"], p99_err=p["p99_err"], tok_mae=p["tok_mae"],
                       power_mae=p["power_mae"], regret_rel=p["regret_rel"]))
    res["selection"] = select(ms, ORDER)
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.with_suffix(".json").write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")
    print(json.dumps(res["selection"], indent=1, default=float))


if __name__ == "__main__":
    main()
