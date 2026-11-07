"""v2 sprint 1, step 4 (docs/V2_SPRINT1_PAUSE_COST.md): SIMULATION ESTIMATE of what pausable decode would buy. No hardware. The measured group shares and per-boundary cost of
tools/pause_analyze.py (summary.json) go into sim/plant_pausable.py, in which a bg token is G groups that each start only where they fit the slack. Two policies of the existing simulator are run on the S1
and S5 scenes of the evaluation (60 s, 60 W budget, evaluation seeds 200-204): the best fixed setting (aligned, tuned global setting of the budget study) and the learned governor (d'B3 constants of
sim_tuned_round3.json). Medians over the seeds. S5 uses the sim's fp16-profile background (the unseen, longer-token model); the group shares measured on the 3B are applied to it unchanged.
   python tools/pause_payoff.py data/v2/s1_pause/<stamp>"""
import dataclasses
import json
import statistics as st
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from sim.params import load_params  # noqa: E402
from sim.plant import summarise  # noqa: E402
from sim.plant_pausable import PausablePlant  # noqa: E402
from sim.run import load_tuned, make_controller  # noqa: E402
from sim.scenarios import build  # noqa: E402

SEEDS = (200, 201, 202, 203, 204)
GS = (1, 2, 4, 7, 14, 28)
V1_GOVERNOR = {"S1": (19.4, 1.72), "S5": (7.8, 4.72)}          # registered-evaluation medians of the v1 governor (docs/W5B_RESULTS.md observation 2, data/w5b/eval_descriptive.md): tok/s, late %


def tuned_all():
    t = load_tuned()
    for f in ("sim_tuned_budget.json", "sim_tuned_round3.json"):
        t.update(json.loads((ROOT / "data" / f).read_text(encoding="utf-8")))
    return t


def main(d):
    res = json.loads((Path(d) / "summary.json").read_text())["results"]
    P, tuned = load_params(ROOT), tuned_all()
    # S5-like: the evaluation's S5 uses the held-out 8B. The simulator's own S5 profile ('fp16') runs at the 3B's speed (about 100 tok/s at 1800 MHz), so it is not 8B-like. Here the 3B curve is scaled to the
    # 8B's alone speed (46.4 against 96.53 tok/s, the model constants of docs/dashboard_reference.html; the 8B speed there is itself an estimate) with the 3B's power curve.
    P.profiles["llama31_8b"] = (P._bg_x, P._bg_tok * (46.4 / 96.53), P._bg_p)
    out = {}
    print(f"{'scene':<5}{'policy':<14}{'G':>3}{'tok/s':>8}{'late %':>8}")
    for scene in ("S1", "S5"):
        for pol in ("g'B", "d'B3"):
            for G in GS:
                if G == 1:
                    fracs, bms = (1.0,), 0.0
                else:
                    gm = res[f"G{G}"]["group_gpu_ms_median"]
                    v = [gm[str(k)] if str(k) in gm else gm[k] for k in range(G)]
                    fracs, bms = tuple(x / sum(v) for x in v), max(res[f"G{G}"]["per_boundary_us"], 0.0) / 1000.0
                rows = []
                for s in SEEDS:
                    ctrl = make_controller(P, pol, scene, tuned, budget=60.0)
                    sc = build(scene)
                    if scene == "S5":
                        sc.bg = dataclasses.replace(sc.bg, profile="llama31_8b")
                    rows.append(summarise(PausablePlant(P, sc, seed=s, fracs=fracs, boundary_ms=bms).run(ctrl)))
                tok, late = st.median(r["bg_tok_s"] for r in rows), 100.0 * st.median(r["miss_frac"] for r in rows)
                out[f"{scene}|{pol}|G{G}"] = dict(tok_s=tok, late_pct=late, boundary_ms=bms)
                print(f"{scene:<5}{pol:<14}{G:>3}{tok:>8.1f}{late:>8.2f}")
    out["v1_governor_hardware_medians"] = V1_GOVERNOR
    Path(ROOT / "data" / "v2" / "s1_payoff.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print("v1 governor on hardware (registered medians): S1 %.1f tok/s %.2f%% late, S5 %.1f tok/s %.2f%% late" % (*V1_GOVERNOR["S1"], *V1_GOVERNOR["S5"]))


if __name__ == "__main__":
    main(sys.argv[1])
