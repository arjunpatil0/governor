"""--smoke summary (sprint R1 Step 5): a plain text block from one smoke cell's result.json and PresentMon frames.csv. Information only: nothing in it decides anything.
Frames come from PresentMon only, through the same functions as analyze (presentmon.parse_csv, metrics.cell_frame_metrics)."""
import json
from pathlib import Path

import numpy as np

from tools.realgame import metrics, presentmon

PRESET_BUSY_MS = (6.0, 10.0)
PRESET_HITCH_BELOW_PCT = 1.0
PRESET_MIN_FPS = 59.0


def _yn(ok):
    return "yes" if ok else "no"


def preset_acceptance_line(s):
    """INFORMATION ONLY: the prereg 'Preset acceptance' numbers for SOLO. s: gpu_busy_median, hitch_share (%), fps."""
    return ("preset acceptance (prereg): GPU busy median in 6 to 10 ms: " + _yn(PRESET_BUSY_MS[0] <= s["gpu_busy_median"] <= PRESET_BUSY_MS[1])
            + "; hitch share below 1%: " + _yn(s["hitch_share"] < PRESET_HITCH_BELOW_PCT) + "; fps >= 59: " + _yn(s["fps"] >= PRESET_MIN_FPS))


def csv_header_line(frames_csv):
    text = Path(frames_csv).read_text(encoding="utf-8-sig")
    return text.lstrip("\r\n").splitlines()[0] if text.strip() else ""


def window_stats(cell_dir, res):
    cm = metrics.cell_frame_metrics(presentmon.parse_csv(Path(cell_dir) / "frames.csv"), res["t_open"], res["t_close"], res["qpc_hz"])
    fr = cm["frames"]
    ft = np.asarray([f.frame_ms for f in fr], dtype=float)
    busy = np.asarray([f.gpu_busy_ms for f in fr], dtype=float)
    f = cm["frame"]
    return {"n": f["n"], "fps": f["n"] / res["window_s"], "p50": f["p50"], "p99": f["p99"], "max": float(ft.max()), "low1_fps": f["low1_fps"], "hitch_share": f["hitch_share"],
            "gpu_busy_median": float(np.median(busy)), "gpu_busy_p95": float(np.percentile(busy, 95, method=metrics.PERCENTILE_METHOD)), "idle_median": float(np.median(ft - busy)),
            "present_modes": sorted({x.present_mode for x in fr if x.present_mode}), "swapchain": cm["swapchain"], "n_dropped": cm["n_dropped"]}


def summary_text(cell_dir):
    cell_dir = Path(cell_dir)
    res = json.loads((cell_dir / "result.json").read_text())
    arm, s = res["arm"], window_stats(cell_dir, res)
    tc, vm = res.get("temp_c") or {}, res.get("vram_mb") or {}
    lines = ["smoke summary (information only; it decides nothing by itself)",
             f"arm: {arm}", f"warm-up {res['warmup_s']} s, window {res['window_s']} s",
             f"frames in window: {s['n']}", f"achieved fps (frames / window_s): {s['fps']:.2f}",
             f"frame time ms p50 / p99 / max: {s['p50']:.2f} / {s['p99']:.2f} / {s['max']:.2f}", f"1% low fps: {s['low1_fps']:.2f}",
             f"hitch share (> {metrics.HITCH_MS:.1f} ms): {s['hitch_share']:.2f} %",
             f"GPU busy per frame ms median / p95: {s['gpu_busy_median']:.2f} / {s['gpu_busy_p95']:.2f}",
             f"idle per frame ms (frame - GPU busy) median: {s['idle_median']:.2f}",
             f"PresentMode seen: {s['present_modes']}", f"dominant swapchain: {s['swapchain']}",
             f"any frame dropped: {_yn(s['n_dropped'])} (n_dropped={s['n_dropped']})",
             f"PresentMon CSV header: {csv_header_line(cell_dir / 'frames.csv')}",
             f"VRAM MiB start / end: {vm.get('start')} / {vm.get('end')}", f"idle VRAM MiB: {res.get('idle_vram_mib')}",
             f"temperature C start / end: {tc.get('start')} / {tc.get('end')}",
             "enforced power limit W start / end / min / max: " + " / ".join(str(res.get(k)) for k in ("enforced_limit_w_start", "enforced_limit_w_end", "enforced_limit_w_min", "enforced_limit_w_max")),
             f"SM clock median MHz: {res.get('sm_clock_mhz_median')}",
             f"throttle masks: or={res.get('throttle_mask_or')} flag_mask_or={res.get('throttle_flag_mask_or')}",
             f"power W (energy counter): {res['power_w']:.2f}  energy J: {res['energy_j']:.2f}", f"power_rejected: {res.get('power_rejected')}"]
    if arm == "UNGATED":
        lines += [f"tok/s in window: {res['tok_s']:.2f}", f"LLM exec line: {res.get('exec_mode')}"]
    if arm == "SOLO":
        lines.append(preset_acceptance_line(s) + "  [INFORMATION ONLY, decides nothing by itself]")
    return "\n".join(lines) + "\n"


def write_outputs(cell_dir):
    """Write smoke_summary.txt and real_header.csv (header line only) into cell_dir; return the summary text."""
    cell_dir = Path(cell_dir)
    text = summary_text(cell_dir)
    (cell_dir / "smoke_summary.txt").write_text(text)
    (cell_dir / "real_header.csv").write_text(csv_header_line(cell_dir / "frames.csv") + "\n")
    return text
