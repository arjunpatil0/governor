"""GPU scheduling priority class of a process (D3DKMTSetProcessSchedulingPriorityClass / D3DKMTGetProcessSchedulingPriorityClass in gdi32).

CLASSES is UNVERIFIED against d3dkmthk.h (D3DKMT_SCHEDULINGPRIORITYCLASS): the values below are the recalled order IDLE..REALTIME. The cell logs the read-back and the preregistration
treats a read-back that differs from the requested idle class as invalid (PRIO_IDLE void). Whether WDDM applies the class to CUDA compute queues is the experiment itself.
gdi32/kernel32 are injectable so tests use fakes; the real libraries are loaded lazily with explicit argtypes/restype (nothing Windows-specific happens at import)."""
import ctypes

CLASSES = {"IDLE": 0, "BELOW_NORMAL": 1, "NORMAL": 2, "ABOVE_NORMAL": 3, "HIGH": 4, "REALTIME": 5}
CLASSES_VERIFIED = False
PROCESS_SET_INFORMATION = 0x0200
PROCESS_QUERY_INFORMATION = 0x0400


class PriorityError(RuntimeError):
    def __init__(self, msg, set_status=None, readback=None):
        super().__init__(msg)
        self.set_status, self.readback = set_status, readback


def _real_libs():
    from ctypes import wintypes
    gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    k32.OpenProcess.restype = wintypes.HANDLE
    k32.CloseHandle.argtypes = [wintypes.HANDLE]
    k32.CloseHandle.restype = wintypes.BOOL
    gdi32.D3DKMTSetProcessSchedulingPriorityClass.argtypes = [wintypes.HANDLE, ctypes.c_int]
    gdi32.D3DKMTSetProcessSchedulingPriorityClass.restype = ctypes.c_long       # NTSTATUS
    gdi32.D3DKMTGetProcessSchedulingPriorityClass.argtypes = [wintypes.HANDLE, ctypes.POINTER(ctypes.c_int)]
    gdi32.D3DKMTGetProcessSchedulingPriorityClass.restype = ctypes.c_long
    return gdi32, k32


def _libs(gdi32, k32):
    if gdi32 is None or k32 is None:
        g, k = _real_libs()
        return gdi32 or g, k32 or k
    return gdi32, k32


def _cls_value(cls):
    v = CLASSES[cls] if isinstance(cls, str) else cls
    if v not in CLASSES.values():
        raise ValueError(f"unknown scheduling priority class {cls!r}; known {CLASSES}")
    return int(v)


def _open(k32, access, pid):
    h = k32.OpenProcess(access, False, pid)
    if not h:
        raise OSError(f"OpenProcess(access={access:#x}, pid={pid}) failed")
    return h


def set_priority(pid, cls, gdi32=None, k32=None):
    """-> NTSTATUS (0 is success). The process handle is closed in every case."""
    value = _cls_value(cls)
    gdi32, k32 = _libs(gdi32, k32)
    h = _open(k32, PROCESS_SET_INFORMATION, pid)
    try:
        return int(gdi32.D3DKMTSetProcessSchedulingPriorityClass(h, value))
    finally:
        k32.CloseHandle(h)


def get_priority(pid, gdi32=None, k32=None):
    """-> the class value read back. Raises PriorityError on a nonzero NTSTATUS."""
    gdi32, k32 = _libs(gdi32, k32)
    h = _open(k32, PROCESS_SET_INFORMATION | PROCESS_QUERY_INFORMATION, pid)     # verified on hardware: the Get call needs the SET right; QUERY alone gives STATUS_ACCESS_DENIED (0xC0000022)
    try:
        out = ctypes.c_int(-1)
        status = int(gdi32.D3DKMTGetProcessSchedulingPriorityClass(h, ctypes.byref(out)))
    finally:
        k32.CloseHandle(h)
    if status != 0:
        raise PriorityError(f"D3DKMTGetProcessSchedulingPriorityClass failed: NTSTATUS {status:#x}", set_status=None, readback=None)
    return int(out.value)


def set_and_verify(pid, cls, gdi32=None, k32=None):
    """Set then read back. -> dict(set_status, readback, ok=True). Raises PriorityError if the status is nonzero or the read-back differs from the request."""
    value = _cls_value(cls)
    gdi32, k32 = _libs(gdi32, k32)
    status = set_priority(pid, value, gdi32, k32)
    if status != 0:
        raise PriorityError(f"D3DKMTSetProcessSchedulingPriorityClass failed: NTSTATUS {status:#x}", set_status=status, readback=None)
    rb = get_priority(pid, gdi32, k32)
    if rb != value:
        raise PriorityError(f"priority read-back {rb} != requested {value}", set_status=status, readback=rb)
    return {"set_status": status, "readback": rb, "ok": True}
