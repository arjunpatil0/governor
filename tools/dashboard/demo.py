"""Demo launcher: runs ONE scene with a chosen model and manager on the real GPU through the existing hardware executor (experiments/w5b/executors.py HwExecutor, unchanged), with the Governor's telemetry on, so the
dashboard (tools/dashboard/server.py, LIVE mode) can show it as it happens.
   python tools/dashboard/demo.py --scene S1 --model 3b --manager dB --armoury-mode Performance            (about 100 s: set-up, 5 s warm-up, 60 s measured, cool-down)
Needs what a registered cell needs: the admin clock helper running in its own Administrator window, AC power, Armoury mode stated, a clean committed tree (untracked files under data/ are fine), a fresh restart (uptime <= 2 h),
Chrome closed (open the dashboard in Edge or Firefox). The SAME refusal rules as evaluate.py (experiments/w5b/tune.py refusal) apply. The cell is run exactly as an evaluation cell (same cell spec from experiments/w5b/eval_lib
with the frozen constants, same executor); only the model may differ from the registered one, and the id says demo. A DEMO is NEVER registered data: its meta.json says "demo": true and its output goes to
data/dashboard_demos/<utc>_<id>/ (the program refuses any output directory under data/w5b/eval); it appears in the dashboard's REPLAY picker under 'demo' (with the governor's predictions).
Managers: a (nobody), gB (best fixed setting), eB (fixed + idle rule), cBb (simple reacting PI, c'B-T3b), dB (the governor). Scenes: S0 steady, S1 load jumps, S1d slow drift, S2 idle phases, S5 (the scene of the 8B model).
The decision telemetry is OFF everywhere else; here it is switched on by setting Governor.default_telemetry in THIS process only (controllers/runtime.py)."""
import argparse
import hashlib
import json
import os
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "experiments" / "w5b")); sys.path.insert(0, str(ROOT / "experiments" / "w5a"))
sys.path.insert(0, str(ROOT / "experiments" / "w4_smoke")); sys.path.insert(0, str(ROOT / "workloads" / "common")); sys.path.insert(0, str(ROOT / "telemetry"))

MANAGERS = {"a": "a", "gB": "g'B", "eB": "eB", "cBb": "c'B-T3b", "dB": "d'B"}
MODELS = {"1b": "llama32_1b", "3b": "llama32_3b", "phi": "phi35_mini", "8b": "llama31_8b"}
SCENES = ("S0", "S1", "S1d", "S2", "S5")
EVAL_DIR = (ROOT / "data" / "w5b" / "eval").resolve()
DEMO_ROOT = ROOT / "data" / "dashboard_demos"
SESSION_FILE = ROOT / "data" / "dashboard_live" / "session.json"
CONSTANTS = ROOT / "data" / "w5b" / "constants.json"
SHA_FILE = ROOT / "data" / "w5b" / "constants.sha256"


def load_frozen_constants(path=CONSTANTS, sha_file=SHA_FILE):
    p = Path(path)
    sha = hashlib.sha256(p.read_bytes()).hexdigest()
    want = Path(sha_file).read_text(encoding="utf-8").split()[0]
    if sha != want:
        sys.exit(f"refused: the constants file hash {sha} is not the frozen one {want}")
    return json.loads(p.read_text(encoding="utf-8"))


def plan(scene, model, manager, budget_w, const, measure_s=None, stamp=None):
    """The cell spec of a demo: the evaluation's own cell for (scene, manager, budget) with the model swapped, id 'demo_...', demo flag set. Pure; raises ValueError for an unknown choice."""
    import eval_lib as el
    if scene not in SCENES or model not in MODELS or manager not in MANAGERS or float(budget_w) not in (60.0, 35.0):
        raise ValueError(f"unknown demo choice: scene {scene}, model {model}, manager {manager}, budget {budget_w}")
    ctl = MANAGERS[manager]
    tpl = next((c for c in el.block_cells(4, const, seed_block=4) if c["scene"] == scene and c["controller"] == ctl and float(c["budget_w"]) == float(budget_w)), None)
    if tpl is None:
        raise ValueError(f"the evaluation has no cell for scene {scene}, manager {manager}, {budget_w:.0f} W (arm a exists only at 60 W)")
    spec = dict(tpl)
    spec.update(id=f"demo_{scene}_{manager}_{model}_{int(budget_w)}", workload=MODELS[model], demo=True, exploratory=True, block=None)
    if measure_s is not None:
        spec["measure_s"] = float(measure_s)
    stamp = stamp or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return spec, DEMO_ROOT / f"{stamp}_{spec['id']}"


def check_out_dir(out):
    """Demo output must never land in the registered evaluation tree."""
    o = Path(out).resolve()
    if o == EVAL_DIR or EVAL_DIR in o.parents:
        raise ValueError(f"refused: a demo's output must stay out of {EVAL_DIR} (it is not registered data)")
    return o


def session_registry(names, spec, pid=None):
    return dict(names=names, pid=os.getpid() if pid is None else pid, id=spec["id"], scene=spec["scene"], controller=spec["controller"], workload=spec["workload"], budget_w=spec["budget_w"], demo=True,
                started_utc=datetime.now(timezone.utc).isoformat())


def fetch_stats(port):
    try:
        with urllib.request.urlopen(urllib.request.Request(f"http://127.0.0.1:{port}/api/stats", headers={"Host": f"127.0.0.1:{port}"}), timeout=1.0) as r:
            return json.loads(r.read())
    except Exception:                                                        # noqa: BLE001
        return None


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--scene", required=True, choices=SCENES); ap.add_argument("--model", required=True, choices=sorted(MODELS)); ap.add_argument("--manager", required=True, choices=sorted(MANAGERS))
    ap.add_argument("--budget-w", type=float, default=60.0, choices=[60.0, 35.0]); ap.add_argument("--armoury-mode", default=None)
    ap.add_argument("--measure-s", type=float, default=None, help="shorter measured window in seconds (default 60, the registered one)")
    ap.add_argument("--out-root", default=str(DEMO_ROOT)); ap.add_argument("--max-uptime-s", type=float, default=7200.0)
    ap.add_argument("--dashboard-port", type=int, default=8765, help="measure this server's CPU overhead during the run (if it is running)")
    ap.add_argument("--no-telemetry", action="store_true", help="run without the decision telemetry (the dashboard then shows frames, tokens, clock and power only)")
    a = ap.parse_args(argv)
    const = load_frozen_constants()
    spec, out = plan(a.scene, a.model, a.manager, a.budget_w, const, a.measure_s)
    out = check_out_dir(Path(a.out_root) / out.name)
    import subprocess

    import psutil
    from tune import refusal
    from workloads.common import procsnap
    bat = psutil.sensors_battery()
    porcelain = subprocess.run(["git", "-C", str(ROOT), "status", "--porcelain"], capture_output=True, text=True).stdout
    why = refusal(a.armoury_mode, None if bat is None else bool(bat.power_plugged), time.time() - psutil.boot_time(), a.max_uptime_s, porcelain, procsnap.chrome_running(procsnap.snapshot(interval=1.0)))
    if why:
        sys.exit(why)
    import executors
    import smoke
    from controllers.runtime import Governor
    from telemetry.decision_block import DECISION_FIELDS, DecisionBlock, DecisionPublisher

    if a.measure_s is not None:
        executors.MEASURE_S = float(a.measure_s)                             # module constant read at run time by HwExecutor; demo cells only

    class LoggingPublisher(DecisionPublisher):
        def __init__(self, block):
            super().__init__(block)
            self.rows = []

        def publish(self, ctl, action, t_s):
            super().publish(ctl, action, t_s)
            self.rows.append([self.last[f] for f in DECISION_FIELDS])

    class DemoExecutor(executors.HwExecutor):
        """HwExecutor, unchanged, plus: the ring and block names are published for the dashboard (LIVE) and a decision block exists."""
        decision = None

        def _rings(self):
            rings = super()._rings()
            frames, tokens, ctrl, pace = rings
            self.decision = DecisionBlock(smoke.nm("dc"), create=True)
            names = dict(frames=frames.name, tokens=tokens.name, ctrl=ctrl.name, pace=pace.name, decision=self.decision.name, frames_capacity=8192, tokens_capacity=65536)
            SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
            SESSION_FILE.write_text(json.dumps(session_registry(names, spec)), encoding="utf-8")
            return rings

    out.mkdir(parents=True, exist_ok=True)
    smoke.write_meta(out, a.armoury_mode)
    meta = json.loads((out / "meta.json").read_text(encoding="utf-8"))
    meta.update(demo=True, demo_note="NOT registered data: a demo run for the live dashboard (tools/dashboard/demo.py)", spec_id=spec["id"], telemetry=not a.no_telemetry)
    (out / "meta.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
    print(f"demo {spec['id']} -> {out}\nopen the dashboard (python tools/dashboard/server.py) in Edge or Firefox and pick LIVE; the cell takes about 100 s", flush=True)
    ex = DemoExecutor(power_source="sampled")
    pub = None
    st0 = fetch_stats(a.dashboard_port)
    t0 = time.perf_counter()
    try:
        if not a.no_telemetry:
            ex.decision = None
            Governor.default_telemetry = pub = _LazyPublisher(lambda: ex.decision, LoggingPublisher)
        ex.between_cells()
        metrics = ex.run(spec, out)
    finally:
        Governor.default_telemetry = None
        ex.close()
        try:
            SESSION_FILE.unlink()
        except OSError:
            pass
    wall = time.perf_counter() - t0
    st1 = fetch_stats(a.dashboard_port)
    (out / "cell.json").write_text(json.dumps(dict(id=spec["id"], spec=spec, metrics=metrics, executor="hw", demo=True), indent=1, default=str), encoding="utf-8")
    real = getattr(pub, "real", None)
    if real is not None and real.rows:
        import numpy as np
        np.savez_compressed(out / "decisions.npz", fields=np.array(DECISION_FIELDS), rows=np.array(real.rows, float))
    over = None
    if st0 and st1 and st1["wall_s"] > st0["wall_s"]:
        over = dict(server_cpu_s=st1["cpu_s"] - st0["cpu_s"], wall_s=st1["wall_s"] - st0["wall_s"], server_cpu_pct_of_one_core=100.0 * (st1["cpu_s"] - st0["cpu_s"]) / (st1["wall_s"] - st0["wall_s"]), demo_wall_s=wall)
    meta.update(dashboard_overhead=over)
    (out / "meta.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
    print(f"done: miss {metrics.get('miss')}, tok/s {metrics.get('tok_s')}, power {metrics.get('power_w')} W; dashboard server CPU during the run: {over}")


class _LazyPublisher:
    """The decision block is created when the cell's rings are (inside HwExecutor.run); the Governor asks for the sink before that, so the real publisher is built on the first publish."""

    def __init__(self, get_block, cls):
        self.get_block, self.cls, self.real = get_block, cls, None

    def publish(self, ctl, action, t_s):
        if self.real is None:
            self.real = self.cls(self.get_block())
        self.real.publish(ctl, action, t_s)


if __name__ == "__main__":
    main()
