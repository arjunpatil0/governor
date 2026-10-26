"""Integrity check of finished evaluation blocks (addenda O-5, O-6, O-7). It reads NO outcome (no miss fraction, no throughput): only completeness and measurement integrity.
   python experiments/w5b/eval_integrity.py --out data/w5b/eval --blocks 4 9 --constants data/w5b/constants.json --constants-sha256 <hash>
A block rerun under a new number (evaluate.py --as-block) is checked against the cells of the seed list recorded in its block.json. A discarded block is reported as a flag with its count of measured cells.
Checks (a failing cell is named): the constants file hash (and the hash in every session meta); every block complete (block.json) with exactly the cells eval_lib composes and a cell.json each; no incident files; governed cells (c'B, d'B, eB) on the sampled power source with gov_reads = 0; counter vs sampled power within 15% in every cell; full GPU offload in every cell; the per-tick log and the 0.5 s power
trace of every governed cell present and long enough (evaluate._per_tick_problems); results.csv row count. Flags (not failures): thermal event reasons, clock not confirmed, ring drops, abandoned frames."""
import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "experiments" / "w5b")); sys.path.insert(0, str(ROOT / "experiments" / "w5a"))
import eval_lib as el  # noqa: E402
import evaluate  # noqa: E402

GOVERNED = ("cB", "dB", "eB")


def check_session(out, blocks, constants_path, expected_sha):
    out = Path(out)
    problems, flags, n = [], [], 0
    sha = hashlib.sha256(Path(constants_path).read_bytes()).hexdigest()
    if sha != expected_sha:
        problems.append(f"constants file hash {sha} is not the frozen one {expected_sha}")
    const = json.loads(Path(constants_path).read_text(encoding="utf-8"))
    for mp in sorted((out / "sessions").glob("*/meta.json")):
        h = json.loads(mp.read_text(encoding="utf-8")).get("constants_sha256")
        if h != expected_sha:
            problems.append(f"session meta {mp.parent.name}: constants hash {h} differs from the frozen one")
    for dd in sorted((out / "discarded").glob("*")) if (out / "discarded").exists() else []:
        flags.append(f"discarded block {dd.name}: {len(list(dd.glob('cells/*/cell.json')))} measured cells (kept, not counted; the block is rerun under a new number)")
    for b in blocks:
        bdir = out / f"block{b:02d}"
        if not (bdir / "block.json").exists():
            problems.append(f"block {b} is not complete (no block.json)")
        seed = b
        if (bdir / "block.json").exists():                       # a block rerun under a new number runs the seed list (and cells) of the block it replaces
            seed = json.loads((bdir / "block.json").read_text(encoding="utf-8")).get("seed_block", b)
        want = {c["id"] for c in el.block_cells(b, const, seed_block=seed)}
        have = {p.name for p in (bdir / "cells").glob("*")} if (bdir / "cells").exists() else set()
        for cid in sorted(want - have):
            problems.append(f"cell {cid}: missing in block {b}")
        for cid in sorted(have - want):
            problems.append(f"cell {cid}: not part of block {b} as composed")
        for cid in sorted(want & have):
            cd = bdir / "cells" / cid
            if (cd / "incident.json").exists():
                problems.append(f"cell {cid}: incident.json present")
            if not (cd / "cell.json").exists():
                problems.append(f"cell {cid}: cell.json missing")
                continue
            n += 1
            d = json.loads((cd / "cell.json").read_text(encoding="utf-8"))
            m, sp = d["metrics"], d["spec"]
            if sp.get("kind") in GOVERNED:
                if m.get("power_source") != "sampled":
                    problems.append(f"cell {cid}: governed cell power_source {m.get('power_source')}, expected sampled")
                if (m.get("gov_reads") or 0) > 0:
                    problems.append(f"cell {cid}: the Governor loop read the energy counter {m['gov_reads']} times")
                problems += [x.replace(f"{cid}: ", f"cell {cid}: ", 1) for x in evaluate._per_tick_problems(cid, cd / "frames.npz")]
            w, s_ = m.get("power_w"), m.get("power_sampled_w")
            if w is None or s_ is None or w != w or s_ != s_ or abs(w - s_) / max(s_, 1e-9) > 0.15:
                problems.append(f"cell {cid}: counter power {w} W and sampled power {s_} W differ by more than 15% (or are missing)")
            em = m.get("exec_mode") or ""
            if "offloaded=" in em:
                a, c = em.split("offloaded=")[1].split()[0].split("/")
                if a != c:
                    problems.append(f"cell {cid}: not a full GPU offload ({em})")
            else:
                problems.append(f"cell {cid}: no EXEC_MODE line (full offload not confirmed)")
            for key in ("thermal_reason_bits", "ring_dropped", "abandoned"):
                if m.get(key):
                    flags.append(f"cell {cid}: {key} = {m[key]}")
            if m.get("clock_ok") is False:
                flags.append(f"cell {cid}: clock lock not confirmed")
    rc = out / "results.csv"
    if rc.exists():
        with open(rc, encoding="utf-8") as f:
            rows = sum(1 for _ in csv.DictReader(f))
        expect = sum(1 for p in out.glob("block*/block.json") for _ in (p.parent / "cells").glob("*/cell.json"))
        if rows != expect:
            problems.append(f"results.csv has {rows} rows, the complete blocks hold {expect} cells")
    else:
        problems.append("results.csv missing")
    return dict(ok=not problems, problems=problems, flags=flags, n_cells=n)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True); ap.add_argument("--blocks", type=int, nargs="+", required=True)
    ap.add_argument("--constants", required=True); ap.add_argument("--constants-sha256", required=True)
    a = ap.parse_args()
    r = check_session(a.out, a.blocks, a.constants, a.constants_sha256)
    print(f"INTEGRITY {'PASS' if r['ok'] else 'FAIL'}: blocks {a.blocks}, {r['n_cells']} cells checked, {len(r['problems'])} problems, {len(r['flags'])} flags")
    for x in r["problems"]:
        print("  problem:", x)
    for x in r["flags"]:
        print("  flag:", x)
    raise SystemExit(0 if r["ok"] else 1)


if __name__ == "__main__":
    main()
