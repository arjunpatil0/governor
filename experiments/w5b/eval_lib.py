"""W5b evaluation blocks 4-13: pure composition of a block (plan addendum O-6 section 5; tests/test_w5b_eval.py).
One block = 25 primary cells (scenes S0, S1, S1d, S2, S5 x controllers g'B, eB, c'B, d'B at 60 W + the reference arm a in the 5 scenes); blocks 4-8 add the exploratory 35 W family (the same 20 cells).
S3 and d'B-HGB are not built. Background: the 3B for S0, S1, S1d, S2; the held-out Llama-3.1-8B for S5. Foreground: synthetic FMA at the frozen c0; scene time starts at the measured window (origin 5000 ms).
The order inside a block is seeded-random per (block, cell)."""
import random

SEED = 20261025
SCENES = ("S0", "S1", "S1d", "S2", "S5")
CONTROLLERS = ("g'B", "eB", "c'B", "d'B")
EVAL_BLOCKS = tuple(range(4, 14))
EXPLORATORY_BLOCKS = tuple(range(4, 9))
HELD_OUT = "llama31_8b"
KNOWN_BG = "llama32_3b"
CELL_S = 100.0                      # estimate per cell (measured in the tuning sittings: 100 s mean, 112 s max)
SESSION_MAX_S = 3 * 3600.0
WARMUP_ORIGIN_MS = 5000.0
_CODE = {"g'B": "gB", "eB": "eB", "c'B": "cB", "d'B": "dB", "a": "a"}


def _cell(block, scene, ctrl, budget, const, exploratory):
    base = dict(id=f"ev{block:02d}_{scene}_{_CODE[ctrl]}_{int(budget)}", block=block, scene=scene, controller=ctrl, budget_w=float(budget), exploratory=exploratory,
                workload=HELD_OUT if scene == "S5" else KNOWN_BG, c0=const["c0"], origin_ms=WARMUP_ORIGIN_MS)
    if ctrl == "a":
        return dict(base, kind="arm_a")
    if ctrl in ("g'B", "eB"):
        setting = const["g_b"].get(str(int(budget)))
        if setting is None:
            return None
        return dict(base, kind="static" if ctrl == "g'B" else "eB", setting=setting)
    if ctrl == "c'B":
        return dict(base, kind="cB", params=dict(target=const["c_b"]["target"], ki=const["c_b"]["ki"]))
    return dict(base, kind="dB", params=dict(margin=const["d_b"]["margin"]))


def block_cells(block, const, seed=SEED, hgb=False, seed_block=None):
    """The cells of one evaluation block in run order. seed_block: draw the order of that block's seed list (a block rerun under another number, yaml: 'the same seed list')."""
    if hgb:
        raise NotImplementedError("d'B-HGB is not built (addendum O-3 section 6, O-6 section 6)")
    cells = [_cell(block, s, k, 60.0, const, False) for s in SCENES for k in CONTROLLERS] + [_cell(block, s, "a", 60.0, const, False) for s in SCENES]
    if block in EXPLORATORY_BLOCKS or (seed_block in EXPLORATORY_BLOCKS):
        cells += [_cell(block, s, k, 35.0, const, True) for s in SCENES for k in CONTROLLERS]
    cells = [c for c in cells if c is not None]
    sb = block if seed_block is None else seed_block
    return sorted(cells, key=lambda c: random.Random(f"{seed}:{sb}:{c['scene']}:{c['controller']}:{int(c['budget_w'])}").random())


def session_estimate_s(blocks, const):
    return sum(len(block_cells(b, const)) for b in blocks) * CELL_S


def check_session(blocks, const, allow_rerun_numbers=True):
    """Reason a session request is refused, or None: only evaluation blocks (a rerun of a discarded block may take the next number, 14+), at most 3 h at CELL_S per cell, blocks never split."""
    ok = set(EVAL_BLOCKS) | (set(range(14, 40)) if allow_rerun_numbers else set())
    if any(b not in ok for b in blocks):
        return f"refused: {blocks} are not evaluation blocks (evaluation blocks are 4-13)"
    est = session_estimate_s(blocks, const)
    if est > SESSION_MAX_S:
        return f"refused: the session would take about {est / 3600:.1f} h at {CELL_S:.0f} s per cell, above the 3 h rule (blocks are never split: take fewer blocks)"
    return None
