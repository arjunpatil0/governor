"""Windows console helpers. QuickEdit pauses a console program when the window is clicked (journal 0023: two A2 stalls, 23 and 10 min)."""
import ctypes
import sys

ENABLE_QUICK_EDIT_MODE, ENABLE_EXTENDED_FLAGS = 0x40, 0x80
STD_INPUT_HANDLE = -10


def quickedit_off_mode(mode):
    return (mode & ~ENABLE_QUICK_EDIT_MODE) | ENABLE_EXTENDED_FLAGS


def disable_quickedit():
    """Turn QuickEdit off for this console. Returns True on success, False (with a loud warning) if it could not be changed."""
    try:
        k32 = ctypes.windll.kernel32
        h = k32.GetStdHandle(STD_INPUT_HANDLE)
        mode = ctypes.c_uint32()
        if not k32.GetConsoleMode(h, ctypes.byref(mode)):
            raise OSError("no console input handle (redirected stdin?)")
        if not k32.SetConsoleMode(h, quickedit_off_mode(mode.value)):
            raise OSError("SetConsoleMode failed")
        return True
    except Exception as e:                                       # noqa: BLE001
        print(f"WARNING: could not disable console QuickEdit ({e}). DO NOT click in this window: a click pauses the run until Enter.",
              file=sys.stderr, flush=True)
        return False
