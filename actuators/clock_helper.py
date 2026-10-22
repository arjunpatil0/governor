"""Minimal allowlisted SM-clock helper. Run ELEVATED (NVML clock locking needs admin); the governor talks to it over a named pipe.

Attack surface kept small on purpose:
- Verbs: LOCK <mhz>, RESET, HB (heartbeat), PING. Nothing else; lines are at most MAX_LINE bytes, ASCII, strictly parsed.
- LOCK values must be in the allowlist from a config file chosen by whoever starts the helper (never by the client); changes are rate limited.
- No subprocess, no shell, no eval, no file paths or free text from the client; the GPU is driven through NVML directly (pynvml).
- The pipe accepts local connections from the current user only (DACL = that user SID, remote clients rejected, one client at a time, first-instance flag).
Fail-safe: the lock is reset on startup, on RESET, on client disconnect, on watchdog timeout (no message for watchdog_s), on any exit path
(finally, atexit, console control events). NVML has no server-side lock expiry; if this process is killed hard the lock stays until
`nvidia-smi -rgc` (documented in docs/W45_PLAN.md).
Usage (Administrator PowerShell):  python actuators/clock_helper.py --config C:\\ProgramData\\governor\\clock_helper.json --log C:\\ProgramData\\governor\\clock_helper.log"""
import argparse
import atexit
import ctypes
import json
import logging
import re
import threading
import time
from dataclasses import dataclass
from pathlib import Path

PIPE_NAME = r"\\.\pipe\governor_clock"
MAX_LINE = 32
_LOCK_RE = re.compile(rb"^LOCK ([0-9]{3,4})\r?\n$")
_SIMPLE = {b"RESET": "RESET", b"HB": "HB", b"PING": "PING"}
MIN_MHZ, MAX_MHZ = 300, 3105          # RTX 4070 Laptop SM range (CLAUDE.md hardware section)
log = logging.getLogger("clock_helper")


class ProtocolError(ValueError):
    pass


@dataclass(frozen=True)
class Command:
    verb: str
    arg: int = None


def parse_command(line: bytes) -> Command:
    """Strict parse of ONE newline-terminated command. Anything else raises ProtocolError."""
    if not line or len(line) > MAX_LINE or not line.endswith(b"\n") or line.count(b"\n") != 1:
        raise ProtocolError("framing")
    m = _LOCK_RE.match(line)
    if m:
        mhz = int(m.group(1))
        if not MIN_MHZ <= mhz <= MAX_MHZ:
            raise ProtocolError("range")
        return Command("LOCK", mhz)
    verb = _SIMPLE.get(line.rstrip(b"\r\n"))
    if verb is None:
        raise ProtocolError("verb")
    return Command(verb)


class HelperCore:
    """State machine: allowlist, rate limit, watchdog. Thread-safe; the backend is injected (NvmlBackend in production, a fake in tests)."""

    def __init__(self, backend, allowed_mhz, watchdog_s=3.0, min_interval_s=1.0, now=time.monotonic):
        self.be, self.allowed, self.watchdog_s, self.min_interval_s, self.now = backend, frozenset(int(x) for x in allowed_mhz), watchdog_s, min_interval_s, now
        self.locked = None
        self.last_seen = self.now()
        self.last_lock = -1e18
        self.lk = threading.RLock()

    def _reset_backend(self):
        try:
            self.be.reset()
        except Exception:                                      # noqa: BLE001  a failing reset must be visible, not fatal to the watchdog
            log.exception("backend reset failed")
        self.locked = None

    def startup(self):
        with self.lk:
            self._reset_backend()
            log.info("startup: lock reset")

    def handle(self, cmd: Command) -> str:
        with self.lk:
            self.last_seen = self.now()
            if cmd.verb == "HB":
                return "OK"
            if cmd.verb == "PING":
                return f"OK {self.locked if self.locked else 'none'}"
            if cmd.verb == "RESET":
                self._reset_backend(); log.info("RESET")
                return "OK"
            if cmd.arg not in self.allowed:
                log.warning("rejected LOCK %s (not in allowlist)", cmd.arg)
                return "ERR NOT_ALLOWED"
            if self.now() - self.last_lock < self.min_interval_s:
                return "ERR RATE"
            try:
                self.be.lock(cmd.arg)
            except Exception:                                  # noqa: BLE001
                log.exception("backend lock failed")
                self._reset_backend()
                return "ERR BACKEND"
            self.locked, self.last_lock = cmd.arg, self.now()
            log.info("LOCK %d", cmd.arg)
            return "OK"

    def tick(self):
        """Watchdog: call at >= 4 Hz."""
        with self.lk:
            if self.locked and self.now() - self.last_seen > self.watchdog_s:
                log.warning("watchdog: no message for %.1f s, resetting lock %s", self.now() - self.last_seen, self.locked)
                self._reset_backend()

    def on_disconnect(self):
        with self.lk:
            self._reset_backend(); log.info("client disconnected: lock reset")

    def shutdown(self):
        with self.lk:
            self._reset_backend(); log.info("shutdown: lock reset")


class NvmlBackend:
    def __init__(self):
        import pynvml as nv
        self.nv = nv
        nv.nvmlInit()
        if nv.nvmlDeviceGetCount() != 1:
            raise RuntimeError("expected exactly one GPU")
        self.h = nv.nvmlDeviceGetHandleByIndex(0)

    def lock(self, mhz):
        self.nv.nvmlDeviceSetGpuLockedClocks(self.h, int(mhz), int(mhz))

    def reset(self):
        self.nv.nvmlDeviceResetGpuLockedClocks(self.h)


# ---------------------------------------------------------------- config
def _my_sid_string():
    import win32api
    import win32con
    import win32security
    tok = win32security.OpenProcessToken(win32api.GetCurrentProcess(), win32con.TOKEN_QUERY)
    return win32security.ConvertSidToStringSid(win32security.GetTokenInformation(tok, win32security.TokenUser)[0])


def _acl_ok(path):
    """Owner must be the current user, Administrators or SYSTEM, and no allow-ACE may give Everyone / Authenticated Users / Users any write access."""
    import ntsecuritycon as con
    import win32security
    sd = win32security.GetFileSecurity(str(path), win32security.OWNER_SECURITY_INFORMATION | win32security.DACL_SECURITY_INFORMATION)
    if win32security.ConvertSidToStringSid(sd.GetSecurityDescriptorOwner()) not in (_my_sid_string(), "S-1-5-32-544", "S-1-5-18"):
        return False
    writers = {"S-1-1-0", "S-1-5-11", "S-1-5-32-545"}
    write_bits = con.FILE_WRITE_DATA | con.FILE_APPEND_DATA | con.FILE_WRITE_ATTRIBUTES | con.DELETE | con.WRITE_DAC | con.WRITE_OWNER | con.GENERIC_WRITE | con.GENERIC_ALL
    dacl = sd.GetSecurityDescriptorDacl()
    for i in range(dacl.GetAceCount()):
        (ace_type, _flags), mask, sid = dacl.GetAce(i)
        if ace_type == win32security.ACCESS_ALLOWED_ACE_TYPE and win32security.ConvertSidToStringSid(sid) in writers and mask & write_bits:
            return False
    return True


def load_config(path, check_acl=True):
    p = Path(path)
    if check_acl and not _acl_ok(p):
        raise ValueError(f"config {p} is writable by non-administrators or has an unexpected owner")
    d = json.loads(p.read_text(encoding="utf-8"))
    if set(d) != {"allowed_mhz", "watchdog_s", "min_interval_s"}:
        raise ValueError("config keys must be exactly allowed_mhz, watchdog_s, min_interval_s")
    al = d["allowed_mhz"]
    if not isinstance(al, list) or not 1 <= len(al) <= 32 or not all(isinstance(x, int) and not isinstance(x, bool) and MIN_MHZ <= x <= MAX_MHZ for x in al):
        raise ValueError("allowed_mhz must be 1-32 integers within the SM range")
    if not (isinstance(d["watchdog_s"], (int, float)) and 0.5 <= d["watchdog_s"] <= 30):
        raise ValueError("watchdog_s must be 0.5-30")
    if not (isinstance(d["min_interval_s"], (int, float)) and 0 <= d["min_interval_s"] <= 60):
        raise ValueError("min_interval_s must be 0-60")
    return d


# ---------------------------------------------------------------- named pipe
def current_user_sddl():
    import win32api
    import win32security
    sid = win32security.LookupAccountName(None, win32api.GetUserName())[0]
    return f"D:P(A;;GA;;;{win32security.ConvertSidToStringSid(sid)})"


class PipeServer:
    FIRST_INSTANCE = 0x00080000

    def __init__(self, core, name=PIPE_NAME):
        self.core, self.name = core, name
        self.stop_flag = threading.Event()
        self.ready = threading.Event()

    def _create(self):
        import win32pipe
        import win32security
        sa = win32security.SECURITY_ATTRIBUTES()
        sa.SECURITY_DESCRIPTOR = win32security.ConvertStringSecurityDescriptorToSecurityDescriptor(current_user_sddl(), win32security.SDDL_REVISION_1)
        return win32pipe.CreateNamedPipe(self.name, win32pipe.PIPE_ACCESS_DUPLEX | self.FIRST_INSTANCE,
                                         win32pipe.PIPE_TYPE_BYTE | win32pipe.PIPE_READMODE_BYTE | win32pipe.PIPE_WAIT | win32pipe.PIPE_REJECT_REMOTE_CLIENTS,
                                         1, 256, 256, 0, sa)

    def _serve_client(self, h):
        import win32file
        buf = b""
        while not self.stop_flag.is_set():
            try:
                _hr, data = win32file.ReadFile(h, MAX_LINE + 1)
            except Exception:                                  # noqa: BLE001  broken pipe = client gone
                return
            buf += bytes(data)
            while b"\n" in buf:
                line, buf = buf[:buf.index(b"\n") + 1], buf[buf.index(b"\n") + 1:]
                try:
                    resp = self.core.handle(parse_command(line))
                except ProtocolError:
                    resp = "ERR PROTOCOL"
                try:
                    win32file.WriteFile(h, (resp + "\n").encode("ascii"))
                except Exception:                              # noqa: BLE001
                    return
            if len(buf) > MAX_LINE:                            # no newline within the limit: drop the connection
                try:
                    win32file.WriteFile(h, b"ERR PROTOCOL\n")
                except Exception:                              # noqa: BLE001
                    pass
                return

    def serve_forever(self):
        import win32file
        import win32pipe
        h = self._create()
        self.ready.set()
        try:
            while not self.stop_flag.is_set():
                try:
                    win32pipe.ConnectNamedPipe(h, None)
                except Exception:                              # noqa: BLE001
                    break
                if self.stop_flag.is_set():
                    break
                try:
                    self._serve_client(h)
                finally:
                    self.core.on_disconnect()
                    try:
                        win32pipe.DisconnectNamedPipe(h)
                    except Exception:                          # noqa: BLE001
                        pass
        finally:
            win32file.CloseHandle(h)

    def stop(self):
        self.stop_flag.set()
        try:                                                   # unblock ConnectNamedPipe / ReadFile with a throwaway connection
            import win32file
            c = win32file.CreateFile(self.name, win32file.GENERIC_READ | win32file.GENERIC_WRITE, 0, None, win32file.OPEN_EXISTING, 0, None)
            win32file.CloseHandle(c)
        except Exception:                                      # noqa: BLE001
            pass


# ---------------------------------------------------------------- entry point
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--log", required=True)
    ap.add_argument("--pipe", default=PIPE_NAME)
    a = ap.parse_args()
    logging.basicConfig(filename=a.log, level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if not ctypes.windll.shell32.IsUserAnAdmin():
        raise SystemExit("clock_helper must run elevated (NVML clock locking needs administrator rights)")
    cfg = load_config(a.config)
    core = HelperCore(NvmlBackend(), cfg["allowed_mhz"], cfg["watchdog_s"], cfg["min_interval_s"])
    srv = PipeServer(core, a.pipe)
    handler_type = ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_uint)

    @handler_type
    def on_ctrl(_event):                                       # Ctrl+C, Ctrl+Break, console close, logoff, shutdown
        core.shutdown()
        return 0

    ctypes.windll.kernel32.SetConsoleCtrlHandler(on_ctrl, True)
    atexit.register(core.shutdown)
    core.startup()
    stop = threading.Event()

    def watchdog():
        while not stop.wait(0.25):
            core.tick()

    threading.Thread(target=watchdog, daemon=True).start()
    try:
        print(f"clock helper listening on {a.pipe}; allowed {sorted(cfg['allowed_mhz'])} MHz; Ctrl+C to stop (the lock is reset on exit)")
        srv.serve_forever()
    finally:
        stop.set()
        core.shutdown()


if __name__ == "__main__":
    main()
