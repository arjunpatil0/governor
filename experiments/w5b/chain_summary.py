"""End-of-run summary of the unattended T3c chain (scripts/w5b_t3c_chain.ps1; tests/test_w5b_eval.py). Reads the T3c decisions, the frozen constants and the evaluation-trial cells; prints plain lines.
   python experiments/w5b/chain_summary.py --t3c data/w5b/t3c/decisions.json --constants data/w5b/constants.json --sha data/w5b/constants.sha256 --trial data/w5b/eval_trial"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


def summary(t3c, constants, sha, trial):
    L = []
    t3c, constants, sha, trial = Path(t3c), Path(constants), Path(sha), Path(trial)
    if t3c.exists():
        d = json.loads(t3c.read_text(encoding="utf-8"))
        cb = d.get("c_b")
        if cb:
            p = cb["params"]
            L.append(f"c'B (T3c, full 10-combination grid): target {p['target']}, ki {p['ki']}; rule met {cb['rule_met']}; winner at the lowest target of the grid {cb.get('at_grid_edge')}; "
                     f"mean miss {cb['mean_miss'] * 100:.2f}%, {cb['mean_tok_s']:.1f} tok/s, {cb['mean_power_w']:.1f} W")
        h = d.get("headroom")
        if h:
            L.append(f"power headroom (T3b data): {h['w']:.2f} W = p95(counter - sampled) {h['sensor_p95_w']:.2f} W + p95(counter above the steady target) {h['spread_p95_w']:.2f} W; steering target {60.0 - h['w']:.2f} W at 60 W")
        dh = d.get("d_b_headroom")
        if dh:
            L.append(f"d'B at margin {dh['margin']} WITH the headroom (6 cells): mean miss {dh['mean_miss'] * 100:.2f}%, {dh['mean_tok_s']:.1f} tok/s, {dh['mean_power_w']:.1f} W - the <= 1% margin rule "
                     f"{'still holds' if dh['rule_holds'] else 'does NOT hold (the headroom is kept and this is reported, no further tuning)'}")
    else:
        L.append(f"no T3c decisions at {t3c}")
    if constants.exists():
        c = json.loads(constants.read_text(encoding="utf-8"))
        g = {k: (v and v.get("sid")) for k, v in c.get("g_b", {}).items()}
        L.append(f"frozen constants: c0 {c['c0']} ms, g'B {g}, c'B-T3b (primary) {c.get('c_b_t3b')}, c'B-T3c {c.get('c_b_t3c')}, d'B {c['d_b']}, headroom {c.get('headroom', {}).get('w')} W")
        L.append("sha256 of data/w5b/constants.json: " + (sha.read_text(encoding="utf-8").strip() if sha.exists() else "(not written)"))
    cells = trial / "trial" / "cells"
    if cells.exists():
        for cj in sorted(cells.glob("*/cell.json")):
            x = json.loads(cj.read_text(encoding="utf-8"))
            m = x["metrics"]
            L.append(f"trial {x['id']}: {m.get('tok_s', float('nan')):.1f} tok/s, miss {m.get('miss', float('nan')):.3f}, counter {m.get('power_w', float('nan')):.1f} W / sampled {m.get('power_sampled_w', float('nan')):.1f} W, "
                     f"energy reads in the loop {m.get('gov_reads')}, source {m.get('power_source')}")
    else:
        L.append("no evaluation-trial cells found")
    return L


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--t3c", required=True); ap.add_argument("--constants", required=True); ap.add_argument("--sha", required=True); ap.add_argument("--trial", required=True)
    a = ap.parse_args()
    print("\n".join(summary(a.t3c, a.constants, a.sha, a.trial)))


if __name__ == "__main__":
    main()
