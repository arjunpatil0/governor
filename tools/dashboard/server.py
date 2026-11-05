"""Co-Scheduler Lab dashboard server: serves tools/dashboard/index.html and streams JSON at about 20 Hz over Server-Sent Events. Python standard library (+ numpy and the project's own telemetry readers); no new packages.
   python tools/dashboard/server.py [--port 8765]        then open  http://127.0.0.1:8765/
Binds 127.0.0.1 ONLY (any other --host is refused), checks the Host and Origin headers (no DNS-rebinding / cross-site posts), and is READ-ONLY: it never writes a control block, a ring or the clock helper
(tools/dashboard/sources.py reads the frame / token rings and the pace / control / decision blocks, NVML sampled power and SM clock; never the NVML energy counter).
It is a separate low-priority process (BELOW_NORMAL on Windows). DO NOT RUN IT DURING REGISTERED EXPERIMENTS (evaluate.py, tune.py, w5a/run.py): it adds CPU load and NVML polling. It refuses to start while one is running
(override for tests only: --allow-during-experiment). Modes: SIM (nothing connected; the page's own simulator), REPLAY (a recorded cell of data/), LIVE (a running demo session published by tools/dashboard/demo.py).
HTTP API: GET / | /api/state | /api/cells | /api/stats | /stream (SSE: events hello, tick, reset, end) ; POST /api/source {mode: sim|replay|live, cell} | /api/replay {action: play|pause|speed|seek|restart, value}."""
import argparse
import json
import sys
import threading
import time
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(HERE))
import sources as src  # noqa: E402

ALLOWED_HOSTS = ("127.0.0.1", "localhost")
HZ = 20.0
DEFAULT_SESSION = ROOT / "data" / "dashboard_live" / "session.json"
REGISTERED_RUN_MARKERS = ("evaluate.py", "tune.py", "w5a\\run.py", "w5a/run.py", "morning.py")
MAX_BODY = 65536


def check_host(host):
    """The bind address: only the loopback interface is allowed."""
    if host not in ALLOWED_HOSTS:
        raise ValueError(f"refused: the dashboard binds 127.0.0.1 only (got {host!r})")
    return "127.0.0.1"


def registered_run_active(cmdlines):
    """True if any command line (list of strings) is a registered experiment runner."""
    return any(any(mk in " ".join(c) for mk in REGISTERED_RUN_MARKERS) and "dashboard" not in " ".join(c) for c in cmdlines if c)


def _running_cmdlines():
    try:
        import psutil
    except ImportError:
        return []
    out = []
    for p in psutil.process_iter(["cmdline", "name"]):
        try:
            if (p.info["name"] or "").lower().startswith("python"):
                out.append(p.info["cmdline"] or [])
        except Exception:                                                    # noqa: BLE001
            continue
    return out


def lower_priority():
    """BELOW_NORMAL priority class on Windows (the server must never compete with an experiment)."""
    try:
        import ctypes
        k = ctypes.windll.kernel32
        return bool(k.SetPriorityClass(k.GetCurrentProcess(), 0x00004000))
    except Exception:                                                        # noqa: BLE001
        return False


class Hub:
    """The one active source (LIVE / REPLAY / none = SIM), a pump thread that ticks it at HZ while at least one client listens, and a short ring of encoded messages that every SSE client reads by id."""

    def __init__(self, root=ROOT, session_file=DEFAULT_SESSION, poller_factory=None, hz=HZ):
        self.root, self.session_file, self.poller_factory, self.hz = Path(root), Path(session_file), poller_factory, hz
        self.cond = threading.Condition()
        self.msgs, self.next_id = deque(maxlen=600), 1
        self.source, self.mode, self.hello = None, "sim", None
        self.clients, self.stop = 0, threading.Event()
        self.t_start, self.cpu0 = time.perf_counter(), time.process_time()
        self._cells, self._cells_t = None, 0.0
        self.thread = threading.Thread(target=self._pump, daemon=True)
        self.thread.start()

    # ---- messages
    def _push(self, event, data):
        text = json.dumps(src.clean(data), allow_nan=False, separators=(",", ":"))
        with self.cond:
            self.msgs.append((self.next_id, event, text))
            if event == "hello":
                self.hello = (self.next_id, event, text)
            self.next_id += 1
            self.cond.notify_all()

    def wait_msgs(self, last_id, timeout=5.0):
        with self.cond:
            if not any(m[0] > last_id for m in self.msgs):
                self.cond.wait(timeout)
            return [m for m in self.msgs if m[0] > last_id]

    def latest_id(self):
        with self.cond:
            return self.next_id - 1

    # ---- source management
    def set_source(self, mode, cell=None):
        old, new = self.source, None
        if mode == "replay":
            new = src.ReplaySource(src.resolve_cell(self.root, cell), key=cell)
        elif mode == "live":
            s = src.read_session(self.session_file)
            if s is None:
                raise LookupError("no live session: start tools/dashboard/demo.py first")
            new = src.LiveSource(s, poller=self.poller_factory() if self.poller_factory else None)
        elif mode != "sim":
            raise ValueError(f"unknown mode {mode}")
        self.source, self.mode = new, mode if new is not None else "sim"
        if old is not None:
            old.close()
        self._push("reset", dict(mode=self.mode))
        self._push("hello", dict(mode=self.mode, meta=None if new is None else new.meta()))

    def control(self, action, value=None):
        if self.source is None or self.mode != "replay":
            raise LookupError("no replay is loaded")
        self.source.control(action, value)

    def client_enter(self):
        with self.cond:
            self.clients += 1
        if self.source is not None and self.mode == "replay":                           # a new page needs the events it has not seen: re-send from the current position
            self.source.control("seek", self.source.t)

    def client_leave(self):
        with self.cond:
            self.clients -= 1

    def cells(self):
        if self._cells is None or time.time() - self._cells_t > 5.0:
            self._cells, self._cells_t = src.list_cells(self.root), time.time()
        return self._cells

    def state(self):
        live = src.read_session(self.session_file)
        return dict(mode=self.mode, live_available=live is not None, live=None if live is None else {k: live.get(k) for k in ("id", "scene", "controller", "workload", "budget_w", "demo")}, clients=self.clients,
                    meta=None if self.source is None else self.source.meta())

    def stats(self):
        wall, cpu = time.perf_counter() - self.t_start, time.process_time() - self.cpu0
        return dict(cpu_s=cpu, wall_s=wall, cpu_pct_of_one_core=100.0 * cpu / wall if wall > 0 else None, clients=self.clients, mode=self.mode, hz=self.hz)

    # ---- pump
    def _pump(self):
        last = time.perf_counter()
        while not self.stop.is_set():
            time.sleep(max(0.0, 1.0 / self.hz - (time.perf_counter() - last)))
            now = time.perf_counter()
            dt, last = now - last, now
            if self.clients <= 0 or self.source is None:
                continue
            try:
                if self.mode == "live" and not self.source.alive():
                    self._push("end", dict(mode="live", reason="the live session ended"))
                    self.source.close(); self.source, self.mode = None, "sim"
                    continue
                self._push("tick", self.source.tick(dt))
            except Exception as ex:                                          # noqa: BLE001
                self._push("end", dict(mode=self.mode, reason=f"{type(ex).__name__}: {ex}"))
                self.source, self.mode = None, "sim"

    def close(self):
        self.stop.set()
        with self.cond:
            self.cond.notify_all()
        if self.source is not None:
            self.source.close()


class Handler(BaseHTTPRequestHandler):
    server_version = "CoSchedulerLab/1"
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):                                       # quiet; the page polls
        pass

    # ---- checks
    def _allowed_hosts(self):
        port = self.server.server_address[1]
        return {f"127.0.0.1:{port}", f"localhost:{port}"}

    def _guard(self):
        if self.headers.get("Host") not in self._allowed_hosts():
            self._json({"error": "bad Host header"}, 403)
            return False
        origin = self.headers.get("Origin")
        if origin is not None and origin not in {f"http://{h}" for h in self._allowed_hosts()}:
            self._json({"error": "bad Origin"}, 403)
            return False
        return True

    # ---- responses
    def _send(self, body, ctype, code=200):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code=200):
        self._send(json.dumps(src.clean(obj), allow_nan=False).encode("utf-8"), "application/json; charset=utf-8", code)

    def do_GET(self):
        if not self._guard():
            return
        path = self.path.split("?")[0]
        hub = self.server.hub
        if path in ("/", "/index.html"):
            p = HERE / "index.html"
            if not p.exists():
                return self._json({"error": "index.html missing"}, 404)
            return self._send(p.read_bytes(), "text/html; charset=utf-8")
        if path == "/favicon.ico":
            return self._send(b"", "image/x-icon", 204)
        if path == "/api/state":
            return self._json(hub.state())
        if path == "/api/cells":
            return self._json(hub.cells())
        if path == "/api/stats":
            return self._json(hub.stats())
        if path == "/stream":
            return self._stream()
        self._json({"error": "not found"}, 404)

    def do_POST(self):
        if not self._guard():
            return
        n = int(self.headers.get("Content-Length") or 0)
        if n > MAX_BODY or "json" not in (self.headers.get("Content-Type") or ""):
            return self._json({"error": "expected a small application/json body"}, 400)
        try:
            body = json.loads(self.rfile.read(n) or b"{}")
        except ValueError:
            return self._json({"error": "bad JSON"}, 400)
        hub = self.server.hub
        try:
            if self.path == "/api/source":
                hub.set_source(body.get("mode"), body.get("cell"))
                if body.get("mode") == "replay":
                    for k in ("speed",):
                        if k in body:
                            hub.control("speed", body[k])
                    if body.get("play") is False:
                        hub.control("pause")
                return self._json(hub.state())
            if self.path == "/api/replay":
                hub.control(body.get("action"), body.get("value"))
                return self._json({"ok": True})
        except (LookupError, ValueError, FileNotFoundError) as ex:
            return self._json({"error": str(ex)}, 400)
        self._json({"error": "not found"}, 404)

    # ---- server-sent events
    def _stream(self):
        hub = self.server.hub
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "keep-alive")
        self.end_headers()
        hub.client_enter()
        try:
            self.wfile.write(b"retry: 1000\n\n")
            last = hub.latest_id()
            first = hub.hello or (0, "hello", json.dumps(dict(mode="sim", meta=None)))
            self.wfile.write(f"id: {first[0]}\nevent: {first[1]}\ndata: {first[2]}\n\n".encode("utf-8"))
            self.wfile.flush()
            while not hub.stop.is_set():
                msgs = hub.wait_msgs(last, timeout=5.0)
                if not msgs:
                    self.wfile.write(b": keepalive\n\n")
                    self.wfile.flush()
                    continue
                for mid, ev, text in msgs:
                    self.wfile.write(f"id: {mid}\nevent: {ev}\ndata: {text}\n\n".encode("utf-8"))
                    last = mid
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
            pass
        finally:
            hub.client_leave()
        self.close_connection = True


class DashboardServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False                                              # on Windows SO_REUSEADDR lets a second process share the port (found: two servers answered on 8765); bind exclusively

    def __init__(self, host, port, hub):
        self.hub = hub                                                       # before binding: TCPServer calls server_close() if the bind fails
        super().__init__((check_host(host), port), Handler)

    def server_close(self):
        self.hub.close()
        super().server_close()


def make_server(host="127.0.0.1", port=8765, root=ROOT, session_file=DEFAULT_SESSION, poller_factory=None, hz=HZ):
    """A DashboardServer on the loopback interface (ValueError for any other host). port 0 = an ephemeral port (tests)."""
    check_host(host)
    return DashboardServer(host, port, Hub(root, session_file, poller_factory, hz))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--host", default="127.0.0.1"); ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--session-file", default=str(DEFAULT_SESSION))
    ap.add_argument("--allow-during-experiment", action="store_true", help="tests only: start even if a registered experiment runner is running")
    a = ap.parse_args(argv)
    try:
        check_host(a.host)
    except ValueError as ex:
        sys.exit(str(ex))
    if not a.allow_during_experiment and registered_run_active(_running_cmdlines()):
        sys.exit("refused: a registered experiment runner (evaluate.py / tune.py / w5a run.py) is running; the dashboard must not run during registered experiments")
    lower_priority()
    srv = make_server(a.host, a.port, session_file=a.session_file)
    print(f"Co-Scheduler Lab dashboard on http://127.0.0.1:{srv.server_address[1]}/  (read-only, low priority; do not run during registered experiments; Ctrl+C to stop)", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()


if __name__ == "__main__":
    main()
