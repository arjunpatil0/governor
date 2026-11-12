"""Seeded SYNTHETIC run tree for the analyze tests (not data from the machine). Uses only random.Random(seed) so the tree is identical on every platform."""
import json
import random
from pathlib import Path

from tools.realgame import cell as rg_cell
from tools.realgame import run as rg_run

HZ = 10_000_000
HEADER = (Path(__file__).parent / "data" / "pm_sample_synthetic.csv").read_text().splitlines()[0]
WINDOW_S = 10.0
# (spike probability, spike ms, tok/s) per arm
ARM_PARAMS = {"SOLO": (0.0, 0, 0.0), "UNGATED": (0.15, 31.0, 45.0), "PRIO_IDLE": (0.12, 31.0, 40.0), "DUTY50": (0.06, 28.0, 25.0), "IGPU": (0.002, 26.0, 16.0)}


def write_fresh_rehearsal(run_dir, arms=("UNGATED", "PRIO_IDLE", "DUTY50", "IGPU"), status="PASS", timestamp=None, **doc_update):
    """A fresh rehearsal.json (what `run.py --rehearse --run-dir` writes) with every arm PASS, so that main() will start a sweep."""
    import time
    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "rehearsal.json").write_text(json.dumps({"timestamp": time.time() if timestamp is None else timestamp, "rehearsal": True,
                                                        "exe_sha256": {"llm_exe": "sha-a", "llm_exe_vk": "sha-llama_realgame_bench_vk.exe"},
                                                        "presentmon_sha256": rg_cell.PRESENTMON_SHA256_PREREG,
                                                        "model": {"size": 1000, "mtime": 1.0}, "git_head": "abc123",
                                                        "arms": {a: {"status": status, "reasons": []} for a in arms}, **doc_update}))


def write_fresh_clock_check(run_dir, rehearsal=True):
    """A passed, fresh clock_check.json (what `run.py --check-clocks --run-dir` writes) so that main() will start a sweep / LLM-alone run. Also a fresh all-PASS rehearsal.json
    (the sweep refuses without one) unless rehearsal=False."""
    import time
    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    if rehearsal:
        write_fresh_rehearsal(run_dir)
    (run_dir / "clock_check.json").write_text(json.dumps({"status": "passed", "timestamp": time.time(), "helper_present": [], "max_sm_mhz": 2100, "info": {}, "thresholds": {}, "problems": []}))


def _frames_csv(rng, arm, t_open, swap_extra=True):
    p_spike, spike_ms, _ = ARM_PARAMS[arm]
    rows, t = [HEADER], t_open - 3.0                          # capture starts 3 s before the window
    i = 0
    while t < t_open + WINDOW_S + 2.0:
        ft = 16.667 + rng.uniform(-0.05, 0.05)
        if rng.random() < p_spike:
            ft = spike_ms + rng.uniform(0, 4)
        busy = 8.0 + rng.uniform(-0.4, 0.4)
        lat = 1.0 + rng.uniform(0.0, 0.05)
        sc = "0x2" if (swap_extra and i % 97 == 0) else "0x1"
        disp = "NA" if i % 211 == 5 else f"{ft:.3f}"
        rows.append(f"S.exe,1,{sc},D3D11,1,0,0,Flip,Application,{int(round(t * HZ))},{ft:.3f},3,13,{lat:.3f},{busy + 0.2:.3f},{busy:.3f},1,0,20,{disp},0,0,0,NA,NA,NA")
        t += ft / 1000.0
        i += 1
    return "\n".join(rows) + "\n"


def _tokens_csv(rng, tok_s, t_open):
    rows, t = ["t_tok_end_s,dur_ms,kind"], t_open - 0.5
    if tok_s > 0:
        while t < t_open + WINDOW_S + 0.5:
            d = (1.0 / tok_s) * rng.uniform(0.9, 1.1)
            t += d
            rows.append(f"{t:.6f},{d * 1000:.6f},token")
    rows.append(f"{t_open + 3.0:.6f},50.0,reset")
    return "\n".join(rows) + "\n"


def write_cell(d: Path, arm, rep, seed, t_open, prio_readbacks=None):
    d.mkdir(parents=True, exist_ok=True)
    rng = random.Random(seed)
    res = {"arm": arm, "rep": rep, "t_open": t_open, "t_close": t_open + WINDOW_S, "qpc_hz": float(HZ), "power_w": 80.0 + rng.random(), "elevated": False, "sm_clock_mhz_median": 1500,
           "throttle_mask_or": 0, "temp_c": {"start": 60.0, "end": 66.0}, "vram_mb": {"start": 1000.0, "end": 1100.0},
           "shared_gpu_mem_bytes": {"start": 10 * 2**20, "end": 10 * 2**20 + (100 * 2**20 if (arm == "DUTY50" and rep == 1) else 0)}}
    if arm == "LLM_ALONE":
        res["tok_s"] = None
        res["game_absent"] = True
        res["present_modes"] = None
        (d / "llm_tokens.csv").write_text(_tokens_csv(rng, 100.0, t_open))
    else:
        res["present_modes"] = ["Flip"]
        (d / "frames.csv").write_text(_frames_csv(rng, arm, t_open, swap_extra=(arm != "SOLO")))
        if arm != "SOLO":
            (d / "llm_tokens.csv").write_text(_tokens_csv(rng, ARM_PARAMS[arm][2], t_open))
    if prio_readbacks is not None:
        res["prio_readbacks"] = prio_readbacks
    (d / "result.json").write_text(json.dumps(res))


def build_tree(root: Path, seed=11, reps=3, failed_first_attempt=True, prio_readbacks=(0, 0), arms=("UNGATED", "PRIO_IDLE", "DUTY50", "IGPU")):
    root.mkdir(parents=True, exist_ok=True)
    order = rg_run.make_order(seed, reps, arms=arms)
    rg_run.write_run_meta(root, seed=seed, reps=reps, arms=arms, order=order, igpu_dropped_reason=None if "IGPU" in arms else "synthetic: dropped")
    write_cell(root / "llm_alone", "LLM_ALONE", 0, seed * 1000, 5000.0)
    k = 0
    for rep, arms_in_rep in enumerate(order):
        attempts = [1]
        if failed_first_attempt and rep == 0:
            attempts = [1, 2]
            bad = rg_run.cell_dir(root, rep, 1, 0, arms_in_rep[0])
            write_cell(bad, arms_in_rep[0], rep, seed * 77, 6000.0)
            bad2 = rg_run.cell_dir(root, rep, 1, 1, arms_in_rep[1])
            bad2.mkdir(parents=True)
            (bad2 / "FAILED.json").write_text(json.dumps({"error": "synthetic crash"}))
        for attempt in attempts[-1:]:
            for pos, arm in enumerate(arms_in_rep):
                k += 1
                rb = list(prio_readbacks) if arm == "PRIO_IDLE" else None
                write_cell(rg_run.cell_dir(root, rep, attempt, pos, arm), arm, rep, seed * 1000 + k, 10000.0 + 100.0 * k, rb)
            rg_run.noise_marker(root, rep, attempt).write_text(json.dumps({"rep": rep, "attempt": attempt, "ok": True, "checked": True}))
    return order
