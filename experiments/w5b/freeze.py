"""Freeze the tuned constants of the evaluation (plan addendum O-6 section 5): reads the decisions of the tuning sittings and writes data/w5b/constants.json, which is then COMMITTED; the evaluation runner
refuses a constants file whose sha256 differs from the one given on its command line (like the W5a cell list).
   python experiments/w5b/freeze.py --tuning data/w5b/tuning/decisions.json --t3b data/w5b/t3b/decisions.json --t3c data/w5b/t3c/decisions.json --out data/w5b/constants.json
c0 and g'B come from the T1-T3 sitting, d'B's margin from T3b, c'B's constants from T3c (the full 10-combination grid). Rule flags are recorded, not hidden."""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def sha256_file(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def build_constants(tuning, t3b, t3c, out):
    t, b, c = (json.loads(Path(x).read_text(encoding="utf-8")) for x in (tuning, t3b, t3c))
    g = {k: (None if v is None else v["setting"]) for k, v in t["g_b"].items()}
    cb = c["c_b"]["params"]
    git = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    const = dict(c0=t["c0"], g_b=g, c_b=dict(target=cb["target"], ki=cb["ki"], guard0=cb.get("guard0", 0.5), gmin=cb.get("gmin", 0.3)), d_b=dict(margin=b["d_b"]["margin"]), power_source="sampled",
                 rules=dict(c_b_rule_met=c["c_b"]["rule_met"], c_b_at_grid_edge=c["c_b"].get("at_grid_edge"), d_b_rule_met=b["d_b"]["rule_met"],
                            g_b_feasible_cells={k: (None if v is None else v.get("feasible_cells")) for k, v in t["g_b"].items()}),
                 sources={f"{Path(x).parent.name}/{Path(x).name}": sha256_file(x) for x in (tuning, t3b, t3c)}, git_head=git)
    Path(out).write_text(json.dumps(const, indent=1), encoding="utf-8")
    return const


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tuning", required=True); ap.add_argument("--t3b", required=True); ap.add_argument("--t3c", required=True); ap.add_argument("--out", required=True)
    a = ap.parse_args()
    const = build_constants(a.tuning, a.t3b, a.t3c, a.out)
    print(json.dumps(const, indent=1))
    print("sha256 of", a.out, "=", sha256_file(a.out), "(commit the file, then pass this hash to evaluate.py --constants-sha256)")


if __name__ == "__main__":
    main()
