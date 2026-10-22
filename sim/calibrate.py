"""Fit the plant's one free parameter, the time-slice share divisor S (each context runs at 1/S of solo speed while both have work), to the A2 SA4
anchor cells. The G-derived value 2 + 2s/q is an independent estimate and is kept as the sensitivity setting. Writes data/sim_calibration.json."""
import dataclasses
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from sim.anchors import ANCHOR_IDS, a2_run  # noqa: E402
from sim.params import load_params  # noqa: E402

GRID = tuple(round(x, 2) for x in np.arange(2.2, 2.81, 0.1))


def fit_share_divisor(P, grid=GRID, seeds=(1, 2)):
    res = {}
    for S in grid:
        Ps = dataclasses.replace(P, share_override=float(S))
        err = [np.log(np.mean([a2_run(Ps, cid, seed=s)["lat_mean_ms"] for s in seeds]) / P.sa4[cid]["lat_mean_ms"]) for cid in ANCHOR_IDS]
        res[S] = float(np.sqrt(np.mean(np.square(err))))
    best = min(res, key=res.get)
    return dict(share_divisor_fit=float(best), rmse_log_by_S={str(k): v for k, v in res.items()}, anchors=list(ANCHOR_IDS), seeds=list(seeds),
                share_divisor_G=P.share_divisor_G, note="rmse of log(sim mean latency / measured mean latency) over the SA4 anchors; fitted S replaces the G-derived 2+2s/q in the plant")


if __name__ == "__main__":
    P = load_params(ROOT)
    out = fit_share_divisor(P)
    (ROOT / "data" / "sim_calibration.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(json.dumps(out, indent=1))
