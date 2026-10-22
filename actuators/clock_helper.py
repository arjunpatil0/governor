"""Minimal allowlisted SM-clock helper. Run ELEVATED (NVML clock locking needs admin); the governor talks to it over a named pipe.

Attack surface kept small on purpose:
- Verbs: LOCK <mhz>, RESET, HB (heartbeat), PING. Nothing else; lines are at most MAX_LINE bytes, ASCII, strictly parsed.
- LOCK values must be in the allowlist from a config file chosen by whoever starts the helper (never by the client); changes are rate limited.
- The config file and its directory must be owned and writable only by SYSTEM / Administrators (the unprivileged client runs as the same user and must not be able
  to widen its own allowlist); the file is opened once, checked on that handle and read from it (no path re-open, reparse points refused).
- No subprocess, no shell, no eval, no file paths or free text from the client; the GPU is driven through NVML directly (pynvml).
- The pipe accepts local connections from the current user only (DACL = the token SID with data-access rights only, remote clients rejected, one client at a time,
  first-instance flag). An idle client is disconnected after idle_s so it cannot occupy the only instance.
Fail-safe: the lock is reset on startup (startup aborts if that fails), on RESET, on client disconnect, on watchdog timeout (no message for watchdog_s), on any exit
path (finally, atexit, console control events, after which the process exits). A reset that FAILS is remembered (state `dirty`) and retried every second; PING / HB report
it. NVML has no server-side lock expiry; if this process is killed hard the lock stays until the next helper start or `nvidia-smi -rgc` (docs/W45_PLAN.md).
Setup (Administrator PowerShell, once): create C:\\ProgramData\\governor with `icacls C:\\ProgramData\\governor /inheritance:r /grant "SYSTEM:(OI)(CI)F" "Administrators:(OI)(CI)F"`,
write clock_helper.json there from the elevated shell (it is then Administrators-owned), then
  python actuators/clock_helper.py --config C:\\ProgramData\\governor\\clock_helper.json --log C:\\ProgramData\\governor\\clock_helper.log"""
import argparse
import atexit
import ctypes
import json
import logging
import logging.handlers
import os
import re
import threading
import time
from dataclasses import dataclass
from pathlib import Path

PIPE_NAME = r"\\.\pipe\governor_clock"
PIPE_ACCESS_MASK = 0x0012019B         # FILE_READ_DATA | FILE_WRITE_DATA | READ_EA | WRITE_EA | READ_ATTR | WRITE_ATTR | READ_CONTROL | SYNCHRONIZE (no WRITE_DAC / WRITE_OWNER / APPEND)
MAX_LINE = 32
_CMD_RE = re.compile(rb"^(?:LOCK ([0-9]{3,4})|(RESET|HB|PING))\r?\n$")
MIN_MHZ, MAX_MHZ = 300, 3105          # RTX 4070 Laptop SM range (CLAUDE.md hardware section)
TRUSTED_WRITERS = frozenset({"S-1-5-18", "S-1-5-32-544", "S-1-5-80-956008885-3418522649-1831038044-1853292631-2271478464"})     # SYSTEM, Administrators, TrustedInstaller
log = logging.getLogger("clock_helper")


class ProtocolError(ValueError):
    pass


@dataclass(frozen=True)
class Command:
    verb: str
    arg: int = None


def parse_command(line: bytes) -> Command:
    """Strict parse of ONE newline-terminated command. Anything else raises ProtocolError."""
    if not line or len(line) > MAX_LINE:
        raise ProtocolError("framing")
    m = _CMD_RE.match(line)
    if not m:
        raise ProtocolError("verb")
    if m.group(1):
        mhz = int(m.group(1))
        if not MIN_MHZ <= mhz <= MAX_MHZ:
            raise ProtocolError("range")
        return Command("LOCK", mhz)
    return Command(m.group(2).decode("ascii"))


class HelperCore:
    """State machine: allowlist, rate limit, watchdog. Thread-safe; the backend is injected (NvmlBackend in production, a fake in tests)."""

    def __init__(self, backend, allowed_mhz, watchdog_s=3.0, min_interval_s=1.0, now=time.monotonic, retry_s=1.0):
        self.be, self.allowed, self.watchdog_s, self.min_interval_s, self.now, self.retry_s = backend, frozenset(int(x) for x in allowed_mhz), watchdog_s, min_interval_s, now, retry_s
        self.locked = None
        self.dirty = False                                     # a reset failed and must be retried
        self.closed = False
        self.last_seen = self.now()
        self.last_lock = -1e18
        self.last_retry = -1e18
        self._last_note, self._suppressed = -1e18, 0
        self.lk = threading.RLock()

    def _note(self, level, msg, *args):
        """Rate-limited logging (one line per second, with a count of suppressed lines): untrusted input must not be able to flood the log."""
        t = self.now()
        if t - self._last_note >= 1.0:
            extra = f" (+{self._suppressed} suppressed)" if self._suppressed else ""
            log.log(level, msg + extra, *args)
            self._last_note, self._suppressed = t, 0
        else:
            self._suppressed += 1

    def _reset_backend(self):
        try:
            self.be.reset()
        except Exception:                                      # noqa: BLE001  a failing reset must be remembered and retried, never forgotten
            log.exception("backend reset failed; will retry")
            self.dirty = True
            self.last_retry = self.now()
            return False
        self.locked, self.dirty = None, False
        return True

    def _state(self):
        return "dirty" if self.dirty else (str(self.locked) if self.locked else "none")

    def startup(self):
        with self.lk:
            ok = self._reset_backend()
            log.info("startup: lock reset %s", "ok" if ok else "FAILED")
            return ok

    def handle(self, cmd: Command) -> str:
        with self.lk:
            if self.closed:
                return "ERR SHUTDOWN"
            self.last_seen = self.now()
            if cmd.verb in ("HB", "PING"):
                return f"OK {self._state()}"
            if cmd.verb == "RESET":
                ok = self._reset_backend()
                self._note(logging.INFO, "RESET %s", "ok" if ok else "FAILED")
                return "OK" if ok else "ERR BACKEND"
            if cmd.arg not in self.allowed:
                self._note(logging.WARNING, "rejected LOCK %s (not in allowlist)", cmd.arg)
                return "ERR NOT_ALLOWED"
            if self.now() - self.last_lock < self.min_interval_s:
                return "ERR RATE"
            self.last_lock = self.now()                        # failed attempts count too: a client cannot hammer the driver
            try:
                self.be.lock(cmd.arg)
            except Exception:                                  # noqa: BLE001
                log.exception("backend lock failed")
                self._reset_backend()
                return "ERR BACKEND"
            self.locked = cmd.arg
            log.info("LOCK %d", cmd.arg)
            return "OK"

    def tick(self):
        """Watchdog: call at >= 4 Hz. Resets a lock whose client went silent and retries a failed reset."""
        with self.lk:
            t = self.now()
            expired = bool(self.locked) and t - self.last_seen > self.watchdog_s
            if (self.dirty or expired) and t - self.last_retry >= (self.retry_s if self.dirty else 0.0):
                if expired:
                    log.warning("watchdog: no message for %.1f s, resetting lock %s", t - self.last_seen, self.locked)
                self.last_retry = t
                self._reset_backend()

    def on_disconnect(self):
        with self.lk:
            ok = self._reset_backend()
            self._note(logging.INFO, "client disconnected: lock reset %s", "ok" if ok else "FAILED")

    def shutdown(self):
        with self.lk:
            self.closed = True
            ok = self._reset_backend()
            log.info("shutdown: lock reset %s", "ok" if ok else "FAILED")
            return ok


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


# ---------------------------------------------------------------- config trust
_WRITE_BITS = 0x2 | 0x4 | 0x10 | 0x40 | 0x100 | 0x10000 | 0x40000 | 0x80000 | 0x40000000 | 0x10000000


def _my_sid_string():
    import win32api
    import win32con
    import win32security
    tok = win32security.OpenProcessToken(win32api.GetCurrentProcess(), win32con.TOKEN_QUERY)
    try:
        return win32security.ConvertSidToStringSid(win32security.GetTokenInformation(tok, win32security.TokenUser)[0])
    finally:
        tok.Close()


def _sd_trusted(sd, trusted):
    """Owner must be trusted and every allow-ACE granting any write/delete/ownership right must belong to a trusted SID (an allowlist, not a blacklist)."""
    import win32security
    if win32security.ConvertSidToStringSid(sd.GetSecurityDescriptorOwner()) not in trusted:
        return False
    dacl = sd.GetSecurityDescriptorDacl()
    if dacl is None:
        return False                                           # NULL DACL = everyone full control
    for i in range(dacl.GetAceCount()):
        (ace_type, _flags), mask, sid = dacl.GetAce(i)
        s = win32security.ConvertSidToStringSid(sid)
        if ace_type == win32security.ACCESS_ALLOWED_ACE_TYPE and mask & _WRITE_BITS and s not in trusted and s not in ("S-1-3-4", "S-1-3-0"):     # OWNER RIGHTS / CREATOR OWNER = the owner, already required to be trusted
            return False
    return True


def _path_trusted(path, trusted):
    import win32security
    sd = win32security.GetFileSecurity(str(path), win32security.OWNER_SECURITY_INFORMATION | win32security.DACL_SECURITY_INFORMATION)
    return _sd_trusted(sd, trusted)


def _read_checked(path, trusted):
    """Open once (no write sharing, reparse points not followed), check owner/DACL on THAT handle, read from it."""
    import win32file
    import win32security
    h = win32file.CreateFile(str(path), win32file.GENERIC_READ | 0x20000, win32file.FILE_SHARE_READ, None, win32file.OPEN_EXISTING, 0x00200000, None)   # FILE_FLAG_OPEN_REPARSE_POINT
    try:
        if win32file.GetFileInformationByHandle(h)[0] & 0x400:
            raise ValueError(f"config {path} is a reparse point")
        sd = win32security.GetSecurityInfo(h, win32security.SE_FILE_OBJECT, win32security.OWNER_SECURITY_INFORMATION | win32security.DACL_SECURITY_INFORMATION)
        if not _sd_trusted(sd, trusted):
            raise ValueError(f"config {path} is owned or writable by an untrusted account (must be SYSTEM/Administrators only)")
        size = win32file.GetFileSize(h)
        if size > 4096:
            raise ValueError("config too large")
        return bytes(win32file.ReadFile(h, size)[1]).decode("utf-8")
    finally:
        h.Close()


def load_config(path, check_acl=True, trusted_sids=frozenset()):
    p = Path(path)
    if check_acl:
        trusted = TRUSTED_WRITERS | frozenset(trusted_sids)
        if not _path_trusted(p.parent, trusted):
            raise ValueError(f"directory {p.parent} is owned or writable by an untrusted account")
        text = _read_checked(p, trusted)
    else:
        text = p.read_text(encoding="utf-8")
    d = json.loads(text)
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
    return f"D:P(A;;0x{PIPE_ACCESS_MASK:08x};;;{_my_sid_string()})"


class PipeServer:
    FIRST_INSTANCE = 0x00080000

    def __init__(self, core, name=PIPE_NAME, idle_s=10.0):
        self.core, self.name, self.idle_s = core, name, idle_s
        self.stop_flag = threading.Event()
        self.ready = threading.Event()
        self.h = None
        self.connected = False
        self.last_activity = time.monotonic()

    def _create(self):
        import win32pipe
        import win32security
        sa = win32security.SECURITY_ATTRIBUTES()
        sa.SECURITY_DESCRIPTOR = win32security.ConvertStringSecurityDescriptorToSecurityDescriptor(current_user_sddl(), win32security.SDDL_REVISION_1)
        return win32pipe.CreateNamedPipe(self.name, win32pipe.PIPE_ACCESS_DUPLEX | self.FIRST_INSTANCE,
                                         win32pipe.PIPE_TYPE_BYTE | win32pipe.PIPE_READMODE_BYTE | win32pipe.PIPE_WAIT | win32pipe.PIPE_REJECT_REMOTE_CLIENTS,
                                         1, 256, 256, 0, sa)

    def _monitor(self):
        """Boots a client that has been silent for idle_s (it would otherwise hold the only pipe instance forever)."""
        while not self.stop_flag.wait(0.1):
            if self.connected and time.monotonic() - self.last_activity > self.idle_s:
                log.warning("idle client disconnected after %.1f s", self.idle_s)
                self.connected = False
                # CancelIoEx is not serialised with the blocked ReadFile of the serving thread (DisconnectNamedPipe would be); that thread then disconnects
                ctypes.windll.kernel32.CancelIoEx(ctypes.c_void_p(int(self.h)), None)

    def _serve_client(self, h):
        import win32file
        buf = b""
        while not self.stop_flag.is_set():
            try:
                _hr, data = win32file.ReadFile(h, MAX_LINE + 1)
            except Exception:                                  # noqa: BLE001  broken pipe / cancelled = client gone
                return
            self.last_activity = time.monotonic()
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
        h = self.h = self._create()
        threading.Thread(target=self._monitor, daemon=True).start()
        self.ready.set()
        try:
            while not self.stop_flag.is_set():
                try:
                    win32pipe.ConnectNamedPipe(h, None)
                except Exception:                              # noqa: BLE001
                    break
                if self.stop_flag.is_set():
                    break
                self.last_activity, self.connected = time.monotonic(), True
                try:
                    self._serve_client(h)
                finally:
                    self.connected = False
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
            c = win32file.CreateFile(self.name, PIPE_ACCESS_MASK, 0, None, win32file.OPEN_EXISTING, 0, None)
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
    if not ctypes.windll.shell32.IsUserAnAdmin():
        raise SystemExit("clock_helper must run elevated (NVML clock locking needs administrator rights)")
    if not _path_trusted(Path(a.log).resolve().parent, TRUSTED_WRITERS):
        raise SystemExit("log directory must be owned and writable only by SYSTEM / Administrators (see the setup note at the top of clock_helper.py)")
    h = logging.handlers.RotatingFileHandler(a.log, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logging.getLogger().addHandler(h)
    logging.getLogger().setLevel(logging.INFO)
    cfg = load_config(a.config)
    core = HelperCore(NvmlBackend(), cfg["allowed_mhz"], cfg["watchdog_s"], cfg["min_interval_s"])
    if not core.startup():
        raise SystemExit("startup reset failed: NVML clock control does not work here; not serving")
    srv = PipeServer(core, a.pipe)
    handler_type = ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_uint)

    @handler_type
    def on_ctrl(_event):                                       # Ctrl+C, Ctrl+Break, console close, logoff, shutdown: reset, stop serving, exit
        core.shutdown()
        srv.stop()
        logging.shutdown()
        os._exit(0)

    ctypes.windll.kernel32.SetConsoleCtrlHandler(on_ctrl, True)
    atexit.register(core.shutdown)
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
