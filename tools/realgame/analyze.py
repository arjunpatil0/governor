"""Offline analysis of an R1 run tree (written by tools/realgame/run.py): cell summaries, paired comparison, the decision rule, predictability, flags and plots.

  python -m tools.realgame.analyze --run-dir <run> --out <new dir>

Never overwrites: refuses if --out exists and is not empty, or if any target path (or the --out directory) is tracked by git. Only the last complete attempt of each rep is analysed;
the failed attempts are listed. Window frames come from the raw PresentMon CSV (frames.csv) cut on QPC time with the cell's own t_open/t_close/qpc_hz; tokens from llm_tokens.csv."""
import argparse
import json
import subprocess
import sys
from pathlib import Path

from tools.realgame import cell as rg_cell
from tools.realgame import decision, metrics, presentmon
from tools.realgame import run as rg_run

PAGING_MB = 64.0
TARGETS = ("summary.json", "summary.md", "p99_by_arm.png", "hitch_by_arm.png")


class OutputRefused(RuntimeError):
    pass


def is_tracked(path):
    """True if git tracks the path (or, for a directory, anything under it): `git ls-files --error-unmatch`. Not in a repo -> False."""
    path = Path(path).resolve()
    anchor = path
    while not anchor.exists():
        anchor = anchor.parent
    cwd = anchor if anchor.is_dir() else anchor.parent
    r = subprocess.run([rg_cell.tool_paths()["git"], "-C", str(cwd), "ls-files", "--error-unmatch", "--", str(path)], capture_output=True, text=True)
    return r.returncode == 0


def _check_out(out, targets):
    out = Path(out)
    if out.exists() and (not out.is_dir() or any(out.iterdir())):
        raise OutputRefused(f"--out {out} exists and is not empty: refusing to write")
    for t in [out, *targets]:
        if is_tracked(t):
            raise OutputRefused(f"{t} is tracked by git: refusing to overwrite a committed file")


def _load(d):
    return json.loads((Path(d) / "result.json").read_text())


def cell_summary(cell_dir):
    """Recomputed from the raw files of one cell."""
    d = Path(cell_dir)
    res = _load(d)
    out = {"arm": res["arm"], "rep": res["rep"], "t_open": res["t_open"], "t_close": res["t_close"], "power_w": res.get("power_w"), "energy_j": res.get("energy_j"),
           "sm_clock_mhz_median": res.get("sm_clock_mhz_median"), "throttle_mask_or": res.get("throttle_mask_or"), "throttle_flag_mask_or": res.get("throttle_flag_mask_or"),
           "temp_c": res.get("temp_c"), "vram_mb": res.get("vram_mb"), "shared_gpu_mem_bytes": res.get("shared_gpu_mem_bytes"), "prio_readbacks": res.get("prio_readbacks")}
    if (d / "frames.csv").exists():
        cm = metrics.cell_frame_metrics(presentmon.parse_csv(d / "frames.csv"), res["t_open"], res["t_close"], res["qpc_hz"])
        fm = cm["frame"]
        out.update(p50=fm["p50"], p99=fm["p99"], low1_fps=fm["low1_fps"], hitch_share=fm["hitch_share"], n_frames=fm["n"], n_dropped=cm["n_dropped"],
                   gpu_busy_ms_median=cm["gpu_busy_ms_median"], swapchain=cm["swapchain"])
        out["_frames"] = cm["frames"]
    if (d / "llm_tokens.csv").exists():
        out["n_tokens"] = metrics.count_tokens(d / "llm_tokens.csv", res["t_open"], res["t_close"])
        out["tok_s"] = metrics.token_rate(d / "llm_tokens.csv", res["t_open"], res["t_close"])
    return out


def _round(x):
    if isinstance(x, float):
        return round(x, 9)
    if isinstance(x, dict):
        return {str(k): _round(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_round(v) for v in x]
    return x


def _flags(cells):
    """Paging and throttling flags. Paging uses the end-of-window shared-memory reading (shared_gpu_mem_bytes['end']) of each cell against the mean END reading of the rep's SOLO cells;
    the start reading (taken during the warm-up) is recorded but never used for the flag."""
    paging, throttling = [], []
    for rep in sorted({c["rep"] for c in cells}):
        rc = [c for c in cells if c["rep"] == rep]
        solo = [c["shared_gpu_mem_bytes"]["end"] for c in rc if c["arm"] == "SOLO" and isinstance(c.get("shared_gpu_mem_bytes"), dict)]
        solo = [v for v in solo if isinstance(v, (int, float))]
        for c in rc:
            sm = c.get("shared_gpu_mem_bytes")
            val = sm.get("end") if isinstance(sm, dict) else sm
            if c["arm"] != "SOLO" and solo and isinstance(val, (int, float)) and (val - sum(solo) / len(solo)) / 2**20 > PAGING_MB:
                paging.append({"rep": rep, "arm": c["arm"], "pos": c["pos"], "excess_mb": (val - sum(solo) / len(solo)) / 2**20})
            if c.get("throttle_flag_mask_or"):
                throttling.append({"rep": rep, "arm": c["arm"], "pos": c["pos"], "mask": c["throttle_flag_mask_or"]})
    return {"paging": paging, "throttling": throttling, "paging_threshold_mb": PAGING_MB,
            "note": "paging = shared GPU memory above the rep's SOLO mean by more than 64 MB (bytes/2**20; cells without a reading are not flagged)"}


def collect_prio_readbacks(run_dir, order):
    """Every PRIO_IDLE read-back of every attempt (discarded and failed attempts included, where the cell wrote a result.json), not only the final attempt: a bad read-back anywhere
    voids PRIO_IDLE for the sweep."""
    out = []
    for rep, o in enumerate(order):
        if "PRIO_IDLE" not in o:
            continue
        pos = o.index("PRIO_IDLE")
        for attempt in rg_run._attempts(run_dir, rep):
            f = rg_run.cell_dir(run_dir, rep, attempt, pos, "PRIO_IDLE") / "result.json"
            if f.exists():
                out += list(json.loads(f.read_text()).get("prio_readbacks") or [])
    return out


def _load_llm_alone(run_dir):
    d = rg_run.llm_alone_dir(run_dir)
    if not (d / "result.json").exists():
        raise ValueError(f"LLM_ALONE reference missing: {d / 'result.json'} does not exist; run `python -m tools.realgame.run --llm-alone ...` with the game not running, "
                         "UNGATED validity cannot be evaluated without it")
    if _load(d).get("game_absent") is not True:
        raise ValueError(f"LLM_ALONE reference in {d} was not measured with the game absent (game_absent is not true in result.json); refusing to use it")
    alone = cell_summary(d)
    if not alone.get("tok_s"):
        raise ValueError(f"LLM_ALONE reference in {d} has no usable tok/s")
    return alone


def analyze(run_dir):
    run_dir = Path(run_dir)
    meta = json.loads((run_dir / "run_meta.json").read_text())
    order = meta["order"]
    finals = rg_run.final_attempts(run_dir, order)
    cells, by = [], {}
    for rep, o in enumerate(order):
        for pos, arm in enumerate(o):
            d = rg_run.cell_dir(run_dir, rep, finals[rep], pos, arm)
            s = cell_summary(d)
            s.update(pos=pos, attempt=finals[rep])
            cells.append(s)
            by[(rep, pos)] = s
    alone = _load_llm_alone(run_dir)
    solo = [({"p99": by[(r, 0)]["p99"], "hitch": by[(r, 0)]["hitch_share"]}, {"p99": by[(r, len(o) - 1)]["p99"], "hitch": by[(r, len(o) - 1)]["hitch_share"]})
            for r, o in enumerate(order)]
    arms_present = [a for a in order[0] if a != "SOLO"]
    arms = {a: [{"p99": c["p99"], "hitch": c["hitch_share"], "toks": c["tok_s"], "tokens_csv": rg_run.cell_dir(run_dir, r, c["attempt"], c["pos"], a) / "llm_tokens.csv",
                 "t_open": c["t_open"], "t_close": c["t_close"]} for r in range(len(order)) for c in [by[(r, order[r].index(a))]]] for a in arms_present}
    prio_rb = collect_prio_readbacks(run_dir, order) if "PRIO_IDLE" in arms_present else []
    # predictability: SOLO decides, UNGATED is supplementary
    def frames_of(arm):
        return [c["_frames"] for c in cells if c["arm"] == arm]
    hz = {_load(rg_run.cell_dir(run_dir, c["rep"], c["attempt"], c["pos"], c["arm"]))["qpc_hz"] for c in cells}
    if len(hz) != 1:
        raise ValueError(f"cells disagree on qpc_hz: {sorted(hz)}")
    qhz = hz.pop()
    pred_solo = metrics.predictability_report(frames_of("SOLO"), qhz)
    pred = {"solo": pred_solo, "solo_decides": True}
    pred["ungated"] = dict(metrics.predictability_report(frames_of("UNGATED"), qhz), informational=True)
    pred["ungated"]["note"] = "supplementary: the cadence under LLM overlap; decides nothing"
    from tools.realgame.gpu_priority import CLASSES
    ev = decision.evaluate(solo=solo, arms=arms, llm_alone_toks=alone["tok_s"], predictability_pass=pred_solo["primary"]["pass"], prio_readbacks=prio_rb,
                           idle_class=CLASSES["IDLE"])
    for c in cells:
        c.pop("_frames", None)
    summary = {"run_meta": {k: meta[k] for k in ("seed", "reps", "arms", "order", "igpu_dropped_reason")}, "llm_alone": alone,
               "cells": cells, "decision": ev, "predictability": pred, "flags": _flags(cells),
               "attempts": {str(r): {"final_attempt": finals[r], "failed_attempts": rg_run.failed_attempts(run_dir, order)[r]} for r in range(len(order))}}
    summary["decision_notes"] = ("noise drift is reported separately in decision.noise; DUTY50 is reference only; bootstrap/median/worst are for information only; "
                                 "predictability is pooled over the SOLO cells (errors computed within each cell)")
    return _round(summary)


def _plots(summ, out):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    arms = [a for a in summ["decision"]["arms"]]
    for key, fname, ylabel in (("worsening_pct", "p99_by_arm.png", "paired p99 worsening (%)"), ("hitch_pp", "hitch_by_arm.png", "paired hitch increase (pp)")):
        fig, ax = plt.subplots(figsize=(6, 4))
        for i, a in enumerate(arms):
            vals = [p[key] for p in summ["decision"]["arms"][a]["paired"]]
            ax.scatter([i] * len(vals), vals, alpha=0.7)
            ax.hlines(sum(vals) / len(vals), i - 0.3, i + 0.3, colors="k")
        ax.set_xticks(range(len(arms)))
        ax.set_xticklabels(arms, rotation=20)
        ax.set_ylabel(ylabel)
        ax.axhline(0, color="grey", lw=0.5)
        ax.set_title("R1: per-rep paired values (bar = mean)")
        fig.tight_layout()
        fig.savefig(Path(out) / fname, dpi=100)
        plt.close(fig)


def _markdown(s):
    d = s["decision"]
    lines = [f"# R1 analysis", "", f"Branch: **{d['branch']}**", ""] + [f"- {r}" for r in d["reasons"]] + ["", "| arm | mean worsening % | mean hitch pp | within limits | harmful |", "|---|---|---|---|---|"]
    for a, e in d["arms"].items():
        lines.append(f"| {a} | {e['mean_worsening_pct']:.3f} | {e['mean_hitch_pp']:.3f} | {e['within_limits']} | {e['harmful']} |")
    lines += ["", f"Noise precondition ok: {d['noise']['ok']} (drift p99 {d['noise']['drift_p99_pct_mean']:.3f} %, hitch {d['noise']['drift_hitch_pp_mean']:.3f} pp)",
              f"Predictability (SOLO, N=8) pass: {s['predictability']['solo']['primary']['pass']}"]
    return "\n".join(lines) + "\n"


def run_analysis(run_dir, out, plots=True):
    out = Path(out)
    _check_out(out, [out / t for t in TARGETS])
    summ = analyze(run_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "summary.json").write_text(json.dumps(summ, indent=1))
    (out / "summary.md").write_text(_markdown(summ))
    if plots:
        _plots(summ, out)
    return summ


def main(argv=None):
    p = argparse.ArgumentParser(description="Analyse an R1 run tree")
    p.add_argument("--run-dir", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--no-plots", action="store_true")
    a = p.parse_args(argv)
    try:
        run_analysis(a.run_dir, a.out, plots=not a.no_plots)
    except (OutputRefused, ValueError) as e:
        print(f"refused: {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
