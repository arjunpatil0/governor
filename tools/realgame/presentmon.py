"""PresentMon 2.6.0 CSV schema, parser and capture wrapper (sprint R1).

The PresentMon docs conflict: the v2.6.0 README names columns with an Ms prefix (MsCPUBusy, MsGPULatency, MsGPUBusy, MsBetweenAppStart) while the tag's own gold CSV uses
CPUBusy, GPULatency, GPUBusy, FrameTime. PM_ALIASES accepts both. The real header of this machine's build replaces the synthetic sample after the smoke cell.
Units: the README states "All time values are in milliseconds", so FrameTime/GPUBusy/GPULatency are read as ms and nothing is converted. CPUStartQPC is a raw performance-counter
value whose unit is not documented: Frame.t_cpu_start keeps it raw and seconds = value / qpc_hz (to_seconds), with qpc_hz supplied by the harness (QueryPerformanceFrequency)."""
import csv
import io
import os
import signal
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

PM_ALIASES = {
    "cpu_start": ("CPUStartQPC",),
    "frame_ms": ("FrameTime", "MsBetweenAppStart"),
    "gpu_busy_ms": ("GPUBusy", "MsGPUBusy"),
    "gpu_latency_ms": ("GPULatency", "MsGPULatency"),
    "displayed_time": ("DisplayedTime",),
}

_README_COLUMNS = (
    "Application ProcessID SwapChainAddress PresentRuntime SyncInterval PresentFlags VidPnSourceId LayerIndex AllowsTearing PresentMode FrameType "
    "CPUStartTime CPUStartQPC CPUStartQPCTime CPUStartDateTime MsCPUBusy MsCPUWait MsGPULatency MsGPUTime MsGPUBusy MsGPUWait VideoBusy DisplayLatency DisplayedTime "
    "MsAnimationError AnimationTime MsClickToPhotonLatency MsAllInputToPhotonLatency InstrumentedLatency MsBetweenPresents MsInPresentAPI MsBetweenDisplayChange "
    "MsUntilDisplayed MsRenderPresentLatency MsBetweenSimulationStart MsPCLatency MsBetweenAppStart PresentId").split()
_GOLD_COLUMNS = (
    "Application ProcessID SwapChainAddress PresentRuntime SyncInterval PresentFlags AllowsTearing PresentMode FrameType CPUStartQPC FrameTime CPUBusy CPUWait GPULatency "
    "GPUTime GPUBusy GPUWait VideoBusy DisplayLatency DisplayedTime AnimationError AnimationTime MsFlipDelay AllInputToPhotonLatency ClickToPhotonLatency InstrumentedLatency").split()
KNOWN_COLUMNS = frozenset(_README_COLUMNS) | frozenset(_GOLD_COLUMNS)

# Flags verified for PresentMon 2.6.0 (console build).
_FLAGS = ["--v2_metrics", "--qpc_time", "--no_console_stats"]


MAX_CSV_BYTES = 500 * 1024 * 1024        # a PresentMon CSV larger than this is refused (hostile or runaway capture)


class PresentMonError(ValueError):
    pass


class PresentMonGapError(PresentMonError):
    """The capture does not cover the window continuously (the cell fails and the whole rep is rerun)."""


class UnknownColumnError(PresentMonError):
    pass


class MissingColumnError(PresentMonError):
    pass


@dataclass(frozen=True)
class Frame:
    t_cpu_start: float      # raw CPUStartQPC counter value (NOT seconds)
    frame_ms: float
    gpu_busy_ms: float
    gpu_latency_ms: float
    displayed: bool         # False when DisplayedTime is 'NA'; such frames are kept
    swapchain: "str | None"
    present_mode: "str | None"


def to_seconds(qpc_value, qpc_hz):
    if not qpc_hz or qpc_hz <= 0:
        raise ValueError(f"qpc_hz must be a positive counter frequency, got {qpc_hz!r}")
    return qpc_value / qpc_hz


def _read_file(p):
    if not p.exists():
        _raise_missing(p)
    size = p.stat().st_size
    if size > MAX_CSV_BYTES:
        raise PresentMonError(f"PresentMon CSV {p} is too large: size {size} bytes exceeds the cap of {MAX_CSV_BYTES}")
    return p.read_text(encoding="utf-8-sig")


def _read(path_or_text):
    if isinstance(path_or_text, Path):
        return _read_file(path_or_text)
    if isinstance(path_or_text, str) and ("\n" in path_or_text or "," in path_or_text):
        if len(path_or_text) > MAX_CSV_BYTES:
            raise PresentMonError(f"PresentMon CSV text is too large: size {len(path_or_text)} exceeds the cap of {MAX_CSV_BYTES}")
        return path_or_text
    return _read_file(Path(path_or_text))


def _raise_missing(p):
    raise PresentMonError(f"PresentMon CSV not found: {p}")


def _num(row, col, line):
    v = row.get(col)
    try:
        x = float(v)
    except (TypeError, ValueError):
        raise PresentMonError(f"line {line}: column {col} is not a number: {v!r}") from None
    if x != x:
        raise PresentMonError(f"line {line}: column {col} is NaN")
    return x


def _field(header, logical):
    present = [a for a in PM_ALIASES[logical] if a in header]
    if not present:
        raise MissingColumnError(f"{logical}: none of {PM_ALIASES[logical]} is in the CSV header")
    return present


def parse_csv(path_or_text):
    """-> list[Frame]. Raises PresentMonError (empty), UnknownColumnError (column not in KNOWN_COLUMNS), MissingColumnError (a logical field has no alias present, or two aliases of
    one field disagree in a row). A header-only file gives []. Dropped frames (DisplayedTime NA) are kept with displayed=False."""
    text = _read(path_or_text)
    if not text.strip():
        raise PresentMonError("PresentMon CSV is empty (no header)")
    reader = csv.DictReader(io.StringIO(text.lstrip("\r\n")))
    try:
        header = reader.fieldnames or []
    except csv.Error as e:
        raise PresentMonError(f"malformed PresentMon CSV header (csv.Error): {e}") from None
    unknown = [c for c in header if c not in KNOWN_COLUMNS]
    if unknown:
        raise UnknownColumnError(f"unknown PresentMon column(s) {unknown}: add them to KNOWN_COLUMNS only after reading the real header and docs")
    cols = {k: _field(header, k) for k in PM_ALIASES}
    frames = []
    try:
        for row in reader:
            _parse_row(row, reader.line_num, cols, frames)
    except csv.Error as e:
        raise PresentMonError(f"malformed PresentMon CSV (csv.Error at line {reader.line_num}): {e}") from None
    return frames


def _parse_row(row, line, cols, frames):
    if not any(row.values()):
        return
    vals = {}
    for logical in ("frame_ms", "gpu_busy_ms", "gpu_latency_ms"):
        nums = [_num(row, a, line) for a in cols[logical]]
        if len(set(nums)) > 1:
            raise MissingColumnError(f"{logical}: aliases {cols[logical]} disagree at line {line}: {nums}")
        vals[logical] = nums[0]
    start = _num(row, cols["cpu_start"][0], line)
    disp = (row.get(cols["displayed_time"][0]) or "").strip()
    if disp == "":
        raise PresentMonError(f"line {line}: DisplayedTime is blank (expected a number or NA)")
    frames.append(Frame(start, vals["frame_ms"], vals["gpu_busy_ms"], vals["gpu_latency_ms"], disp.upper() != "NA", row.get("SwapChainAddress"), row.get("PresentMode")))


def dominant_swapchain(frames):
    """The swapchain address with the most frames (ties: first seen). Raises ValueError on no frames."""
    if not frames:
        raise ValueError("no frames")
    counts = Counter(f.swapchain for f in frames)
    best = max(counts.values())
    return next(f.swapchain for f in frames if counts[f.swapchain] == best)


def frames_of_swapchain(frames, swapchain):
    return [f for f in frames if f.swapchain == swapchain]


def check_window_continuity(frames, t_open, t_close, qpc_hz, max_edge_s=0.1, max_gap_s=0.5, min_fps=60.0, min_share=0.95):
    """Raises PresentMonGapError unless the window frames (one swapchain, start QPC in [t_open, t_close)) cover the window: the first frame starts at most max_edge_s after t_open,
    the last frame ends (start + frame time) at most max_edge_s before t_close, no gap between consecutive frame starts exceeds max_gap_s, and the frame count is at least
    min_share x min_fps x window length (0.95 x 60 x 60 = 3420 for the 60 s window)."""
    st = sorted(to_seconds(f.t_cpu_start, qpc_hz) for f in frames)
    if not st:
        raise PresentMonGapError("no frames in the window")
    last = max(to_seconds(f.t_cpu_start, qpc_hz) + f.frame_ms / 1000.0 for f in frames)
    if st[0] - t_open > max_edge_s:
        raise PresentMonGapError(f"first window frame starts {st[0] - t_open:.3f} s after t_open (limit {max_edge_s} s)")
    if t_close - last > max_edge_s:
        raise PresentMonGapError(f"last window frame ends {t_close - last:.3f} s before t_close (limit {max_edge_s} s)")
    worst = max((b - a for a, b in zip(st, st[1:])), default=0.0)
    if worst > max_gap_s:
        raise PresentMonGapError(f"gap of {worst:.3f} s between consecutive frame starts (limit {max_gap_s} s)")
    need = min_share * min_fps * (t_close - t_open)
    if len(st) < need:
        raise PresentMonGapError(f"frame count {len(st)} is below {min_share} x {min_fps:g} x {t_close - t_open:g} s = {need:.0f}")


class Capture:
    """PresentMon console capture of one process. popen is injectable for tests."""

    def __init__(self, exe, process_name, out_csv, session_name, timed_s=None, popen=subprocess.Popen):
        self.exe, self.process_name, self.out_csv, self.session_name, self.timed_s = exe, process_name, out_csv, session_name, timed_s
        self._popen, self.proc, self._stopped = popen, None, False

    @staticmethod
    def build_cmd(exe, process_name, out_csv, session_name, timed_s=None):
        cmd = [str(exe), *_FLAGS, "--process_name", str(process_name), "--output_file", str(out_csv), "--session_name", str(session_name), "--stop_existing_session"]
        if timed_s is not None:
            cmd += ["--timed", str(timed_s), "--terminate_after_timed"]
        return cmd

    def start(self):
        cmd = self.build_cmd(self.exe, self.process_name, self.out_csv, self.session_name, self.timed_s)
        kw = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL, "stdin": subprocess.DEVNULL}
        if sys.platform == "win32":
            kw["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        self.proc = self._popen(cmd, **kw)
        self._stopped = False
        return self.proc

    def stop(self, timeout=10.0):
        """Graceful stop (console Ctrl+Break on Windows, SIGINT elsewhere), then kill after `timeout` seconds. Idempotent."""
        if self.proc is None:
            raise RuntimeError("Capture.stop() before start()")
        if self._stopped:
            return self.proc.poll()
        self._stopped = True
        if self.proc.poll() is None:
            try:
                self.proc.send_signal(getattr(signal, "CTRL_BREAK_EVENT", signal.SIGINT) if sys.platform == "win32" else signal.SIGINT)
            except OSError:
                pass
            try:
                self.proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                try:
                    self.proc.wait(timeout=timeout)
                except subprocess.TimeoutExpired:
                    pass
        return self.proc.poll()


def version(exe, run=subprocess.run):
    """First line printed by `<exe> --version` (UNVERIFIED that 2.6.0 supports this flag: the smoke cell checks it). Raises RuntimeError if the call fails or prints nothing."""
    r = run([str(exe), "--version"], capture_output=True, text=True, timeout=30)
    out = ((r.stdout or "") + (r.stderr or "")).strip()
    if r.returncode != 0 or not out:
        raise RuntimeError(f"{exe} --version failed (rc={r.returncode}): {out!r}")
    return out.splitlines()[0].strip()
