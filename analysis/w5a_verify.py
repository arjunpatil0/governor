"""Verify W5a data against the frozen cell list (tests/test_w5a_verify.py).
   python analysis/w5a_verify.py --list data/w5a/cell_list.json --root data/w5a --sessions 1 2 3 [--out data/w5a/verification.json]
problems = the data set is not what the registration says (missing/extra cells, incidents, manifest mismatch, sessions that differ in armoury mode / exe / git head);
flags = per-cell conditions to look at (not necessarily errors): clock not applied, partial offload, frames != 1800, abandoned frames, ring drops, SM clock far from the request, hot GPU."""
import argparse
import hashlib
import json
import math
from pathlib import Path

EXPECTED_FRAMES, SM_TOL_MHZ, TEMP_WARN_C = 1800, 30.0, 83


def _num(x):
    return isinstance(x, (int, float)) and not (isinstance(x, float) and math.isnan(x))


def verify(list_path, root, sessions):
    root = Path(root)
    listing = json.loads(Path(list_path).read_text(encoding="utf-8"))["cells"]
    problems, flags, n_cells, metas = [], [], 0, {}
    for s in sessions:
        sd = root / f"session{s}"
        want = {c["cell_id"]: c for c in listing if c["session"] == s}
        have = {p.parent.name for p in sd.glob("*/cell.json")}
        for cid in sorted(set(want) - have):
            problems.append(f"session{s}: missing cell {cid}")
        for cid in sorted(have - set(want)):
            problems.append(f"session{s}: cell {cid} is not in the frozen list")
        for p in sorted(sd.glob("*/incident.json")):
            problems.append(f"session{s}: incident file {p.parent.name}")
        meta_p = sd / "meta.json"
        metas[s] = json.loads(meta_p.read_text(encoding="utf-8")) if meta_p.exists() else {}
        if not meta_p.exists():
            problems.append(f"session{s}: meta.json missing")
        man_p = sd / "manifest.json"
        if not man_p.exists():
            problems.append(f"session{s}: manifest.json missing")
        else:
            man = {k.replace(chr(92), "/"): v for k, v in json.loads(man_p.read_text(encoding="utf-8")).items()}     # run.py writes the Windows separator
            on_disk = {str(p.relative_to(sd)).replace(chr(92), "/"): p for p in sd.rglob("*") if p.is_file() and p.name != "manifest.json"}
            for k in sorted(set(man) - set(on_disk)):
                problems.append(f"session{s}: manifest lists {k} but the file is gone")
            for k in sorted(set(on_disk) - set(man)):
                problems.append(f"session{s}: manifest lacks {k}")
            for k in sorted(set(man) & set(on_disk)):
                if hashlib.sha256(on_disk[k].read_bytes()).hexdigest() != man[k]:
                    problems.append(f"session{s}: manifest sha256 mismatch for {k}")
        for cid in sorted(have & set(want)):
            r = json.loads((sd / cid / "cell.json").read_text(encoding="utf-8"))
            n_cells += 1
            if r.get("session") != s or r.get("order") != want[cid]["order"]:
                problems.append(f"session{s}: {cid} session/order differ from the list")
            if r.get("clock_ok") is not True:
                flags.append(f"{cid}: clock_ok={r.get('clock_ok')} ({r.get('clock_response')})")
            em = r.get("exec_mode") or ""
            if "offloaded=" not in em or len(set(em.split("offloaded=")[1].split()[0].split("/"))) != 1 or "governed=1" not in em:
                flags.append(f"{cid}: exec_mode not full offload/governed: {em}")
            if r.get("frames") != EXPECTED_FRAMES:
                flags.append(f"{cid}: frames={r.get('frames')}")
            if r.get("abandoned"):
                flags.append(f"{cid}: abandoned={r.get('abandoned')}")
            if r.get("ring_dropped"):
                flags.append(f"{cid}: ring_dropped={r.get('ring_dropped')}")
            clk, sm = r.get("clock"), r.get("sm_mhz_median")
            if clk != "unlocked" and _num(sm) and abs(sm - float(clk)) > SM_TOL_MHZ:
                flags.append(f"{cid}: sm_mhz_median {sm:.0f} vs requested {clk}")
            if not _num(sm):
                flags.append(f"{cid}: sm_mhz_median missing")
            if _num(r.get("temp_after_c")) and r["temp_after_c"] >= TEMP_WARN_C:
                flags.append(f"{cid}: temp_after_c={r['temp_after_c']}")
    first = metas[sessions[0]] if sessions else {}
    for s in sessions[1:]:
        for key in ("armoury_mode", "exe_sha256", "git_head"):
            if metas[s].get(key) != first.get(key):
                problems.append(f"sessions differ in {key}: session{sessions[0]}={first.get(key)} session{s}={metas[s].get(key)}")
    for s in sessions:
        if metas[s].get("chrome_running"):
            problems.append(f"session{s}: chrome_running in meta.json")
    return dict(ok=not problems and not flags, cells=n_cells, expected=sum(1 for c in listing if c["session"] in sessions), problems=problems, flags=flags)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", required=True); ap.add_argument("--root", required=True)
    ap.add_argument("--sessions", type=int, nargs="+", required=True); ap.add_argument("--out", default=None)
    a = ap.parse_args()
    rep = verify(a.list, a.root, a.sessions)
    print(f"cells {rep['cells']}/{rep['expected']}  problems {len(rep['problems'])}  flags {len(rep['flags'])}")
    for x in rep["problems"]:
        print("PROBLEM", x)
    for x in rep["flags"]:
        print("FLAG", x)
    if a.out:
        Path(a.out).write_text(json.dumps(rep, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
