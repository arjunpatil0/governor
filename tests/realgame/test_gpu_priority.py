import pytest

from tools.realgame import gpu_priority as gp


class FakeK32:
    def __init__(self, handle=77):
        self.handle, self.opened, self.closed = handle, [], []

    def OpenProcess(self, access, inherit, pid):
        self.opened.append((access, inherit, pid)); return self.handle

    def CloseHandle(self, h):
        self.closed.append(h); return 1


class FakeGdi:
    def __init__(self, set_status=0, get_status=0, readback=None, raises=False):
        self.set_status, self.get_status, self.readback, self.raises = set_status, get_status, readback, raises
        self.set_calls, self.state = [], 0

    def D3DKMTSetProcessSchedulingPriorityClass(self, h, cls):
        if self.raises:
            raise OSError("boom")
        self.set_calls.append((h, cls)); self.state = cls
        return self.set_status

    def D3DKMTGetProcessSchedulingPriorityClass(self, h, out):
        out._obj.value = self.state if self.readback is None else self.readback
        return self.get_status


def test_classes_values_and_unverified_marker():
    assert gp.CLASSES == {"IDLE": 0, "BELOW_NORMAL": 1, "NORMAL": 2, "ABOVE_NORMAL": 3, "HIGH": 4, "REALTIME": 5}
    assert gp.CLASSES_VERIFIED is False


def test_set_priority_uses_enum_and_closes():
    g, k = FakeGdi(), FakeK32()
    assert gp.set_priority(10, gp.CLASSES["IDLE"], gdi32=g, k32=k) == 0
    assert g.set_calls == [(77, 0)] and k.opened == [(gp.PROCESS_SET_INFORMATION, False, 10)] and k.closed == [77]


def test_set_priority_by_name_and_bad_class():
    g, k = FakeGdi(), FakeK32()
    gp.set_priority(10, "BELOW_NORMAL", gdi32=g, k32=k)
    assert g.set_calls[0][1] == 1
    with pytest.raises(ValueError):
        gp.set_priority(10, 9, gdi32=g, k32=k)


def test_handle_closed_on_failure_and_open_failure():
    g, k = FakeGdi(raises=True), FakeK32()
    with pytest.raises(OSError):
        gp.set_priority(10, 0, gdi32=g, k32=k)
    assert k.closed == [77]
    k0 = FakeK32(handle=0)
    with pytest.raises(OSError):
        gp.set_priority(10, 0, gdi32=FakeGdi(), k32=k0)
    assert k0.closed == []


def test_get_priority_and_error_status():
    g, k = FakeGdi(), FakeK32()
    gp.set_priority(10, 3, gdi32=g, k32=k)
    assert gp.get_priority(10, gdi32=g, k32=k) == 3 and k.closed[-1] == 77
    with pytest.raises(gp.PriorityError):
        gp.get_priority(10, gdi32=FakeGdi(get_status=-1), k32=k)


def test_set_and_verify_ok():
    r = gp.set_and_verify(10, 0, gdi32=FakeGdi(), k32=FakeK32())
    assert r == {"set_status": 0, "readback": 0, "ok": True}


def test_set_and_verify_nonzero_status_raises():
    with pytest.raises(gp.PriorityError) as e:
        gp.set_and_verify(10, 0, gdi32=FakeGdi(set_status=-1073741790), k32=FakeK32())
    assert e.value.set_status == -1073741790


def test_set_and_verify_readback_mismatch_raises():
    with pytest.raises(gp.PriorityError) as e:
        gp.set_and_verify(10, 0, gdi32=FakeGdi(readback=2), k32=FakeK32())
    assert e.value.set_status == 0 and e.value.readback == 2


def test_import_does_not_load_windows_libs():
    assert not hasattr(gp, "windll") and not hasattr(gp, "_LIBS_LOADED")


def test_get_priority_opens_the_process_with_set_information_access():
    """Verified on hardware (2026-11-11): D3DKMTGetProcessSchedulingPriorityClass answers STATUS_ACCESS_DENIED (0xC0000022) for a handle opened with PROCESS_QUERY_INFORMATION (0x400) or
    PROCESS_QUERY_LIMITED_INFORMATION (0x1000) alone, and succeeds when the handle includes PROCESS_SET_INFORMATION (0x200). The read-back must open with that right."""
    k = FakeK32()
    assert gp.get_priority(123, FakeGdi(), k) == 0
    (access, _inherit, pid), = k.opened
    assert pid == 123 and access & gp.PROCESS_SET_INFORMATION == gp.PROCESS_SET_INFORMATION


def test_set_and_verify_uses_set_information_access_for_both_calls():
    k = FakeK32()
    gp.set_and_verify(55, "IDLE", FakeGdi(), k)
    assert len(k.opened) == 2 and all(a & gp.PROCESS_SET_INFORMATION for a, _i, _p in k.opened)
    assert k.closed == [77, 77]
