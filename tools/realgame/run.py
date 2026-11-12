"""Sweep driver for sprint R1: order, resume, rep reruns, rest between cells.

Layout under --run-dir:
  run_meta.json                         seed, reps, arms, order (the stored order is the truth on resume)
  llm_alone/                            the single LLM-alone reference cell, measured in its OWN invocation (`run.py --llm-alone`) with the game process absent
  rep<r>/attempt<a>/<pos>_<ARM>/        one cell per directory; the cell is done when result.json exists
  rest_log.jsonl                        one line per rest (rep, attempt, after, before, rest_s, reached, temperatures)
The normal sweep never runs LLM_ALONE. A failed cell (any exception except KeyboardInterrupt) writes FAILED.json into its directory and the WHOLE rep is rerun as the next attempt with
the same order (same seed); every attempt stays on disk. max_attempts is a budget PER INVOCATION per rep (attempts of earlier invocations do not count; new attempt numbers continue after the
highest one on disk). Fail fast: a cell.CellRefused (deterministic refusal) stops the sweep at once (SweepStop, exit code 4, loud banner), and so does the SAME error text twice in a row for the
same cell of the same rep. --stop-after-reps N exits 0 after N reps of this invocation. STATUS.txt in the run dir is rewritten after every cell and at every stop. Resuming after an interruption: cells that already
have result.json are not rerun within a complete attempt, but an UNFINISHED attempt is never continued: it is marked failed (FAILED.json, "interrupted") and a NEW attempt of that rep
starts. Rest rule: before every cell of the sweep except the very first one (this includes the opening SOLO of reps 2 to 5), until the GPU is within 3 C of the rep's starting temperature
(30 s to 300 s); the rest before an opening SOLO uses the temperature at the start of the sweep's first rep as reference (the new rep's own start temperature is read after that rest)."""
import argparse
import json
import random
import shlex
import shutil
import sys
import time
import traceback
from pathlib import Path

from tools.realgame import clockcheck, decision

DEFAULT_SEED = 89770043
DEFAULT_REPS = 5
DEFAULT_ARMS = ("UNGATED", "PRIO_IDLE", "DUTY50", "IGPU")
NOISE_OK = "NOISE_OK.json"  # marker in the attempt directory, written only after the per-rep noise check passed
CLOCK_CHECK = "clock_check.json"
DEFAULT_MAX_CLOCK_CHECK_AGE_S = 21600
RECORD_KEYS = ("nvidia_smi_processes", "display_active", "display_mode", "nvml_name", "nvml_driver_version", "vram_total_mib", "records_mode", "power_static", "nvidia_smi_power", "elevated", "power_scheme_guid", "power_scheme_name")
SMOKE_ARMS = ("SOLO", "UNGATED")
SMOKE_WARM_S = 5.0         # Step-5 smoke: one short cell (5 s warm-up, 20 s window), not part of the sweep
SMOKE_WINDOW_S = 20.0
REHEARSE_WARM_S = 5.0      # --rehearse: one short cell per LLM arm before the sweep
REHEARSE_WINDOW_S = 8.0
REHEARSAL = "rehearsal.json"
DEFAULT_MAX_REHEARSAL_AGE_S = 21600
LLM_ARMS = ("UNGATED", "PRIO_IDLE", "DUTY50", "IGPU")
BELL = "\a"


def noise_stop_limit(reps):
    """Amendment 14, scaled to the number of reps (the ONE place): the sweep stops when MORE THAN this many distinct reps failed the per-rep noise check at any attempt
    (5 reps: 2, 3 reps: 1). The noise limits themselves are never loosened."""
    return max(1, reps // 2)


def _noise_stop_text(bad_reps, reps):
    return f"sweep stopped: reps {sorted(bad_reps)} failed the per-rep noise check (more than {noise_stop_limit(reps)} of {reps} reps failed the noise check); the limits are not loosened"


class NoiseStop(RuntimeError):
    """More than noise_stop_limit(reps) distinct reps failed the per-rep noise check: the sweep stops and is reported."""


class SweepStop(RuntimeError):
    """The sweep stopped on purpose (deterministic refusal, repeated identical error, attempt budget used up): exit code 4."""
    exit_code = 4


def make_order(seed=DEFAULT_SEED, reps=DEFAULT_REPS, arms=DEFAULT_ARMS):
    """Per rep: [SOLO] + the arms shuffled + [SOLO]. A local random.Random(seed) is used (global random state is never touched); one generator runs through the reps in order."""
    arms = tuple(arms)
    if reps < 1:
        raise ValueError("reps must be at least 1")
    if len(set(arms)) != len(arms) or any(a in ("SOLO", "LLM_ALONE") for a in arms):
        raise ValueError(f"arms must be distinct and exclude SOLO and LLM_ALONE: {arms}")
    rng = random.Random(seed)
    order = []
    for _ in range(reps):
        mid = list(arms)
        rng.shuffle(mid)
        order.append(["SOLO"] + mid + ["SOLO"])
    return order


def cell_dir(run_dir, rep, attempt, pos, arm):
    return Path(run_dir) / f"rep{rep}" / f"attempt{attempt}" / f"{pos}_{arm}"


def llm_alone_dir(run_dir):
    return Path(run_dir) / "llm_alone"


def write_run_meta(run_dir, seed, reps, arms, order, igpu_dropped_reason=None, clock_check=None, records=None):
    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    meta = {"seed": seed, "reps": reps, "arms": list(arms), "order": order, "igpu_dropped_reason": igpu_dropped_reason}
    if clock_check is not None:
        meta["clock_check"] = clock_check
    if records is not None:
        meta.update(records)
    (run_dir / "run_meta.json").write_text(json.dumps(meta, indent=1))


def _attempts(run_dir, rep):
    d = Path(run_dir) / f"rep{rep}"
    nums = sorted(int(p.name[len("attempt"):]) for p in d.glob("attempt*") if p.name[len("attempt"):].isdigit()) if d.exists() else []
    return nums


def noise_marker(run_dir, rep, attempt):
    return Path(run_dir) / f"rep{rep}" / f"attempt{attempt}" / NOISE_OK


def _attempt_state(run_dir, rep, attempt, order_rep):
    """'failed' if any cell has FAILED.json; 'complete' if every cell has result.json AND NOISE_OK.json exists; 'unchecked' if every cell has result.json but the noise check never
    passed (no marker); else 'partial'."""
    cells = [cell_dir(run_dir, rep, attempt, i, a) for i, a in enumerate(order_rep)]
    if any((c / "FAILED.json").exists() for c in cells):
        return "failed"
    if not all((c / "result.json").exists() for c in cells):
        return "partial"
    return "complete" if noise_marker(run_dir, rep, attempt).exists() else "unchecked"


def final_attempts(run_dir, order):
    """{rep: highest complete attempt}; raises ValueError if a rep has none (an attempt with all results but no NOISE_OK.json is named in the message)."""
    out = {}
    for rep, o in enumerate(order):
        states = {a: _attempt_state(run_dir, rep, a, o) for a in _attempts(run_dir, rep)}
        done = [a for a, s in states.items() if s == "complete"]
        if not done:
            unchecked = sorted(a for a, s in states.items() if s == "unchecked")
            if unchecked:
                raise ValueError(f"rep {rep} attempt {unchecked[-1]} has all results but no {NOISE_OK} (the per-rep noise check never passed for it) in {run_dir}; resume the sweep to run the check")
            raise ValueError(f"rep {rep} has no complete attempt in {run_dir}")
        out[rep] = max(done)
    return out


def failed_attempts(run_dir, order):
    return {rep: [a for a in _attempts(run_dir, rep) if _attempt_state(run_dir, rep, a, o) == "failed"] for rep, o in enumerate(order)}


def _check_or_write_meta(run_dir, seed, order, arms, igpu_dropped_reason, clock_check=None, records=None):
    p = Path(run_dir) / "run_meta.json"
    reps = len(order)
    if p.exists():
        old = json.loads(p.read_text())
        if old["seed"] != seed or old["reps"] != reps or old["order"] != order:
            raise ValueError(f"run_meta.json in {run_dir} disagrees with the requested seed/reps/order (stored seed={old['seed']}, reps={old['reps']}): refusing to resume")
        if clock_check is not None or records is not None:
            if clock_check is not None:                                       # the clock check that gated THIS invocation replaces an earlier one
                old["clock_check"] = clock_check
            if records is not None:                                           # the records of THIS invocation replace the top-level ones; the earlier ones are kept in a list
                if "nvidia_smi_processes" in old:
                    old.setdefault("earlier_start_records", []).append({k: old[k] for k in RECORD_KEYS if k in old})
                old.update(records)
            p.write_text(json.dumps(old, indent=1))
    else:
        write_run_meta(run_dir, seed, reps, arms, order, igpu_dropped_reason, clock_check, records)


def _write_failed(d, arm, rep, attempt, error, tb="", reason="error"):
    d.mkdir(parents=True, exist_ok=True)
    (d / "FAILED.json").write_text(json.dumps({"arm": arm, "rep": rep, "attempt": attempt, "reason": reason, "error": error, "traceback": tb}, indent=1))


def noise_failed_reps(run_dir):
    """The set of distinct reps that failed the per-rep noise check at ANY attempt (read from the FAILED.json files with reason 'noise', so it survives a resume)."""
    out = set()
    for f in Path(run_dir).glob("rep*/attempt*/*/FAILED.json"):
        try:
            if json.loads(f.read_text()).get("reason") == "noise":
                out.add(int(f.parents[2].name[len("rep"):]))
        except (ValueError, OSError):
            continue
    return out


def rep_noise_from_results(run_dir, rep, attempt, order_rep):
    """Per-rep noise check from the two SOLO result.json files of the attempt (frame.p99, frame.hitch_share) -> (ok, reasons)."""
    first, last = (json.loads((cell_dir(run_dir, rep, attempt, pos, "SOLO") / "result.json").read_text())["frame"] for pos in (0, len(order_rep) - 1))
    return decision.rep_noise_check(first, last)


def _noise_gate(run_dir, rep, attempt, order_rep, noise_check, log, n_reps):
    """Run the per-rep noise check of a finished attempt. Pass (or noise_check None: plumbing tests) -> NOISE_OK.json is written, True. Fail -> FAILED.json (reason 'noise') in the
    closing cell, False (NoiseStop when more than noise_stop_limit(reps) reps failed). An exception from noise_check propagates and no marker is written."""
    if noise_check is None:
        ok, why = True, []
    else:
        ok, why = noise_check(run_dir, rep, attempt, order_rep)
    if ok:
        noise_marker(run_dir, rep, attempt).write_text(json.dumps({"rep": rep, "attempt": attempt, "ok": True, "checked": noise_check is not None}, indent=1))
        return True
    msg = "noise: " + "; ".join(why)
    _write_failed(cell_dir(run_dir, rep, attempt, len(order_rep) - 1, order_rep[-1]), order_rep[-1], rep, attempt, msg, reason="noise")
    log(f"rep {rep} attempt {attempt} FAILED the noise check ({msg}); the whole rep will be rerun with the same order")
    bad_reps = noise_failed_reps(run_dir)
    if len(bad_reps) > noise_stop_limit(n_reps):
        raise NoiseStop(_noise_stop_text(bad_reps, n_reps))
    return False


def _any_cell_ran(run_dir):
    return any(Path(run_dir).glob("rep*/attempt*/*/result.json")) or any(Path(run_dir).glob("rep*/attempt*/*/FAILED.json"))


def _utc_now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def write_status(run_dir, state, last_cell=None, rep=None, attempt=None, error=None, extra=None):
    """<run_dir>/STATUS.txt: the state, the last completed cell, the current rep/attempt, any error text and a UTC timestamp. Rewritten after every cell and at every stop."""
    lines = [f"state: {state}", f"last completed cell: {last_cell or 'none yet'}",
             f"current: rep {rep if rep is not None else '-'} attempt {attempt if attempt is not None else '-'}", f"error: {error if error else 'none'}"]
    if extra:
        lines.append(extra)
    lines.append(f"updated: {_utc_now()} UTC")
    try:
        (Path(run_dir) / "STATUS.txt").write_text("\n".join(lines) + "\n")
    except OSError:
        pass


def _hms(sec):
    sec = int(round(max(0.0, sec)))
    return f"{sec // 3600:02d}:{sec % 3600 // 60:02d}:{sec % 60:02d}"


def _failed_error(run_dir, rep, attempt, pos, arm):
    """The 'error' of an earlier plain-error FAILED.json of this exact cell (None for noise/refused/interrupted or when absent)."""
    f = cell_dir(run_dir, rep, attempt, pos, arm) / "FAILED.json"
    try:
        j = json.loads(f.read_text())
    except (OSError, ValueError):
        return None
    return j.get("error") if j.get("reason") == "error" else None


def _banner(log, title, lines):
    bar = "!" * 78
    log(BELL + bar + "\n" + f"!!! {title}\n" + "\n".join(f"!!! {x}" for x in lines) + "\n" + bar + BELL)


def _stop(run_dir, log, title, lines, rerun_cmd, rep, attempt, last_cell, error):
    lines = list(lines) + ([f"rerun with: {rerun_cmd}"] if rerun_cmd else [])
    _banner(log, title, lines)
    write_status(run_dir, "STOPPED: " + title, last_cell, rep, attempt, error, extra=(f"rerun: {rerun_cmd}" if rerun_cmd else None))
    return SweepStop(title + ": " + "; ".join(lines))


def run_sweep(cfg, run_dir, order, runner, seed=DEFAULT_SEED, read_temp=None, rest=None, max_attempts=3, log=print, igpu_dropped_reason=None, noise_check=None, clock_check=None, records=None,
              stop_after_reps=0, rerun_cmd=None, clock=time.monotonic):
    """runner(arm, rep, out_dir, cfg) must write out_dir/result.json (cell.run_cell does). rest(read_temp, start_temp) -> dict; see cell.rest_until_cool.
    LLM_ALONE is not part of the sweep (see run_llm_alone). noise_check(run_dir, rep, attempt, order_rep) -> (ok, reasons) runs after the closing SOLO of each attempt (amendment 14;
    run.main always passes rep_noise_from_results; None disables it for unit tests of the plumbing). A failing rep is rerun as a new attempt and written to FAILED.json with
    reason 'noise'; when more than noise_stop_limit(reps) distinct reps have failed it at any attempt, NoiseStop is raised.
    max_attempts: attempts started in THIS invocation per rep. cell.CellRefused, or the same error text twice in a row for the same cell, raises SweepStop at once.
    stop_after_reps N > 0: returns 'chunk' after N reps completed in this invocation; otherwise returns 'complete'."""
    from tools.realgame import cell as cell_mod
    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    arms = tuple(a for a in order[0] if a != "SOLO")
    _check_or_write_meta(run_dir, seed, order, arms, igpu_dropped_reason, clock_check, records)
    ran_before = _any_cell_ran(run_dir)                                   # the very first cell of the sweep does not rest
    sweep_ref_temp, prev_label = None, None
    t_start = clock()
    cells_done = 0
    cells_total = sum(0 if any(_attempt_state(run_dir, rep, a, o) == "complete" for a in _attempts(run_dir, rep)) else len(o) for rep, o in enumerate(order))
    reps_done_here = 0
    last_cell = None
    for rep, order_rep in enumerate(order):
        started_here = 0                                                  # attempts started in this invocation for this rep (the per-invocation budget)
        worked = False
        while True:
            if len(noise_failed_reps(run_dir)) > noise_stop_limit(len(order)):
                raise NoiseStop(_noise_stop_text(noise_failed_reps(run_dir), len(order)))
            attempts = _attempts(run_dir, rep)
            for a in attempts:                                            # an unfinished attempt is never continued: it counts as a failed attempt
                if _attempt_state(run_dir, rep, a, order_rep) == "partial":
                    first_open = next(cell_dir(run_dir, rep, a, i, arm) for i, arm in enumerate(order_rep) if not (cell_dir(run_dir, rep, a, i, arm) / "result.json").exists())
                    _write_failed(first_open, first_open.name.split("_", 1)[1], rep, a, "interrupted: unfinished attempt found on resume, treated as a failed attempt")
                    log(f"rep {rep} attempt {a}: unfinished, marked failed (interrupted); a new attempt starts")
            for a in attempts:                                            # all results but never noise-checked (interrupted before/inside the check): check it now
                if _attempt_state(run_dir, rep, a, order_rep) == "unchecked":
                    log(f"rep {rep} attempt {a}: all cells done but never noise-checked; checking now")
                    worked = True
                    _noise_gate(run_dir, rep, a, order_rep, noise_check, log, len(order))
            states = {a: _attempt_state(run_dir, rep, a, order_rep) for a in attempts}
            if any(s == "complete" for s in states.values()):
                break                                                       # rep done
            if started_here >= max_attempts:
                msg = f"rep {rep}: {max_attempts} attempts failed in this invocation (see FAILED.json files under {run_dir / f'rep{rep}'}); stopping the sweep"
                write_status(run_dir, "STOPPED: attempts exhausted", last_cell, rep, started_here, msg)
                _banner(log, "ATTEMPT BUDGET USED UP", [msg] + ([f"rerun with: {rerun_cmd}"] if rerun_cmd else []))
                raise SweepStop(msg)
            attempt = (max(attempts) + 1) if attempts else 1
            started_here += 1
            worked = True
            log(f"rep {rep} attempt {attempt}: order {order_rep}")
            start_temp = None
            failed = False
            for pos, arm in enumerate(order_rep):
                d = cell_dir(run_dir, rep, attempt, pos, arm)
                label = f"rep{rep}/attempt{attempt}/{pos}_{arm}"
                if (d / "result.json").exists():
                    log(f"  skip {pos}_{arm} (result.json exists)")
                    prev_label = label
                    continue
                if ran_before and read_temp and rest:
                    ref = start_temp if pos > 0 else (sweep_ref_temp if sweep_ref_temp is not None else read_temp())
                    r = rest(read_temp, ref)
                    with open(run_dir / "rest_log.jsonl", "a") as f:
                        f.write(json.dumps({"rep": rep, "attempt": attempt, "after": prev_label, "before": f"{pos}_{arm}", **r}) + "\n")
                if pos == 0 and read_temp:
                    start_temp = read_temp()                              # the rep's starting temperature (after the rest before its opening SOLO)
                    if sweep_ref_temp is None:
                        sweep_ref_temp = start_temp
                log(f"  run {pos}_{arm}")
                ran_before = True
                prev_label = label
                try:
                    runner(arm, rep, d, cfg)
                except KeyboardInterrupt:
                    write_status(run_dir, "INTERRUPTED (resumable: rerun the same command)", last_cell, rep, attempt, f"KeyboardInterrupt during {label}")
                    raise
                except Exception as e:                                      # noqa: BLE001
                    err = f"{type(e).__name__}: {e}"
                    refused = isinstance(e, (cell_mod.CellRefused, cell_mod.PreflightError))
                    _write_failed(d, arm, rep, attempt, err, traceback.format_exc(), reason="refused" if refused else "error")
                    if refused:
                        log(f"  REFUSED {pos}_{arm}: {e}")
                        raise _stop(run_dir, log, "SWEEP STOPPED: DETERMINISTIC REFUSAL", [f"error: {err}", f"cell: {label}"], rerun_cmd, rep, attempt, last_cell, err) from e
                    prior = _failed_error(run_dir, rep, attempt - 1, pos, arm) if attempt > 1 else None
                    if prior is not None and prior == err:
                        log(f"  FAILED {pos}_{arm}: {e}")
                        raise _stop(run_dir, log, "SWEEP STOPPED: THE SAME ERROR TWICE IN A ROW (deterministic)", [f"error: {err}", f"cell: {label} (and the same cell of attempt {attempt - 1})"],
                                    rerun_cmd, rep, attempt, last_cell, err) from e
                    write_status(run_dir, "cell failed, the whole rep will be rerun", last_cell, rep, attempt, f"{label}: {err}")
                    log(f"  FAILED {pos}_{arm}: {e}; the whole rep will be rerun with the same order")
                    failed = True
                    break
                cells_done += 1
                last_cell = label
                now = clock() - t_start
                left = max(0, cells_total - cells_done)
                log(f"progress cell {cells_done}/{cells_total} {label} done; elapsed {_hms(now)}; est. remaining {_hms(now / cells_done * left)} ({left} cell(s) left, mean {now / cells_done:.0f} s/cell)")
                write_status(run_dir, "running", last_cell, rep, attempt, None)
            if not failed and not _noise_gate(run_dir, rep, attempt, order_rep, noise_check, log, len(order)):
                continue
            if not failed:
                break
        if worked:
            reps_done_here += 1
        if stop_after_reps and reps_done_here >= stop_after_reps and rep < len(order) - 1:
            msg = f"{reps_done_here} rep(s) done, rerun the same command to continue"
            write_status(run_dir, "chunk finished: " + msg, last_cell, rep, None, None)
            log(msg)
            return "chunk"
    write_status(run_dir, "COMPLETE", last_cell, None, None, None)
    _banner(log, "SWEEP COMPLETE", [f"{len(order)} rep(s) complete in {run_dir}", "next: run analyze"])
    return "complete"


def run_llm_alone(cfg, run_dir, runner, log=print):
    """The LLM-alone reference, in its own invocation with the game absent. runner(arm, rep, out_dir, cfg) as in run_sweep; skipped if result.json exists."""
    alone = llm_alone_dir(run_dir)
    if (alone / "result.json").exists():
        log("skip LLM_ALONE (result.json exists)")
        return False
    log("run LLM_ALONE (game absent)")
    runner("LLM_ALONE", 0, alone, cfg)
    return True


def write_clock_check(run_dir, status, state, problems, now=None, game_running=None):
    """--check-clocks result: run_dir/clock_check.json (status passed/refused, epoch + ISO timestamp, max_sm_mhz under load, thresholds, the information block (idle SM samples, pstate,
    enforced power limit, clocks-event reasons mask), helper_present, load error, problems)."""
    now = time.time() if now is None else now
    state = state or {}
    load = state.get("load_test") or {}
    doc = {"status": status, "timestamp": now, "timestamp_iso": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(now)), "max_sm_mhz": state.get("max_sm_mhz"),
           "thresholds": state.get("thresholds"), "power_limit_max_w": load.get("power_limit_max_w"), "info": load.get("info"), "helper_present": list(state.get("helper_present") or []), "n_load_samples": load.get("n_load_samples"),
           "load_error": load.get("load_error"), "game_running": game_running, "problems": list(problems)}
    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / CLOCK_CHECK).write_text(json.dumps(doc, indent=1, default=str))
    return doc


def load_clock_check(run_dir, max_age_s, now=None):
    """-> (doc, None) when run_dir/clock_check.json exists, has status 'passed' and is no older than max_age_s; else (None, refusal text)."""
    f = Path(run_dir) / CLOCK_CHECK
    if not f.exists():
        return None, f"{f} does not exist: run `--check-clocks --run-dir {run_dir}` first"
    try:
        doc = json.loads(f.read_text())
        ts = float(doc["timestamp"])
    except (ValueError, KeyError, TypeError, OSError) as e:
        return None, f"{f} is unreadable or has no valid timestamp ({type(e).__name__}: {e}); rerun --check-clocks"
    if doc.get("status") != "passed":
        return None, f"{f} status is {doc.get('status')!r}, not 'passed' (clock state refused): fix it and rerun --check-clocks"
    age = (time.time() if now is None else now) - ts
    if age > max_age_s:
        return None, f"{f} is older than {max_age_s} s ({age:.0f} s old): rerun --check-clocks"
    return doc, None


def next_smoke_dir(run_dir, arm):
    """<run_dir>/smoke/<arm>_<n>, n above every existing one (never reused); the directory is created here, so nothing is overwritten."""
    base = Path(run_dir) / "smoke"
    base.mkdir(parents=True, exist_ok=True)
    nums = [int(p.name[len(arm) + 1:]) for p in base.glob(f"{arm}_*") if p.name[len(arm) + 1:].isdigit()]
    d = base / f"{arm}_{max(nums, default=0) + 1}"
    d.mkdir()
    return d


def run_smoke(cfg, run_dir, arm, runner, records, log=print):
    """ONE cell of `arm` through the normal run_cell (via runner) with the smoke warm-up and window passed explicitly, into run_dir/smoke/<arm>_<n>/. No rest, no NOISE_OK, no reps,
    no run_meta.json (analyze never looks at run_dir/smoke). Prints the summary block, writes smoke_summary.txt and real_header.csv. Returns 0."""
    from tools.realgame import smoke
    d = next_smoke_dir(run_dir, arm)
    (d / "start_records.json").write_text(json.dumps(records, indent=1, default=str))
    log(f"smoke {arm} -> {d}")
    runner(arm, 0, d, cfg, warmup_s=SMOKE_WARM_S, window_s=SMOKE_WINDOW_S, smoke=True)
    if (d / "frames.csv").exists() and (d / "result.json").exists():
        log(smoke.write_outputs(d))
    return 0


def evaluate_rehearsal(arm, res):
    """The PASS criteria of one rehearsal result -> list of failure reasons (empty = PASS): EXEC_MODE device, tokens > 0 (the context-reset check is in run_cell and raises), PRIO_IDLE start
    and end read-backs equal to the idle class, DUTY50 DUTY_ACHIEVED parsed, power_rejected reported."""
    from tools.realgame import gpu_priority
    why = []
    dev = res.get("exec_mode") or ""
    device = dev.split("device=", 1)[1].split(" offloaded=", 1)[0] if "device=" in dev else ""
    if arm == "IGPU":
        if "780M" not in device and "Radeon" not in device:
            why.append(f"EXEC_MODE device {device!r} is not the 780M/Radeon")
    elif "RTX" not in device and "NVIDIA" not in device:
        why.append(f"EXEC_MODE device {device!r} is not the RTX/NVIDIA")
    n = res.get("n_tokens")
    if not isinstance(n, (int, float)) or n <= 0:
        why.append(f"tokens in the window: {n!r} (need > 0)")
    if arm == "PRIO_IDLE":
        rb = res.get("prio_readbacks")
        idle = gpu_priority.CLASSES["IDLE"]
        if not isinstance(rb, list) or len(rb) < 2 or any(x != idle for x in rb):
            why.append(f"PRIO_IDLE start/end read-backs {rb!r} are not all the idle class {idle}")
    if arm == "DUTY50" and not isinstance(res.get("duty_achieved"), (int, float)):
        why.append("no DUTY_ACHIEVED line parsed")
    if res.get("power_rejected") is None:
        why.append("power_rejected not reported")
    return why


def run_rehearsal(cfg, run_dir, arms, runner, log=print, now=None, exe_sha256=None, binding=None):
    """One short cell (REHEARSE_WARM_S warm-up, REHEARSE_WINDOW_S window) per LLM arm through the normal run_cell (via runner) into <run_dir>/rehearsal/<ARM>/. Prints
    `REHEARSAL <ARM>: PASS|FAIL (reasons)` per arm, writes <run_dir>/rehearsal.json and returns (all_passed, doc). Touches no sweep directory (rep*/attempt*, run_meta.json)."""
    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    out = {}
    for arm in arms:
        if arm not in LLM_ARMS:
            continue
        d = run_dir / "rehearsal" / arm
        if d.exists():
            shutil.rmtree(d)
        info, reasons = {}, []
        try:
            res = runner(arm, 0, d, cfg, warmup_s=REHEARSE_WARM_S, window_s=REHEARSE_WINDOW_S, rehearsal=True)
            if not (d / "result.json").exists():
                reasons.append("no result.json was written")
            else:
                res = json.loads((d / "result.json").read_text())
                reasons = evaluate_rehearsal(arm, res)
                info = {k: res.get(k) for k in ("exec_mode", "n_tokens", "tok_s", "power_rejected", "prio_readbacks", "duty_achieved")}
        except Exception as e:                                          # noqa: BLE001
            reasons.append(f"{type(e).__name__}: {e}")
        status = "FAIL" if reasons else "PASS"
        out[arm] = {"status": status, "reasons": reasons, "info": info}
        extra = f"; duty_achieved {info['duty_achieved']}" if arm == "DUTY50" and info.get("duty_achieved") is not None else ""
        if status == "PASS":
            log(f"REHEARSAL {arm}: PASS (tokens {info.get('n_tokens')}, power_rejected {info.get('power_rejected')}{extra})")
        else:
            log(f"REHEARSAL {arm}: FAIL ({'; '.join(reasons)})")
    ts = time.time() if now is None else now
    doc = {"rehearsal": True, "timestamp": ts, "timestamp_iso": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(ts)), "exe_sha256": dict(exe_sha256 or {}),
           "warmup_s": REHEARSE_WARM_S, "window_s": REHEARSE_WINDOW_S, "arms": out, **(binding or {})}
    (run_dir / REHEARSAL).write_text(json.dumps(doc, indent=1, default=str))
    return all(v["status"] == "PASS" for v in out.values()), doc


def load_rehearsal(run_dir, arms, max_age_s, now=None):
    """-> (doc, None) when run_dir/rehearsal.json exists, is no older than max_age_s and every arm of `arms` that uses an LLM has status PASS; else (None, refusal text)."""
    f = Path(run_dir) / REHEARSAL
    if not f.exists():
        return None, f"{f} does not exist: run `--rehearse --run-dir {run_dir}` first (a 3-minute dry run of every LLM arm)"
    try:
        doc = json.loads(f.read_text())
        ts = float(doc["timestamp"])
        per = doc["arms"]
    except (ValueError, KeyError, TypeError, OSError) as e:
        return None, f"{f} is unreadable or malformed ({type(e).__name__}: {e}); rerun --rehearse"
    age = (time.time() if now is None else now) - ts
    if age > max_age_s:
        return None, f"{f} is older than {max_age_s} s ({age:.0f} s old): rerun --rehearse"
    bad = []
    for arm in arms:
        if arm not in LLM_ARMS:
            continue
        st = (per.get(arm) or {}).get("status") if isinstance(per, dict) else None
        if st != "PASS":
            bad.append(f"{arm}: {st if st else 'not rehearsed'}" + (f" ({'; '.join((per.get(arm) or {}).get('reasons') or [])})" if st == "FAIL" else ""))
    if bad:
        return None, f"{f}: rehearsal not passed for " + "; ".join(bad) + ": fix it and rerun --rehearse"
    return doc, None


BOUND_GIT_PATHS = ("tools/realgame", "workloads/background")


def rehearsal_binding(cfg, probes):
    """The evidence rehearsal.json binds to: PresentMon sha256 (None when no PresentMon exe was given), the model file's size and mtime, and the git HEAD of the repo."""
    pm = None
    if cfg.presentmon_exe and probes.exists(cfg.presentmon_exe):
        pm = probes.sha256(cfg.presentmon_exe)
    size, mtime = probes.file_stat(cfg.model)
    return {"presentmon_sha256": pm, "model": {"size": size, "mtime": mtime}, "git_head": probes.git_head(cfg.repo_root)}


def rehearsal_binding_problem(doc, cfg, probes):
    """None when the rehearsal evidence still describes the CURRENT executables, model, PresentMon and sources; else the text naming the FIRST mismatch (rerun --rehearse)."""
    tail = ": rerun --rehearse"
    rec = doc.get("exe_sha256")
    if not isinstance(rec, dict) or not rec:
        return "rehearsal.json records no executable sha256" + tail
    for label, exe in (("llm_exe", cfg.llm_exe), ("llm_exe_vk", cfg.llm_exe_vk)):
        if exe is None:
            continue
        if label not in rec:
            return f"rehearsal.json records no sha256 for {label}" + tail
        now = probes.sha256(exe)
        if now != rec[label]:
            return f"{label} sha256 changed since the rehearsal ({rec[label]} then, {now} now; {exe})" + tail
    model = doc.get("model")
    if not isinstance(model, dict) or "size" not in model or "mtime" not in model:
        return "rehearsal.json records no model size/mtime" + tail
    size, mtime = probes.file_stat(cfg.model)
    if size != model["size"]:
        return f"model file size changed since the rehearsal ({model['size']} then, {size} now; {cfg.model})" + tail
    if mtime != model["mtime"]:
        return f"model file mtime changed since the rehearsal ({model['mtime']} then, {mtime} now; {cfg.model})" + tail
    pm_rec = doc.get("presentmon_sha256")
    if not pm_rec:
        return "rehearsal.json records no PresentMon sha256 (pass --presentmon to --rehearse)" + tail
    pm_now = probes.sha256(cfg.presentmon_exe)
    if pm_now != pm_rec:
        return f"PresentMon sha256 changed since the rehearsal ({pm_rec} then, {pm_now} now)" + tail
    head = doc.get("git_head")
    if not head:
        return "rehearsal.json records no git HEAD" + tail
    if head != probes.git_head(cfg.repo_root):
        changed = probes.git_changed(cfg.repo_root, head, BOUND_GIT_PATHS)
        if changed:
            return f"{', '.join(changed[:5])} changed since the rehearsal (git HEAD {head[:12]}, tools/realgame and workloads/background must be unchanged)" + tail
    return None


def _arms_arg(text):
    names = text.split(",")
    bad = [n for n in names if n not in DEFAULT_ARMS]
    if bad:
        raise argparse.ArgumentTypeError(f"unknown arm(s) {bad}; choose from {','.join(DEFAULT_ARMS)}")
    dup = sorted({n for n in names if names.count(n) > 1})
    if dup:
        raise argparse.ArgumentTypeError(f"duplicate arm(s) {dup}")
    return tuple(names)


def _parser():
    p = argparse.ArgumentParser(description="R1 sweep: game + LLM co-location on one GPU, unlocked clocks")
    p.add_argument("--run-dir")
    p.add_argument("--reps", type=int, default=DEFAULT_REPS)
    p.add_argument("--seed", type=int, default=DEFAULT_SEED)
    p.add_argument("--smoke", choices=SMOKE_ARMS, metavar="ARM", help="Step-5 smoke: run ONE cell of this arm (SOLO or UNGATED; 5 s warm-up, 20 s window) into run-dir/smoke/<ARM>_<n>/ and print a summary; same preflight")
    p.add_argument("--dry-run", action="store_true", help="print the order and run preflight only")
    p.add_argument("--llm-alone", action="store_true", help="measure only the LLM-alone reference; the game process must be ABSENT (refused if it is running)")
    p.add_argument("--armoury-mode", help="Armoury Crate mode in force (required)")
    p.add_argument("--expect-power-scheme", metavar="NAME_OR_GUID", help="refuse (preflight and every cell start) unless the active Windows power scheme matches: exact guid or case-insensitive substring of the name; "
                   "a scheme change during a cell fails the cell. Without it the scheme is only recorded")
    p.add_argument("--repo-root", default=str(Path(__file__).resolve().parents[2]))
    p.add_argument("--llama-dir")
    p.add_argument("--llm-exe")
    p.add_argument("--llm-exe-vk", help="the Vulkan build of the driver (IGPU arm only); default workloads/background/llama_realgame_bench_vk.exe")
    p.add_argument("--igpu-vk-index", type=int, help="DEPRECATED and ignored (Vulkan device order is not stable); accepted so old command lines still work")
    p.add_argument("--igpu-device-match", default="780M", help="substring (case-insensitive) of the ggml device description the IGPU arm must run on (RG_DEVICE_MATCH); default 780M")
    p.add_argument("--model")
    p.add_argument("--prompt")
    p.add_argument("--n-prompt", type=int)
    p.add_argument("--presentmon")
    p.add_argument("--check-clocks", action="store_true", help="clock check (amendment 18): admin clock helper absent and max SM clock above 1980 MHz in a ~5 s CUDA load test; information only: game_running is recorded in clock_check.json")
    p.add_argument("--allow-pm-hash-mismatch", action="store_true", help="explicit override of the PresentMon sha256 check (recorded in meta)")
    p.add_argument("--game-process", required=True, help="executable name, must end with .exe")
    p.add_argument("--arms", type=_arms_arg, default=DEFAULT_ARMS, metavar="LIST",
                   help="comma-separated subset of UNGATED,PRIO_IDLE,DUTY50,IGPU (default all four); used for the order, the rehearsal, its gate, the IGPU requirements and run_meta.json")
    p.add_argument("--drop-igpu", metavar="REASON", help="drop the IGPU arm and record the reason")
    p.add_argument("--max-attempts", type=int, default=3, help="attempts per rep in THIS invocation (attempts on disk from earlier invocations do not count)")
    p.add_argument("--rehearse", action="store_true", help="run ONE short cell (5 s warm-up, 8 s window) of every LLM arm into run-dir/rehearsal/<ARM>/ without the game and PresentMon; writes rehearsal.json; the sweep requires a fresh all-PASS one")
    p.add_argument("--max-rehearsal-age-s", type=float, default=DEFAULT_MAX_REHEARSAL_AGE_S, help="the sweep refuses unless run-dir/rehearsal.json passed and is no older than this")
    p.add_argument("--stop-after-reps", type=int, default=0, help="exit 0 after this many reps completed in this invocation (0 = no limit); rerun the same command to continue")
    p.add_argument("--max-clock-check-age-s", type=float, default=DEFAULT_MAX_CLOCK_CHECK_AGE_S, help="the sweep (and --llm-alone) refuses unless run-dir/clock_check.json passed and is no older than this")
    return p


def main(argv=None, probes=None, runner=None, deps=None):
    parser = _parser()
    args = parser.parse_args(argv)
    if not args.check_clocks and (args.n_prompt is None or (args.presentmon is None and not args.rehearse)):
        parser.error("--n-prompt and --presentmon are required (except with --check-clocks; --presentmon is not used by --rehearse)")
    if args.rehearse and (args.smoke or args.llm_alone or args.check_clocks):
        parser.error("--rehearse cannot be combined with --smoke, --llm-alone or --check-clocks")
    if args.igpu_vk_index is not None:
        print("note: --igpu-vk-index is deprecated and ignored (Vulkan device order is not stable); the IGPU arm selects its device by description: --igpu-device-match", file=sys.stderr)
    from tools.realgame import cell
    try:
        cell.validate_game_process(args.game_process)
    except ValueError as e:
        print(f"--game-process: {e}", file=sys.stderr)
        return 2
    if args.check_clocks:
        probes = probes or cell.SystemProbes()
        game_running = bool(probes.process_running(args.game_process))      # information only, never a refusal
        problems, state = cell.clock_state_check(probes, args.game_process, run_load=True)
        print(json.dumps(state, indent=1, default=str))
        if args.run_dir:
            write_clock_check(args.run_dir, "refused" if problems else "passed", state, problems, game_running=game_running)
        else:
            print("note: no --run-dir, so no clock_check.json was written; the sweep will refuse without it", file=sys.stderr)
        if problems:
            print("clock state refused:\n  " + "\n  ".join(problems), file=sys.stderr)
            return 2
        print(f"clock state ok: helper absent, max SM clock under load {state['max_sm_mhz']} MHz (above {clockcheck.PASS_SM_MHZ_ABOVE})")
        return 0
    if args.smoke and args.llm_alone:
        parser.error("--smoke cannot be combined with --llm-alone")
    root = Path(args.repo_root)
    arms = tuple(a for a in args.arms if not (args.drop_igpu and a == "IGPU"))
    use_igpu = "IGPU" in arms and not args.llm_alone and not args.smoke
    cfg = cell.Config(repo_root=root, llm_exe=Path(args.llm_exe or root / "workloads" / "background" / "llama_realgame_bench.exe"),
                      model=Path(args.model or root / "data" / "llama" / "Llama-3.2-3B-Instruct-Q4_K_M.gguf"), prompt=Path(args.prompt or root / "data" / "llama" / "prompt.txt"),
                      presentmon_exe=Path(args.presentmon or "PresentMon-not-used-in-rehearsal.exe"), game_process=args.game_process, armoury_mode=args.armoury_mode,
                      llama_dir=Path(args.llama_dir or root / "third_party" / "llama.cpp"), n_prompt=args.n_prompt, seed=args.seed,
                      llm_exe_vk=Path(args.llm_exe_vk or root / "workloads" / "background" / "llama_realgame_bench_vk.exe") if use_igpu else None,
                      igpu_vk_index=None, igpu_device_match=args.igpu_device_match, allow_pm_hash_mismatch=args.allow_pm_hash_mismatch,
                      expect_power_scheme=args.expect_power_scheme)
    order = make_order(args.seed, args.reps, arms)
    if args.rehearse:
        print(f"mode: REHEARSAL (one cell per LLM arm {list(arms)}, warm-up {REHEARSE_WARM_S} s, window {REHEARSE_WINDOW_S} s; no game, no PresentMon; not part of the sweep)")
    elif args.smoke:
        print(f"mode: SMOKE {args.smoke} (one cell, warm-up {SMOKE_WARM_S} s, window {SMOKE_WINDOW_S} s; not part of the sweep)")
    else:
        print(f"seed {args.seed}  reps {args.reps}  arms {list(arms)}" + (f"  IGPU dropped: {args.drop_igpu}" if args.drop_igpu else ""))
    if args.smoke or args.rehearse:
        pass
    elif args.llm_alone:
        print("mode: LLM_ALONE only (own invocation, game process must be absent)")
    else:
        print("LLM_ALONE is NOT part of this sweep: run it separately with --llm-alone while the game is not running")
        for rep, o in enumerate(order):
            print(f"rep {rep}: " + " ".join(o))
    probes = probes or cell.SystemProbes()
    try:
        cell.preflight(cfg, probes, need_game=not (args.llm_alone or args.rehearse), game_absent=args.llm_alone, need_vk=use_igpu, need_presentmon=not args.rehearse)
    except cell.PreflightError as e:
        print(str(e), file=sys.stderr)
        return 2
    for label, exe in (("llm_exe", cfg.llm_exe), ("llm_exe_vk", cfg.llm_exe_vk)):
        if exe is not None:
            print(f"{label} sha256 {probes.sha256(exe)}  {exe}")
    if args.dry_run:
        print("dry run: preflight passed, nothing was run")
        return 0
    if not args.run_dir:
        print("--run-dir is required unless --dry-run", file=sys.stderr)
        return 2
    if args.rehearse:
        return _main_rehearse(args, cfg, arms, probes, runner, deps)
    clock_check, why = load_clock_check(args.run_dir, args.max_clock_check_age_s)
    if clock_check is None:
        print(f"clock check refused: {why}", file=sys.stderr)
        return 2
    records = dict(cell.sweep_start_records(probes), records_mode="smoke" if args.smoke else "llm_alone" if args.llm_alone else "sweep")      # amendment 21
    if isinstance(records.get("power_static"), dict):
        cfg.power_static_ref = records["power_static"]               # amendment 19 (replaced): every cell start must match these static fields
    deps = deps if deps is not None else (cell.real_deps(cfg) if runner is None else None)
    runner = runner or (lambda arm, rep, out_dir, c, **kw: cell.run_cell(arm, rep, out_dir, c, deps, **kw))
    if args.smoke:
        return run_smoke(cfg, Path(args.run_dir), args.smoke, runner, records)
    if args.llm_alone:
        _check_or_write_meta(Path(args.run_dir), args.seed, order, arms, args.drop_igpu, clock_check, records)
        run_llm_alone(cfg, Path(args.run_dir), runner)
        return 0
    rehearsal, why = load_rehearsal(args.run_dir, arms, args.max_rehearsal_age_s)
    if rehearsal is None:
        print(f"rehearsal refused: {why}", file=sys.stderr)
        return 2
    why = rehearsal_binding_problem(rehearsal, cfg, probes)
    if why:
        print(f"rehearsal refused: {why}", file=sys.stderr)
        return 2
    read_temp = deps.nvml.temp_c if deps is not None else None
    rerun_cmd = "python -m tools.realgame.run " + shlex.join(list(sys.argv[1:] if argv is None else argv))
    try:
        run_sweep(cfg, Path(args.run_dir), order, runner, seed=args.seed, read_temp=read_temp, rest=cell.rest_until_cool if read_temp else None,
                  max_attempts=args.max_attempts, igpu_dropped_reason=args.drop_igpu, noise_check=rep_noise_from_results, clock_check=clock_check, records=records,
                  stop_after_reps=args.stop_after_reps, rerun_cmd=rerun_cmd)
    except NoiseStop as e:
        print(str(e), file=sys.stderr)
        return 3
    except SweepStop as e:
        print(str(e), file=sys.stderr)
        return e.exit_code
    return 0


def _main_rehearse(args, cfg, arms, probes, runner, deps):
    """--rehearse: records and the power-static reference as in a sweep (no run_meta.json, no sweep directory), then one short cell per LLM arm."""
    from tools.realgame import cell
    records = cell.sweep_start_records(probes)
    if isinstance(records.get("power_static"), dict):
        cfg.power_static_ref = records["power_static"]
    deps = deps if deps is not None else (cell.real_deps(cfg) if runner is None else None)
    runner = runner or (lambda arm, rep, out_dir, c, **kw: cell.run_cell(arm, rep, out_dir, c, deps, **kw))
    run_dir = Path(args.run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "rehearsal_start_records.json").write_text(json.dumps(records, indent=1, default=str))
    hashes = {label: probes.sha256(exe) for label, exe in (("llm_exe", cfg.llm_exe), ("llm_exe_vk", cfg.llm_exe_vk)) if exe is not None}
    ok, doc = run_rehearsal(cfg, run_dir, arms, runner, exe_sha256=hashes, binding=rehearsal_binding(cfg, probes))
    print(f"rehearsal {'PASSED' if ok else 'FAILED'}: {run_dir / REHEARSAL}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
