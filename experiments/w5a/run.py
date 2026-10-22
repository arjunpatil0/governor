"""W5a data collection runner (registered in experiments/w5_governor.yaml, stages.W5a_data_collection; no hypothesis of W5b is tested on this data).
One cell = SM clock + pacing configuration + background workload + foreground condition: 5 s warm-up + 30 s measured. The cell list is frozen by an addendum (its sha256 is passed on the command line).
Needs: the admin clock helper running in its own Administrator window (docs/W45_SMOKE_SETUP.md); this script runs in a normal shell. Cells already done in the session directory are skipped (resume).
   python experiments/w5a/run.py --list data/w5a/cell_list.json --list-sha256 <hash> --session 1 --armoury-mode Performance [--limit N]
Writes data/w5a/session<N>/meta.json and <cell_id>/{cell.json, driver.csv, frames.npz}. GPU rec files stay local with a SHA-256 manifest (CLAUDE.md storage rule)."""
import argparse
import dataclasses
import hashlib
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "experiments" / "w4_smoke"))
sys.path.insert(0, str(ROOT / "experiments" / "w5a"))
sys.path.insert(0, str(ROOT / "workloads" / "common"))
sys.path.insert(0, str(ROOT / "telemetry"))
import smoke  # noqa: E402
from actuators.startup_reset import reset_clocks  # noqa: E402
from sim.scenarios import build  # noqa: E402
from telemetry.fg_publisher import FramePublisher  # noqa: E402
from telemetry.ring import SeqBlock, SharedRing  # noqa: E402
from w5a_design import cond_cost_fn  # noqa: E402
from w5a_metrics import ctrl_values, dirty_paths, summarise_cell  # noqa: E402
from workloads.common.exe_warm import ensure_warm, sha256  # noqa: E402
from workloads.foreground.frame_loop import FmaFrameRunner, FrameLoop  # noqa: E402

WARM_S, MEASURE_S = 5.0, 30.0
TEMP_ABORT_C, TEMP_COOL_C, COOL_MIN_S = 85, 55, 20.0
MODELS = ROOT / "data" / "llama" / "models.json"


def refusal(armoury_mode, plugged, listing_sha, expected_sha, porcelain, chrome):
    """Reason the session must not start, or None."""
    if not armoury_mode or not str(armoury_mode).strip():
        return "refused: pass --armoury-mode <the Armoury Crate mode now active> (journal 0021)"
    if plugged is False:
        return "refused: the laptop is on battery (registration: AC power)"
    if listing_sha != expected_sha:
        return f"refused: the cell list hash {listing_sha} is not the frozen one {expected_sha}"
    bad = dirty_paths(porcelain)
    if bad:
        return "refused: the working tree is not clean (commit first): " + ", ".join(bad[:5])
    if chrome:
        return "refused: Chrome is running (close it; the checklist requires it closed)"
    return None


def gpu_temp(nv, h):
    return int(nv.nvmlDeviceGetTemperature(h, nv.NVML_TEMPERATURE_GPU))


def cool_down(nv, h):
    t0 = time.time()
    while time.time() - t0 < COOL_MIN_S or gpu_temp(nv, h) >= TEMP_COOL_C:
        time.sleep(1.0)
        if time.time() - t0 > 300:
            break


def run_cell(w, cal, cl, cell, models, out_dir, nv, h):
    frames, tokens = SharedRing(smoke.nm("fr"), 8192, 3, True), SharedRing(smoke.nm("tk"), 65536, 2, True)
    ctrl, pace = SeqBlock(smoke.nm("ct"), 3, True), SeqBlock(smoke.nm("pc"), 3, True)
    ctrl.write(ctrl_values(cell))
    if cell["clock"] == "unlocked":
        ok_clock = cl.reset()
    else:
        ok_clock = cl.lock(int(cell["clock"]))
    clock_response = cl.last_response
    time.sleep(1.5)                                                        # actuation latency 443 ms + rate limit
    csv_path = out_dir / "driver.csv"
    env = dict(os.environ, PATH=str(smoke.BIN) + ";" + os.environ["PATH"])
    pr = subprocess.Popen([str(smoke.EXE), str(models[cell["workload"]]["path"]), str(smoke.PROMPT), str(csv_path), "-1", str(WARM_S + MEASURE_S + 12), "512", ctrl.name, pace.name, tokens.name, "65536"],
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=env)
    exec_line, res, sm_samples = None, {}, []
    try:
        t_wait = time.time()
        while tokens.write_count == 0:
            if pr.poll() is not None:
                raise RuntimeError("driver exited early: " + pr.stdout.read())
            if time.time() - t_wait > 120:
                raise RuntimeError("driver produced no token within 120 s")
            time.sleep(0.1)
        tokens.read_new()
        smp = smoke.NvmlSampler(); smp.start()
        fg = dataclasses.replace(build("S0").fg, cost_ms=cond_cost_fn(cell["condition"]))
        loop = FrameLoop(fg, FmaFrameRunner(w, cal), FramePublisher(frames, pace))
        t0 = time.perf_counter() + 0.05
        e = {}

        def energy_reader():
            for key, t in (("start", t0 + WARM_S), ("end", t0 + WARM_S + MEASURE_S)):
                while time.perf_counter() < t:
                    time.sleep(0.002)
                e[key] = nv.nvmlDeviceGetTotalEnergyConsumption(h)
        th = threading.Thread(target=energy_reader, daemon=True); th.start()
        temp_before = gpu_temp(nv, h)
        recs = loop.run(duration_s=WARM_S + MEASURE_S, t0=t0)
        th.join(10)
        smp.stop()
        tk, dropped = tokens.read_new()
        temp_after = gpu_temp(nv, h)
        t_sm = np.array(smp.t); sm = np.array(smp.sm)
        win = (t_sm >= t0 + WARM_S) & (t_sm < t0 + WARM_S + MEASURE_S)
        res = summarise_cell(recs, tk[:, 0] if len(tk) else np.array([]), tk[:, 1] if len(tk) else np.array([]), t0, WARM_S, MEASURE_S, e.get("start", 0.0), e.get("end", 0.0), smoke.PERIOD)
        n_aband = int(loop.abandoned)
        res.update(abandoned=n_aband, miss_frac_incl_abandoned=float((res["miss_frac"] * res["frames"] + n_aband) / max(res["frames"] + n_aband, 1)) if res["frames"] else float("nan"),
                   sm_mhz_median=float(np.median(sm[win])) if win.any() else float("nan"), temp_before_c=temp_before, temp_after_c=temp_after, ring_dropped=int(dropped))
        np.savez_compressed(out_dir / "frames.npz", t_sched=[r["t_sched"] for r in recs], lat_ms=[r["lat_ms"] for r in recs], tok_end=tk[:, 0] if len(tk) else [], tok_ms=tk[:, 1] if len(tk) else [], t0=t0)
    finally:
        ctrl.write([0.0, 0.0, 0.5])
        try:
            pr.wait(timeout=45)
        except subprocess.TimeoutExpired:
            pr.kill()
        out_txt = pr.stdout.read() if pr.stdout else ""
        for line in out_txt.splitlines():
            if line.startswith("EXEC_MODE"):
                exec_line = line
        try:
            cl.reset()
        except Exception:                                                  # noqa: BLE001
            pass
    return dict(cell, **res, exec_mode=exec_line, clock_ok=bool(ok_clock), clock_response=clock_response, driver_tail=out_txt.splitlines()[-2:])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", required=True); ap.add_argument("--list-sha256", required=True)
    ap.add_argument("--session", type=int, required=True); ap.add_argument("--armoury-mode", default=None)
    ap.add_argument("--limit", type=int, default=None); ap.add_argument("--out", default=str(ROOT / "data" / "w5a"))
    a = ap.parse_args()
    lst_path = Path(a.list)
    lst_sha = hashlib.sha256(lst_path.read_bytes()).hexdigest()
    import psutil
    from workloads.common import procsnap
    bat = psutil.sensors_battery()
    procs = procsnap.snapshot(interval=1.0)
    porcelain = subprocess.run(["git", "-C", str(ROOT), "status", "--porcelain"], capture_output=True, text=True).stdout
    why = refusal(a.armoury_mode, None if bat is None else bool(bat.power_plugged), lst_sha, a.list_sha256, porcelain, procsnap.chrome_running(procs))
    if why:
        sys.exit(why)
    listing = json.loads(lst_path.read_text(encoding="utf-8"))
    cells = sorted([c for c in listing["cells"] if c["session"] == a.session], key=lambda c: c["order"])
    models = json.loads(MODELS.read_text(encoding="utf-8"))
    for name in {c["workload"] for c in cells}:
        if sha256(Path(models[name]["path"])) != models[name]["sha256"]:
            sys.exit(f"refused: model {name} does not match its registered sha256")
    sdir = Path(a.out) / f"session{a.session}"
    sdir.mkdir(parents=True, exist_ok=True)
    smoke.write_meta(sdir, a.armoury_mode)
    ensure_warm(smoke.EXE, ["m", "p", "o", "-1", "1", "512", smoke.nm("none1"), smoke.nm("none2"), smoke.nm("none3"), "8"], smoke.REGISTRY)
    from workloads.common.w2lib import W2
    import pynvml as nv
    nv.nvmlInit(); h = nv.nvmlDeviceGetHandleByIndex(0)
    w = W2(); cl = smoke.SafeClient(); hb = smoke.Heartbeat(cl); hb.start()
    done = 0
    try:
        reset_clocks(cl, is_admin=False)
        cal = smoke.calibrate(w, cl)
        cl.reset(); time.sleep(1.1)
        (sdir / "calibration.json").write_text(json.dumps(dict(cal=cal, list_sha256=lst_sha, session=a.session, utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))), encoding="utf-8")
        for k, cell in enumerate(cells):
            cdir = sdir / cell["cell_id"]
            if (cdir / "cell.json").exists():
                continue
            if a.limit is not None and done >= a.limit:
                break
            cdir.mkdir(parents=True, exist_ok=True)
            cool_down(nv, h)
            if gpu_temp(nv, h) > TEMP_ABORT_C:
                sys.exit("ABORT: GPU temperature above 85 C")
            t_start = time.time()
            try:
                r = run_cell(w, cal, cl, cell, models, cdir, nv, h)
            except Exception as ex:                                        # noqa: BLE001
                (cdir / "incident.json").write_text(json.dumps(dict(cell=cell, error=f"{type(ex).__name__}: {ex}")), encoding="utf-8")
                print("INCIDENT", cell["cell_id"], ex, flush=True)
                cl.reset(); time.sleep(2)
                continue
            r["wall_s"] = time.time() - t_start
            (cdir / "cell.json").write_text(json.dumps(r, indent=1, default=str), encoding="utf-8")
            done += 1
            print(f"[{k + 1}/{len(cells)}] {cell['cell_id']}: tok/s {r['bg_tok_s']:.1f} miss {r['miss_frac']:.3f} power {r['power_w']:.1f} W sm {r['sm_mhz_median']:.0f} ({r['wall_s']:.0f} s)", flush=True)
    finally:
        hb.stop(); cl.reset(); cl.close()
    manifest = {str(p.relative_to(sdir)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(sdir.rglob("*")) if p.is_file() and p.name != "manifest.json"}
    (sdir / "manifest.json").write_text(json.dumps(manifest, indent=0), encoding="utf-8")
    print(f"session {a.session}: {done} cells run in this call; manifest of {len(manifest)} files written")


if __name__ == "__main__":
    main()
