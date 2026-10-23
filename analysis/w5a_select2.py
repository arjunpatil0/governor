"""W5a model-selection RE-RUN (post hoc, the only one) exactly as registered in plan addendum N (docs/W5A_SELECTION_REDESIGN.md; tests/test_w5a_select2.py).
   python analysis/w5a_select2.py --out data/w5a/selection2          (writes selection2.json; report: python analysis/w5a_select2_report.py)
Reuses the data loading, grey-box, features, folds and adaptation rule of run 1 (analysis/w5a_select.py, w5a_greybox.py). Differences: targets (feasibility classifier, two-part tok/s, power,
in-range p99), cross-conformal intervals in the transformed space, latency on the batched decide path with a 10 ms bound (1 thread), regret on strata with a feasible candidate, exact binomial CIs."""
import argparse
import json
import math
import sys
import time
import warnings
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "analysis"))

TAU, BUDGET_W, SLO_MISS, ORDER = 0.8, 60.0, 0.01, ["G", "HGB", "GP", "MLP"]
LAT_BOUND_S = 10e-3
TARGETS2 = ("feas", "act", "mu", "power_w", "p99r")
BIAS_T = ("mu", "power_w", "p99r")
FALLBACK = "no candidate passes G1-G3: d'B in W5b uses the grey-box ModelController (option B) with the safety shield unchanged; model selection did not discriminate (addendum N section 6)"


# ---------------------------------------------------------------- scoring (tested)
def conformal_q(scores):
    s = np.asarray(scores, float)
    s = np.sort(s[np.isfinite(s)])
    if len(s) == 0:
        return float("nan")
    rank = int(math.ceil((len(s) + 1) * 0.95))
    return float(s[min(rank, len(s)) - 1])


def clopper_pearson(k, n, alpha=0.05):
    if n == 0:
        return float("nan"), float("nan")
    from scipy.stats import beta
    lo = 0.0 if k == 0 else float(beta.ppf(alpha / 2, k, n - k + 1))
    hi = 1.0 if k == n else float(beta.ppf(1 - alpha / 2, k + 1, n - k))
    return lo, hi


def pick2(obs_tok, obs_feas, obs_power, p_feas, p_act, pred_tok, pred_power, q_power, tau=TAU):
    obs_tok, obs_power = np.asarray(obs_tok, float), np.asarray(obs_power, float)
    obs_ok = np.asarray(obs_feas, bool) & (obs_power <= BUDGET_W)
    best = float(obs_tok[obs_ok].max()) if obs_ok.any() else 0.0
    best = best if best >= 1.0 else 0.0
    ok = (np.asarray(p_feas, float) >= tau) & (np.asarray(p_act, float) >= 0.5) & (np.asarray(pred_tok, float) >= 1.0) & (np.asarray(pred_power, float) + np.asarray(q_power, float) <= BUDGET_W)
    if not ok.any():
        return dict(pick=None, best=best, regret=best, false_feasible=None)
    i = int(np.argmax(np.where(ok, pred_tok, -np.inf)))
    if not obs_ok[i]:
        return dict(pick=i, best=best, regret=best, false_feasible=True)
    return dict(pick=i, best=best, regret=max(best - float(obs_tok[i]), 0.0), false_feasible=False)


def regret_summary(rs):
    feas = [r for r in rs if r["best"] > 0]
    picks = [r for r in rs if r["pick"] is not None]
    ff = sum(1 for r in picks if r["false_feasible"])
    return dict(strata_total=len(rs), strata_with_feasible=len(feas), regret_rel=float(sum(r["regret"] for r in feas) / sum(r["best"] for r in feas)) if feas else float("nan"),
                regret_sum=float(sum(r["regret"] for r in feas)), best_sum=float(sum(r["best"] for r in feas)), picks=len(picks), false_feasible_picks=ff,
                false_feasible_pick_rate=ff / len(picks) if picks else float("nan"), false_feasible_pick_ci95=list(clopper_pearson(ff, len(picks))))


def select2(ms, order):
    failed, passing = {}, []
    for m in ms:
        why = []
        if np.isfinite(m["false_feasible_cell_rate"]) and m["false_feasible_cell_rate"] > 0.05:
            why.append(f"G1a false-feasible cells {m['false_feasible_cell_rate'] * 100:.1f}% > 5%")
        if np.isfinite(m["false_feasible_pick_rate"]) and m["false_feasible_pick_rate"] > 0.05:
            why.append(f"G1b false-feasible picks {m['false_feasible_pick_rate'] * 100:.1f}% > 5%")
        for t, c in m["coverage"].items():
            if not (0.90 <= c <= 0.98):
                why.append(f"G2 coverage {t} {c * 100:.1f}% outside 90-98%")
        if not m["latency_p99_s"] <= LAT_BOUND_S:
            why.append(f"G3 latency p99 {m['latency_p99_s'] * 1e3:.2f} ms > 10 ms")
        (failed.__setitem__(m["name"], why) if why else passing.append(m))
    if not passing:
        return dict(selected=None, failed_gates=failed, qualifying=[], fallback=FALLBACK)
    best = {k: min(m[k] for m in passing) for k in ("mu_mae", "power_mae")}
    best_fi = min(m["false_infeasible_rate"] for m in passing)
    best_reg = min(m["regret_rel"] for m in passing)
    qual = [m["name"] for m in passing if all(m[k] <= 1.10 * best[k] + 1e-12 for k in best) and m["false_infeasible_rate"] <= best_fi + 0.10 + 1e-12 and m["regret_rel"] <= best_reg + 0.10 + 1e-12]
    return dict(selected=next((n for n in order if n in qual), None), failed_gates=failed, qualifying=qual, best_errors=best, best_false_infeasible=best_fi, best_regret_rel=best_reg, fallback=None)


# ---------------------------------------------------------------- data, targets, grey-box baseline
import w5a_select as s1  # noqa: E402


def y2(cells):
    feas = np.array([float(c["y_miss"] <= SLO_MISS) for c in cells])
    act = np.array([float(c["bg_tokens"] > 0) for c in cells])
    mu = np.array([math.log(c["bg_tok_s"]) if c["bg_tokens"] > 0 and c["bg_tok_s"] > 0 else float("nan") for c in cells])
    p99 = np.array([c["fg_p99_ms"] if (not c["overloaded"]) and c["fg_p99_ms"] <= 100.0 else float("nan") for c in cells])
    return {"feas": feas, "act": act, "mu": mu, "power_w": np.array([c["y_power_w"] for c in cells]), "p99r": p99}


def g2(ctx, cals, cells):
    gp, _ = s1.g_predict(ctx, cals, cells)
    G = {"feas": (gp["miss"] <= SLO_MISS).astype(float), "act": (gp["tok_s"] > 0).astype(float), "mu": np.log(np.maximum(gp["tok_s"], 0.1)), "power_w": gp["power_w"], "p99r": gp["p99"]}
    return gp, G


class Resid2:
    def __init__(self, kind):
        self.kind, self.m = kind, {}

    def fit(self, Xf, R):
        if self.kind == "G":
            return self
        from sklearn.preprocessing import StandardScaler
        self.sc = StandardScaler().fit(Xf)
        Z_ = self.sc.transform(Xf)
        for t in TARGETS2:
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
            return {t: np.zeros(n) for t in TARGETS2}
        Z_ = self.sc.transform(Xf)
        out = {}
        for t in TARGETS2:
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


def assemble(G, g, bias_by_w, cells):
    out = {}
    for t in TARGETS2:
        v = G[t] + g[t]
        if t in BIAS_T:
            v = v + np.array([bias_by_w[c["workload"]][t] for c in cells])
        out[t] = np.clip(v, 0.0, 1.0) if t in ("feas", "act") else v
    return out


def bias_from2(ctx, model, cals, adapt):
    if not adapt:
        return {t: 0.0 for t in BIAS_T}
    gp, G = g2(ctx, cals, adapt)
    g = model.predict(s1.feature_matrix(ctx, cals, adapt, gp))
    y = y2(adapt)
    out = {}
    for t in BIAS_T:
        r = y[t] - (G[t] + g[t])
        r = r[np.isfinite(r)]
        out[t] = float(r.sum() / (len(r) + 1.0)) if len(r) else 0.0
    return out


def predict2(ctx, model, cals, cells, bias_by_w):
    gp, G = g2(ctx, cals, cells)
    return assemble(G, model.predict(s1.feature_matrix(ctx, cals, cells, gp)), bias_by_w, cells)


def fit2(ctx, kind, train, cals):
    gp, G = g2(ctx, cals, train)
    y = y2(train)
    return Resid2(kind).fit(s1.feature_matrix(ctx, cals, train, gp), {t: y[t] - G[t] for t in TARGETS2})


def conformal_inner(ctx, kind, train, k):
    """Cross-conformal scores per target (mu, power_w): leave one TRAINING workload out, same calibration and bias; |t(y) - t(yhat)| in the transformed space."""
    sc = {"mu": [], "power_w": []}
    for w in sorted({c["workload"] for c in train}):
        sub = [c for c in train if c["workload"] != w]
        held = [c for c in train if c["workload"] == w]
        _, cal_sub = s1.calibrations(ctx, sub, k)
        Ah, cal_h = s1.calibrations(ctx, held, k)
        cals = dict(cal_sub, **cal_h)
        model = fit2(ctx, kind, sub, cals)
        bias = {w: bias_from2(ctx, model, cals, Ah[w])}
        test = [c for c in held if c not in Ah[w]]
        pred, y = predict2(ctx, model, cals, test, bias), y2(test)
        for t in sc:
            r = np.abs(y[t] - pred[t])
            sc[t].extend(r[np.isfinite(r)].tolist())
    return {t: conformal_q(sc[t]) for t in sc}, {t: len(sc[t]) for t in sc}


def run_fold2(ctx, kind, train, test_pool, k, adapt_pool):
    _, cal_tr = s1.calibrations(ctx, train, k)
    A_te, cal_te = s1.calibrations(ctx, adapt_pool, k)
    cals = dict(cal_tr, **cal_te)
    model = fit2(ctx, kind, train, cals)
    bias = {w: bias_from2(ctx, model, cals, A_te[w]) for w in A_te}
    test = [c for c in test_pool if all(c is not a for a in A_te.get(c["workload"], []))]
    q, nq = conformal_inner(ctx, kind, train, k)
    return dict(test=test, pred=predict2(ctx, model, cals, test, bias), q=q, n_scores=nq, model=model, cals=cals, bias=bias)


def lowo2(ctx, kind, cells, k):
    out = []
    for w in sorted({c["workload"] for c in cells}):
        held = [c for c in cells if c["workload"] == w]
        f = run_fold2(ctx, kind, [c for c in cells if c["workload"] != w], held, k, held)
        f["held_out"] = w
        out.append(f)
    return out


def loco2(ctx, kind, cells, k):
    out = []
    for cond in sorted({c["condition"] for c in cells}, key=lambda s: (s.startswith("var"), int(s.replace("var", "").replace("c", "")))):
        train = [c for c in cells if c["condition"] != cond]
        f = run_fold2(ctx, kind, train, [c for c in cells if c["condition"] == cond], k, train)
        f["held_out"] = cond
        out.append(f)
    return out


# ---------------------------------------------------------------- metrics
def fold_metrics2(folds):
    cells = [c for f in folds for c in f["test"]]
    pred = {t: np.concatenate([f["pred"][t] for f in folds]) for t in TARGETS2}
    q = {t: np.concatenate([np.full(len(f["test"]), f["q"][t]) for f in folds]) for t in ("mu", "power_w")}
    y = y2(cells)
    tok, power, feas = np.array([c["y_tok_s"] for c in cells]), y["power_w"], y["feas"].astype(bool)
    act = np.isfinite(y["mu"])
    m = dict(n_test=len(cells), n_active=int(act.sum()), n_feasible=int(feas.sum()), conformal_q={t: [float(f["q"][t]) for f in folds] for t in ("mu", "power_w")})
    ok = pred["feas"] >= TAU
    cl = s1.classify(ok, feas)
    m["feas_class_tau"] = cl
    m["false_feasible_cell_rate"] = cl["false_feasible_of_predicted_feasible"]
    m["false_feasible_cell_ci95"] = list(clopper_pearson(cl["false_feasible"], int(ok.sum())))
    m["false_infeasible_rate"] = cl["false_infeasible_of_observed_feasible"]
    m["feas_class_0.5"] = s1.classify(pred["feas"] >= 0.5, feas)
    m["active_class"] = s1.classify(pred["act"] >= 0.5, act)
    m["mu_mae"] = float(np.mean(np.abs(pred["mu"][act] - y["mu"][act]))) if act.any() else float("nan")
    m["tok_median_rel_err"] = float(np.median(np.abs(np.exp(pred["mu"][act]) - tok[act]) / tok[act])) if act.any() else float("nan")
    m["power_mae"] = float(np.mean(np.abs(pred["power_w"] - power)))
    m["power_class"] = s1.classify(pred["power_w"] <= BUDGET_W, power <= BUDGET_W)
    inr = np.isfinite(y["p99r"])
    m["p99_in_range_mae"], m["n_p99_in_range"] = (float(np.mean(np.abs(pred["p99r"][inr] - y["p99r"][inr]))) if inr.any() else float("nan")), int(inr.sum())
    m["coverage"] = dict(mu=float(np.mean(np.abs(pred["mu"][act] - y["mu"][act]) <= q["mu"][act])) if act.any() else float("nan"), power_w=float(np.mean(np.abs(pred["power_w"] - power) <= q["power_w"])))
    rs = []
    for key in sorted({(c["workload"], c["condition"]) for c in cells}):
        idx = [i for i, c in enumerate(cells) if (c["workload"], c["condition"]) == key]
        rs.append(pick2(tok[idx], feas[idx], power[idx], pred["feas"][idx], pred["act"][idx], np.exp(pred["mu"][idx]), pred["power_w"][idx], q["power_w"][idx]))
    m.update(regret_summary(rs))
    return m


def latency2(ctx, kind, fold):
    """Batched decide path for the 70 settings (state: 3B, c9): grey-box + features + the five residual models + bias + conformal margin + decision. p99 over 300 repetitions after 50 warm-ups."""
    from threadpoolctl import threadpool_limits
    from w5a_greybox import grid70, predict
    cal, bias, model, q = fold["cals"]["llama32_3b"], fold["bias"]["llama32_3b"], fold["model"], fold["q"]
    X = grid70(9.0, ctx.P)
    desc = np.array(s1.descriptors(ctx, cal))

    def once():
        g = predict(ctx.P, cal, X)
        p99 = np.where(np.isnan(g["p99"]), s1.PERIOD, g["p99"])
        G = {"feas": (g["miss"] <= SLO_MISS).astype(float), "act": (g["tok_s"] > 0).astype(float), "mu": np.log(np.maximum(g["tok_s"], 0.1)), "power_w": g["power_w"], "p99r": p99}
        Xf = np.column_stack([X["f"], X["aligned"].astype(float), X["guard"], X["duty"], X["c"], X["varying"].astype(float), g["miss"], g["tok_s"], g["power_w"], p99, np.tile(desc, (len(X["f"]), 1))])
        r = model.predict(Xf)
        p = {}
        for t in TARGETS2:
            v = G[t] + r[t] + (bias[t] if t in BIAS_T else 0.0)
            p[t] = np.clip(v, 0.0, 1.0) if t in ("feas", "act") else v
        ok = (p["feas"] >= TAU) & (p["act"] >= 0.5) & (np.exp(p["mu"]) >= 1.0) & (p["power_w"] + q["power_w"] <= BUDGET_W)
        return int(np.argmax(np.where(ok, p["mu"], -np.inf))) if ok.any() else None

    def measure():
        for _ in range(50):
            once()
        t = []
        for _ in range(300):
            t0 = time.perf_counter(); once(); t.append(time.perf_counter() - t0)
        return float(np.percentile(t, 99))
    d = measure()
    with threadpool_limits(limits=1):
        one = measure()
    return dict(one_thread_s=one, default_threads_s=d)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--kinds", default=",".join(ORDER))
    a = ap.parse_args()
    warnings.filterwarnings("ignore")
    ctx = s1.Ctx()
    cells = s1.load_cells()
    res = dict(label="POST HOC re-run under plan addendum N (the only one)", candidates={})
    for kind in a.kinds.split(","):
        t0 = time.time()
        r = {}
        for k in (3, 1):
            folds = lowo2(ctx, kind, cells, k)
            r[f"lowo_k{k}"] = dict(pooled=fold_metrics2(folds), per_fold={f["held_out"]: fold_metrics2([f]) for f in folds})
            if k == 3:
                r["latency"] = latency2(ctx, kind, next(f for f in folds if f["held_out"] == "llama32_3b"))
        lf = loco2(ctx, kind, cells, 3)
        r["loco_k3"] = dict(pooled=fold_metrics2(lf), per_condition={f["held_out"]: fold_metrics2([f]) for f in lf})
        r["seconds"] = round(time.time() - t0, 1)
        res["candidates"][kind] = r
        print(kind, "done in", r["seconds"], "s", flush=True)
    ms = []
    for kind, r in res["candidates"].items():
        p = r["lowo_k3"]["pooled"]
        ms.append(dict(name=kind, false_feasible_cell_rate=p["false_feasible_cell_rate"], false_feasible_pick_rate=p["false_feasible_pick_rate"], coverage=p["coverage"],
                       latency_p99_s=r["latency"]["one_thread_s"], mu_mae=p["mu_mae"], power_mae=p["power_mae"], false_infeasible_rate=p["false_infeasible_rate"], regret_rel=p["regret_rel"]))
    res["selection"] = select2(ms, ORDER)
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.with_suffix(".json").write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")
    print(json.dumps(res["selection"], indent=1, default=float))


if __name__ == "__main__":
    main()
