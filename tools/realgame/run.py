"""Sweep driver for sprint R1: order, resume, rep reruns, rest between cells.

Layout under --run-dir:
  run_meta.json                         seed, reps, arms, order (the stored order is the truth on resume)
  llm_alone/                            the single LLM-alone reference cell, measured in its OWN invocation (`run.py --llm-alone`) with the game process absent
  rep<r>/attempt<a>/<pos>_<ARM>/        one cell per directory; the cell is done when result.json exists
  rest_log.jsonl                        one line per rest (rep, attempt, after, before, rest_s, reached, temperatures)
The normal sweep never runs LLM_ALONE. A failed cell (any exception except KeyboardInterrupt) writes FAILED.json into its directory and the WHOLE rep is rerun as the next attempt with
the same order (same seed); every attempt stays on disk. After max_attempts failed attempts of one rep the sweep stops with an error. Resuming after an interruption: cells that already
have result.json are not rerun within a complete attempt, but an UNFINISHED attempt is never continued: it is marked failed (FAILED.json, "interrupted") and a NEW attempt of that rep
starts. Rest rule: before every cell of the sweep except the very first one (this includes the opening SOLO of reps 2 to 5), until the GPU is within 3 C of the rep's starting temperature
(30 s to 180 s); the rest before an opening SOLO uses the temperature at the start of the sweep's first rep as reference (the new rep's own start temperature is read after that rest)."""
import argparse
import json
import random
import sys
import traceback
from pathlib import Path

from tools.realgame import decision

DEFAULT_SEED = 89770043
DEFAULT_REPS = 5
DEFAULT_ARMS = ("UNGATED", "PRIO_IDLE", "DUTY50", "IGPU")
MAX_NOISE_REPS = 2          # amendment 14: more than 2 distinct reps failing the noise check at any attempt stops the sweep (never loosened)


class NoiseStop(RuntimeError):
    """More than MAX_NOISE_REPS distinct reps failed the per-rep noise check: the sweep stops and is reported."""


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


def write_run_meta(run_dir, seed, reps, arms, order, igpu_dropped_reason=None):
    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "run_meta.json").write_text(json.dumps({"seed": seed, "reps": reps, "arms": list(arms), "order": order, "igpu_dropped_reason": igpu_dropped_reason}, indent=1))


def _attempts(run_dir, rep):
    d = Path(run_dir) / f"rep{rep}"
    nums = sorted(int(p.name[len("attempt"):]) for p in d.glob("attempt*") if p.name[len("attempt"):].isdigit()) if d.exists() else []
    return nums


def _attempt_state(run_dir, rep, attempt, order_rep):
    """'failed' if any cell has FAILED.json, 'complete' if every cell has result.json, else 'partial'."""
    cells = [cell_dir(run_dir, rep, attempt, i, a) for i, a in enumerate(order_rep)]
    if any((c / "FAILED.json").exists() for c in cells):
        return "failed"
    return "complete" if all((c / "result.json").exists() for c in cells) else "partial"


def final_attempts(run_dir, order):
    """{rep: highest complete attempt}; raises ValueError if a rep has none."""
    out = {}
    for rep, o in enumerate(order):
        done = [a for a in _attempts(run_dir, rep) if _attempt_state(run_dir, rep, a, o) == "complete"]
        if not done:
            raise ValueError(f"rep {rep} has no complete attempt in {run_dir}")
        out[rep] = max(done)
    return out


def failed_attempts(run_dir, order):
    return {rep: [a for a in _attempts(run_dir, rep) if _attempt_state(run_dir, rep, a, o) == "failed"] for rep, o in enumerate(order)}


def _check_or_write_meta(run_dir, seed, order, arms, igpu_dropped_reason):
    p = Path(run_dir) / "run_meta.json"
    reps = len(order)
    if p.exists():
        old = json.loads(p.read_text())
        if old["seed"] != seed or old["reps"] != reps or old["order"] != order:
            raise ValueError(f"run_meta.json in {run_dir} disagrees with the requested seed/reps/order (stored seed={old['seed']}, reps={old['reps']}): refusing to resume")
    else:
        write_run_meta(run_dir, seed, reps, arms, order, igpu_dropped_reason)


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


def _any_cell_ran(run_dir):
    return any(Path(run_dir).glob("rep*/attempt*/*/result.json")) or any(Path(run_dir).glob("rep*/attempt*/*/FAILED.json"))


def run_sweep(cfg, run_dir, order, runner, seed=DEFAULT_SEED, read_temp=None, rest=None, max_attempts=3, log=print, igpu_dropped_reason=None, noise_check=None):
    """runner(arm, rep, out_dir, cfg) must write out_dir/result.json (cell.run_cell does). rest(read_temp, start_temp) -> dict; see cell.rest_until_cool.
    LLM_ALONE is not part of the sweep (see run_llm_alone). noise_check(run_dir, rep, attempt, order_rep) -> (ok, reasons) runs after the closing SOLO of each attempt (amendment 14;
    run.main always passes rep_noise_from_results; None disables it for unit tests of the plumbing). A failing rep is rerun as a new attempt and written to FAILED.json with
    reason 'noise'; when more than MAX_NOISE_REPS distinct reps have failed it at any attempt, NoiseStop is raised."""
    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    arms = tuple(a for a in order[0] if a != "SOLO")
    _check_or_write_meta(run_dir, seed, order, arms, igpu_dropped_reason)
    ran_before = _any_cell_ran(run_dir)                                   # the very first cell of the sweep does not rest
    sweep_ref_temp, prev_label = None, None
    for rep, order_rep in enumerate(order):
        while True:
            if len(noise_failed_reps(run_dir)) > MAX_NOISE_REPS:
                raise NoiseStop(f"sweep stopped: reps {sorted(noise_failed_reps(run_dir))} failed the per-rep noise check (more than {MAX_NOISE_REPS} of {len(order)}); the limits are not loosened")
            attempts = _attempts(run_dir, rep)
            for a in attempts:                                            # an unfinished attempt is never continued: it counts as a failed attempt
                if _attempt_state(run_dir, rep, a, order_rep) == "partial":
                    first_open = next(cell_dir(run_dir, rep, a, i, arm) for i, arm in enumerate(order_rep) if not (cell_dir(run_dir, rep, a, i, arm) / "result.json").exists())
                    _write_failed(first_open, first_open.name.split("_", 1)[1], rep, a, "interrupted: unfinished attempt found on resume, treated as a failed attempt")
                    log(f"rep {rep} attempt {a}: unfinished, marked failed (interrupted); a new attempt starts")
            states = {a: _attempt_state(run_dir, rep, a, order_rep) for a in attempts}
            if any(s == "complete" for s in states.values()):
                break                                                       # rep done
            attempt = (max(attempts) + 1) if attempts else 1
            if attempt > max_attempts:
                raise RuntimeError(f"rep {rep}: {max_attempts} attempts failed (see FAILED.json files under {run_dir / f'rep{rep}'}); stopping the sweep")
            log(f"rep {rep} attempt {attempt}: order {order_rep}")
            start_temp = None
            failed = False
            for pos, arm in enumerate(order_rep):
                d = cell_dir(run_dir, rep, attempt, pos, arm)
                if (d / "result.json").exists():
                    log(f"  skip {pos}_{arm} (result.json exists)")
                    prev_label = f"rep{rep}/attempt{attempt}/{pos}_{arm}"
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
                prev_label = f"rep{rep}/attempt{attempt}/{pos}_{arm}"
                try:
                    runner(arm, rep, d, cfg)
                except Exception as e:                                      # noqa: BLE001  (KeyboardInterrupt is not caught: an interruption is resumable, not a failure)
                    _write_failed(d, arm, rep, attempt, f"{type(e).__name__}: {e}", traceback.format_exc())
                    log(f"  FAILED {pos}_{arm}: {e}; the whole rep will be rerun with the same order")
                    failed = True
                    break
            if not failed and noise_check is not None:
                ok, why = noise_check(run_dir, rep, attempt, order_rep)
                if not ok:
                    msg = "noise: " + "; ".join(why)
                    _write_failed(cell_dir(run_dir, rep, attempt, len(order_rep) - 1, order_rep[-1]), order_rep[-1], rep, attempt, msg, reason="noise")
                    log(f"rep {rep} attempt {attempt} FAILED the noise check ({msg}); the whole rep will be rerun with the same order")
                    bad_reps = noise_failed_reps(run_dir)
                    if len(bad_reps) > MAX_NOISE_REPS:
                        raise NoiseStop(f"sweep stopped: reps {sorted(bad_reps)} failed the per-rep noise check (more than {MAX_NOISE_REPS} of {len(order)}); the limits are not loosened")
                    continue
            if not failed:
                break


def run_llm_alone(cfg, run_dir, runner, log=print):
    """The LLM-alone reference, in its own invocation with the game absent. runner(arm, rep, out_dir, cfg) as in run_sweep; skipped if result.json exists."""
    alone = llm_alone_dir(run_dir)
    if (alone / "result.json").exists():
        log("skip LLM_ALONE (result.json exists)")
        return False
    log("run LLM_ALONE (game absent)")
    runner("LLM_ALONE", 0, alone, cfg)
    return True


def _parser():
    p = argparse.ArgumentParser(description="R1 sweep: game + LLM co-location on one GPU, unlocked clocks")
    p.add_argument("--run-dir")
    p.add_argument("--reps", type=int, default=DEFAULT_REPS)
    p.add_argument("--seed", type=int, default=DEFAULT_SEED)
    p.add_argument("--dry-run", action="store_true", help="print the order and run preflight only")
    p.add_argument("--llm-alone", action="store_true", help="measure only the LLM-alone reference; the game process must be ABSENT (refused if it is running)")
    p.add_argument("--armoury-mode", help="Armoury Crate mode in force (required)")
    p.add_argument("--repo-root", default=str(Path(__file__).resolve().parents[2]))
    p.add_argument("--llama-dir")
    p.add_argument("--llm-exe")
    p.add_argument("--llm-exe-vk", help="the Vulkan build of the driver (IGPU arm only); default workloads/background/llama_realgame_bench_vk.exe")
    p.add_argument("--igpu-vk-index", type=int, help="Vulkan device index of the Radeon 780M (GGML_VK_VISIBLE_DEVICES); required for the IGPU arm")
    p.add_argument("--model")
    p.add_argument("--prompt")
    p.add_argument("--n-prompt", type=int)
    p.add_argument("--presentmon")
    p.add_argument("--check-clocks", action="store_true", help="read-only clock-state check (admin clock helper absent, SM clock not locked by the idle probe); the game process must be ABSENT")
    p.add_argument("--allow-pm-hash-mismatch", action="store_true", help="explicit override of the PresentMon sha256 check (recorded in meta)")
    p.add_argument("--game-process", required=True, help="executable name, must end with .exe")
    p.add_argument("--drop-igpu", metavar="REASON", help="drop the IGPU arm and record the reason")
    p.add_argument("--max-attempts", type=int, default=3)
    return p


def main(argv=None, probes=None, runner=None):
    parser = _parser()
    args = parser.parse_args(argv)
    if not args.check_clocks and (args.n_prompt is None or args.presentmon is None):
        parser.error("--n-prompt and --presentmon are required (except with --check-clocks)")
    from tools.realgame import cell
    try:
        cell.validate_game_process(args.game_process)
    except ValueError as e:
        print(f"--game-process: {e}", file=sys.stderr)
        return 2
    if args.check_clocks:
        probes = probes or cell.SystemProbes()
        if probes.process_running(args.game_process):
            print(f"--check-clocks: game process {args.game_process} is running; the idle probe needs the game absent", file=sys.stderr)
            return 2
        problems, state = cell.clock_state_check(probes, args.game_process)
        print(json.dumps(state, indent=1, default=str))
        if problems:
            print("clock state refused:\n  " + "\n  ".join(problems), file=sys.stderr)
            return 2
        print("clock state ok: helper absent, SM clock unlocked (idle probe: " + str(state["idle_probe"].get("status")) + ")")
        return 0
    root = Path(args.repo_root)
    arms = tuple(a for a in DEFAULT_ARMS if not (args.drop_igpu and a == "IGPU"))
    use_igpu = "IGPU" in arms and not args.llm_alone
    if use_igpu and args.igpu_vk_index is None:
        print("--igpu-vk-index is required for the IGPU arm (the Vulkan device index of the Radeon 780M); or drop the arm with --drop-igpu REASON", file=sys.stderr)
        return 2
    cfg = cell.Config(repo_root=root, llm_exe=Path(args.llm_exe or root / "workloads" / "background" / "llama_realgame_bench.exe"),
                      model=Path(args.model or root / "data" / "llama" / "Llama-3.2-3B-Instruct-Q4_K_M.gguf"), prompt=Path(args.prompt or root / "data" / "llama" / "prompt.txt"),
                      presentmon_exe=Path(args.presentmon), game_process=args.game_process, armoury_mode=args.armoury_mode,
                      llama_dir=Path(args.llama_dir or root / "third_party" / "llama.cpp"), n_prompt=args.n_prompt, seed=args.seed,
                      llm_exe_vk=Path(args.llm_exe_vk or root / "workloads" / "background" / "llama_realgame_bench_vk.exe") if use_igpu else None,
                      igpu_vk_index=args.igpu_vk_index if use_igpu else None, allow_pm_hash_mismatch=args.allow_pm_hash_mismatch)
    order = make_order(args.seed, args.reps, arms)
    print(f"seed {args.seed}  reps {args.reps}  arms {list(arms)}" + (f"  IGPU dropped: {args.drop_igpu}" if args.drop_igpu else ""))
    if args.llm_alone:
        print("mode: LLM_ALONE only (own invocation, game process must be absent)")
    else:
        print("LLM_ALONE is NOT part of this sweep: run it separately with --llm-alone while the game is not running")
        for rep, o in enumerate(order):
            print(f"rep {rep}: " + " ".join(o))
    probes = probes or cell.SystemProbes()
    try:
        cell.preflight(cfg, probes, need_game=not args.llm_alone, game_absent=args.llm_alone, need_vk=use_igpu)
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
    deps = cell.real_deps(cfg) if runner is None else None
    runner = runner or (lambda arm, rep, out_dir, c: cell.run_cell(arm, rep, out_dir, c, deps))
    if args.llm_alone:
        run_llm_alone(cfg, Path(args.run_dir), runner)
        return 0
    read_temp = deps.nvml.temp_c if deps is not None else None
    try:
        run_sweep(cfg, Path(args.run_dir), order, runner, seed=args.seed, read_temp=read_temp, rest=cell.rest_until_cool if read_temp else None,
                  max_attempts=args.max_attempts, igpu_dropped_reason=args.drop_igpu, noise_check=rep_noise_from_results)
    except NoiseStop as e:
        print(str(e), file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
