"""W2 design expansion: turns experiments/w2_colocation.yaml into per-block cell lists, seeded orders and clock-validity flags.
Pure functions (no GPU); tested in tests/test_w2_design.py. Parts: A (primary residual-wait), A2 (secondary preemption
characterisation), B (clock lock vs foreground), C (decode proxy knee)."""
import json
import random
from pathlib import Path

# Registered in the yaml as prose (experiment_B.clocks); mirrored here and checked by tests/test_w2_design.py.
# 1050 MHz is a descriptive level added by experiments/w2_colocation_addendum_B_levels_2026-10-21.md (outside the HB1/HB2 families).
B_LEVELS = [900, 1050, 1200, 1500, 1800, "unlocked"]
# Part L (experiments/w2_colocation_addendum_llamacpp_2026-10-21.md): the same nine levels as experiment_C.sm_levels_mhz
LLAMA_LEVELS = [600, 750, 900, 1050, 1200, 1350, 1500, 1800, "unlocked"]
LLAMA_MODEL = "Llama-3.2-3B-Instruct-Q4_K_M.gguf"
# Part G (experiments/w2_colocation_addendum_globaltimer_2026-10-22.md): fresh seed namespace ("fresh seeds from a new seed namespace")
G_SEED = 20261022
MEM_MHZ = 8001
SM_TOL, MEM_TOL = 0.03, 0.01      # validity_checks in the yaml

# fg request streams: size_ms -> (rate_hz, requests, arrivals); the 9 ms entry is the B fma 60 Hz frame
FG_STREAMS = {0.1: (200, 2000, "poisson"), 1: (100, 1000, "poisson"), 4: (40, 400, "poisson"), 9: (60, 600, "periodic")}
FRAMES = {"fma_60hz": (60, 600), "fma_120hz": (120, 1200), "mem_60hz": (60, 600)}


def _fg(size_ms, priority="normal"):
    rate, n, arr = FG_STREAMS[size_ms]
    d = dict(size_ms=size_ms, rate_hz=rate, n=n, arrivals=arr, priority=priority, kind="fma")
    if size_ms == 9:
        d["frame"] = "fma_60hz"
    return d


def _bg(m_ms, cv, duty=1.0, kind="fma"):
    return dict(kind=kind, m_ms=m_ms, cv=cv, duty=duty)


def _cell(part, cell_id, sm, fg, bg, **extra):
    return dict(part=part, cell_id=cell_id, sm_mhz=sm, mem_mhz=MEM_MHZ, fg=fg, bg=bg, **extra)


def build_cells(cfg, part):
    """All cells of one block for `part`, in registration order (unshuffled)."""
    if part == "A":
        a = cfg["experiment_A"]["factors"]
        cells = [_cell("A", "baseline", 1800, _fg(0.1), None)]
        for m in a["m_ms"]:
            for c in a["c"]:
                cells.append(_cell("A", f"bg_fma_m{m}_c{c}", 1800, _fg(0.1), _bg(m, c)))
        return cells
    if part == "A2":
        cells = []
        for m in (2, 8):
            for c in (0.0, 1.0):
                cells.append(_cell("A2", f"sa3_high_m{m}_c{c}", 1800, _fg(0.1, "high"), _bg(m, c)))
        for s in (1, 4, 9):
            cells.append(_cell("A2", f"sa4_fg{s}_alone", 1800, _fg(s), None))
            for m in (2, 8):
                cells.append(_cell("A2", f"sa4_fg{s}_m{m}", 1800, _fg(s), _bg(m, 0.0)))
        for s in (4, 9):
            for d in (0.25, 0.5, 0.75):
                cells.append(_cell("A2", f"duty_fg{s}_d{d}", 1800, _fg(s), _bg(2, 0.0, duty=d)))
        return cells
    if part == "B":
        cells = []
        for frame, (rate, n) in FRAMES.items():
            fg = dict(frame=frame, size_ms=None, rate_hz=rate, n=n, arrivals="periodic", priority="normal",
                      kind="mem" if frame.startswith("mem") else "fma")
            for bgname, bg in (("nobg", None), ("membg", _bg(1, 0.0, kind="mem"))):
                for lv in B_LEVELS:
                    cells.append(_cell("B", f"{frame}_{bgname}_{lv}", lv, dict(fg), bg))
        return cells
    if part == "C":
        cells = []
        for variant in ("int4", "fp16"):
            for graph in (False, True):
                for lv in cfg["experiment_C"]["sm_levels_mhz"]:
                    cells.append(_cell("C", f"{variant}_{'graph' if graph else 'stream'}_{lv}", lv, None, None,
                                       decode=dict(variant=variant, graph=graph)))
        return cells
    if part == "L":
        return [_cell("L", f"llama_{lv}", lv, None, None, llama=dict(model=LLAMA_MODEL, n_prompt=512)) for lv in LLAMA_LEVELS]
    if part == "G":
        rec = lambda c, on: dict(c, rec=on)
        cells = [rec(_cell("G", "g_baseline", 1800, _fg(0.1), None), True)]
        for m in (0.5, 1, 2, 8):
            for on in (True, False):
                cells.append(rec(_cell("G", f"g_R{m}" + ("" if on else "_off"), 1800, _fg(0.1), _bg(m, 0.0)), on))
        cells.append(rec(_cell("G", "g_T1", 1800, _fg(1), _bg(2, 0.0)), True))
        cells.append(rec(_cell("G", "g_T4", 1800, _fg(4), _bg(2, 0.0)), True))
        cells.append(rec(_cell("G", "g_bgalone", 1800, None, _bg(2, 0.0)), True))
        cells.append(rec(_cell("G", "g_T1_alone", 1800, _fg(1), None), True))
        cells.append(rec(_cell("G", "g_T4_alone", 1800, _fg(4), None), True))
        return cells
    raise ValueError(f"unknown part {part!r}; expected A, A2, B, C, L or G")


def precheck_cells_G(cells):
    """Cells of the Experiment G pre-check (iii) run: instrumented/uninstrumented pairs for fg alone (g_baseline_off exists only here, it is
    not one of the 14 registered cells) and for R_2, plus bgalone and T4 so every recording code path runs. Not a result."""
    by = {c["cell_id"]: c for c in cells}
    twin = dict(by["g_baseline"], cell_id="g_baseline_off", rec=False)
    return [by["g_baseline"], twin, by["g_R2"], by["g_R2_off"], by["g_bgalone"], by["g_T4"]]


def order_block(cells, base_seed, block):
    """Seeded permutation of a block's cells (independent of the input order)."""
    out = sorted(cells, key=lambda c: c["cell_id"])
    random.Random(base_seed + block).shuffle(out)
    return out


def cell_seed(base_seed, block, cell_idx):
    return base_seed * 1_000_003 + block * 1009 + cell_idx


def clock_flags(sm_samples, mem_samples, sm_target, mem_target):
    """Flags for a window whose logged clocks left the locked target (sm_target None = unlocked cell, SM not checked)."""
    if not len(sm_samples) and not len(mem_samples):
        return ["no_clock_samples"]
    flags = []
    if sm_target is not None and len(sm_samples):
        worst = max(sm_samples, key=lambda s: abs(s - sm_target))
        if abs(worst - sm_target) > SM_TOL * sm_target:
            flags.append(f"sm_clock_left_target:{worst:.0f}")
    if mem_target is not None and len(mem_samples):
        worst = max(mem_samples, key=lambda s: abs(s - mem_target))
        if abs(worst - mem_target) > MEM_TOL * mem_target:
            flags.append(f"mem_clock_left_target:{worst:.0f}")
    return flags


def frame_units_from_pilot(path):
    """Frame kernel units are fixed from the pilot (sized at the unlocked clock; yaml experiment_B.foreground_frames)."""
    p4 = json.loads(Path(path).read_text(encoding="utf-8"))["P4_frames"]
    return {k.lower(): v["units"] for k, v in p4.items() if k.lower() in FRAMES}


def frame_units_for_part(part, cells, pilot_path):
    """Frame units for every part whose cells use a named frame (B and A2's 9 ms stream); None when no cell does."""
    if not any(c.get("fg") and c["fg"].get("frame") for c in cells):
        return None
    return frame_units_from_pilot(pilot_path)
