"""Client for the admin clock helper (actuators/clock_helper.py): LOCK / RESET / HB / PING over the named pipe. Not elevated."""
import win32file

PIPE_NAME = r"\\.\pipe\governor_clock"


class ClockClient:
    def __init__(self, name=PIPE_NAME):
        self.h = win32file.CreateFile(name, win32file.GENERIC_READ | win32file.GENERIC_WRITE, 0, None, win32file.OPEN_EXISTING, 0, None)
        self.last_response = None

    def _ask(self, line):
        win32file.WriteFile(self.h, line.encode("ascii") + b"\n")
        _hr, data = win32file.ReadFile(self.h, 64)
        self.last_response = bytes(data).decode("ascii").strip()
        return self.last_response

    def lock(self, mhz):
        return self._ask(f"LOCK {int(mhz)}") == "OK"

    def reset(self):
        return self._ask("RESET") == "OK"

    def heartbeat(self):
        return self._ask("HB") == "OK"

    def ping(self):
        return self._ask("PING")

    def close(self):
        if self.h is not None:
            win32file.CloseHandle(self.h)
            self.h = None
