"""Break-even lambda between the simple design e (aligned + idle clock drop) and each dynamic controller, from the follow-up evaluation CSV (simulation only).
lambda* = (tok_e - tok_x) / (P_e - P_x): for lambda above it, the lower-power controller x has the higher tok/s - lambda*W. Medians over seeds that meet the SLO."""
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def breakeven(df, a, b, scenario, jitter):
    x = df[(df.scenario == scenario) & (df.jitter == jitter) & (df.miss_frac <= 0.01)]
    ta, pa = x[x.controller == a].bg_tok_s.median(), x[x.controller == a].power_w.median()
    tb, pb = x[x.controller == b].bg_tok_s.median(), x[x.controller == b].power_w.median()
    return (ta - tb) / (pa - pb) if pa != pb else float("nan"), ta, pa, tb, pb


def main():
    df = pd.read_csv(ROOT / "data" / "w45_sim_followup.csv")
    L = ["# Break-even lambda (tok/s per W) between e and the dynamic aligned controllers (SIMULATION ONLY; medians over SLO-holding seeds)", "",
         "x beats e on tok/s - lambda W iff lambda > lambda*. Source: data/w45_sim_followup.csv.", "", "| jitter | scenario | x | tok/s e | W e | tok/s x | W x | lambda* |", "|---|---|---|---|---|---|---|---|"]
    for jit in (False, True):
        for scn in ("S1", "S1d", "S4"):
            for x in ("c'", "d'"):
                lam, te, pe, tx, px = breakeven(df, "e", x, scn, jit)
                L.append(f"| {jit} | {scn} | {x} | {te:.2f} | {pe:.2f} | {tx:.2f} | {px:.2f} | {lam:.3f} |")
    (ROOT / "data" / "w45_sim_breakeven.md").write_text("\n".join(L), encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    main()
