import json
from pathlib import Path

import pytest

from tools.realgame import cell as c
from tools.realgame.gpu_priority import CLASSES, PriorityError

SAMPLE_HEADER = (Path(__file__).parent / "data" / "pm_sample_synthetic.csv").read_text().splitlines()[0]


def make_cfg(tmp_path, **kw):
    base = dict(repo_root=tmp_path, llm_exe=tmp_path / "llm.exe", model=tmp_path / "m.gguf", prompt=tmp_path / "p.txt", presentmon_exe=tmp_path / "pm.exe",
                game_process="game.exe", armoury_mode="Turbo", llama_dir=tmp_path / "llama.cpp", n_prompt=64, warmup_s=2.0, window_s=6.0, pm_settle_s=0.0,
                ready_timeout_s=5.0,
                llm_exe_vk=tmp_path / "llm_vk.exe", igpu_vk_index=1)
    base.update(kw)
    return c.Config(**base)


class FakeProbes:
    def __init__(self, dirty=(), llama_dirty=(), llama_head="620d2225c4f7e1b", game=True, ac=True, missing=()):
        self.dirty, self.llama_dirty, self.llama_head, self.game, self.ac, self.missing = list(dirty), list(llama_dirty), llama_head, game, ac, {Path(m) for m in missing}
        self.hashes = 0

    def git_head(self, path):
        return self.llama_head if Path(path).name == "llama.cpp" else "abc123"

    def git_dirty(self, path):
        return self.llama_dirty if Path(path).name == "llama.cpp" else self.dirty

    def process_running(self, name):
        return self.game

    def find_pid(self, name):
        return 4242 if self.game else None

    def on_ac(self):
        return self.ac

    def exists(self, path):
        return Path(path) not in self.missing

    def hags(self):
        return 2

    def driver_version(self):
        return "999.99"

    def sha256(self, path):
        self.hashes += 1
        if Path(path).name in ("pm.exe", "d"):
            return c.PRESENTMON_SHA256_PREREG
        return "sha-" + Path(path).name

    def is_elevated(self):
        return False

    def presentmon_version(self, exe):
        return "PresentMon 2.6.0"

    def process_snapshot(self):
        return ["game.exe", "explorer.exe"]


# ---------------------------------------------------------------- preflight
def test_preflight_ok(tmp_path):
    assert c.preflight(make_cfg(tmp_path), FakeProbes()) is None


@pytest.mark.parametrize("probes,needle", [
    (dict(dirty=[" M x.py"]), "dirty"),
    (dict(llama_dirty=[" M ggml.c"]), "llama.cpp tree is dirty"),
    (dict(llama_head="deadbeef0"), "620d2225c"),
    (dict(game=False), "game process"),
    (dict(ac=False), "AC"),
    (dict(ac=None), "AC"),
    (dict(missing=["{tmp}/pm.exe"]), "pm.exe"),
])
def test_preflight_refusals(tmp_path, probes, needle):
    probes = {k: ([s.replace("{tmp}", str(tmp_path)) for s in v] if isinstance(v, list) else v) for k, v in probes.items()}
    with pytest.raises(c.PreflightError, match=needle):
        c.preflight(make_cfg(tmp_path), FakeProbes(**probes))


def test_preflight_refuses_missing_armoury_mode(tmp_path):
    for bad in (None, ""):
        with pytest.raises(c.PreflightError, match="armoury"):
            c.preflight(make_cfg(tmp_path, armoury_mode=bad), FakeProbes())


def test_preflight_game_not_needed_for_llm_alone(tmp_path):
    assert c.preflight(make_cfg(tmp_path), FakeProbes(game=False), need_game=False) is None


def test_preflight_lists_every_failure(tmp_path):
    with pytest.raises(c.PreflightError) as e:
        c.preflight(make_cfg(tmp_path, armoury_mode=None), FakeProbes(dirty=["?? a"], game=False, ac=False))
    assert len(e.value.failures) == 4


# ---------------------------------------------------------------- meta and hashing
def test_build_meta_fields(tmp_path):
    m = c.build_meta(make_cfg(tmp_path, seed=7), FakeProbes())
    for k in ("git_head", "llama_head", "hags_hwschmode", "driver_version", "llm_exe_sha256", "model_sha256", "presentmon_version", "presentmon_sha256", "seed",
              "process_snapshot", "armoury_mode", "game_process"):
        assert k in m
    assert m["seed"] == 7 and m["hags_hwschmode"] == 2 and m["presentmon_version"] == "PresentMon 2.6.0"


def test_sha256_cached_by_path_mtime_size(tmp_path, monkeypatch):
    p = tmp_path / "f.bin"
    p.write_bytes(b"abc")
    calls = []
    real = c._hash_file
    monkeypatch.setattr(c, "_hash_file", lambda path: (calls.append(path), real(path))[1])
    c._SHA_CACHE.clear()
    h1, h2 = c.sha256_file(p), c.sha256_file(p)
    assert h1 == h2 == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad" and len(calls) == 1
    p.write_bytes(b"abcd")
    assert c.sha256_file(p) != h1 and len(calls) == 2


# ---------------------------------------------------------------- rest rule
class FakeTime:
    def __init__(self):
        self.t = 0.0

    def clock(self):
        return self.t

    def sleep(self, s):
        assert s > 0
        self.t += s


def rest(temp_fn, start=60.0, **kw):
    ft = FakeTime()
    r = c.rest_until_cool(lambda: temp_fn(ft.t), start, clock=ft.clock, sleep=ft.sleep, **kw)
    return r, ft


def test_rest_minimum_30s_even_if_already_cool():
    r, ft = rest(lambda t: 60.0)
    assert 30.0 <= r["rest_s"] < 31.5 and r["reached"] is True and ft.t == r["rest_s"]


def test_rest_waits_until_within_3c():
    r, _ = rest(lambda t: 80.0 - t * 0.25 if t < 80 else 60.0)       # 63.0 at t=68
    assert 68.0 <= r["rest_s"] < 70.0 and r["reached"] and r["final_temp"] <= 63.0


def test_rest_capped_at_180s_and_logged():
    r, _ = rest(lambda t: 90.0)
    assert r["rest_s"] == 180.0 and r["reached"] is False and r["final_temp"] == 90.0 and r["start_temp"] == 60.0


def test_rest_boundary_exactly_3c():
    assert rest(lambda t: 63.0)[0]["reached"] is True
    assert rest(lambda t: 63.1)[0]["reached"] is False


# ---------------------------------------------------------------- run_cell with fakes
class Clock:
    def __init__(self):
        self.t = 1000.0

    def now(self):
        return self.t

    def sleep(self, s):
        self.t += s


class FakeLlm:
    pid = 555

    def __init__(self, clock, out_prefix, backend_line="EXEC_MODE cuda device=FAKE offloaded=29/29 n_layer=28 duty=0"):
        self.clock, self.prefix, self.sent, self.killed = clock, out_prefix, [], False
        self.lines = [backend_line, "READY"]
        if "duty=1" in backend_line:
            self.lines.append("DUTY_ACHIEVED 0.4900 decode_s=1.000000 sleep_s=1.040000")

    def wait_for(self, prefix, timeout):
        if prefix == "DONE":
            return "DONE tokens=1 resets=0"
        return next(line for line in self.lines if line.startswith(prefix))

    def send(self, text):
        self.sent.append(text)
        t_stop = float(text.split()[1])
        rows = ["t_tok_end_s,dur_ms,kind"]
        t = self.clock.now()
        while t < t_stop:
            t += 0.01
            rows.append(f"{t:.6f},10.0,token")
        Path(str(self.prefix) + "_tokens.csv").write_text("\n".join(rows) + "\n")

    def poll(self):
        return None

    def kill(self):
        self.killed = True


class FakeCapture:
    instances = []

    def __init__(self, clock, out_csv, fail_start=False):
        self.clock, self.out_csv, self.started, self.stopped, self.fail_start = clock, out_csv, False, 0, fail_start
        FakeCapture.instances.append(self)

    def start(self):
        if self.fail_start:
            raise RuntimeError("presentmon start failed")
        self.started = True; self.t0 = self.clock.now()

    def stop(self, timeout=10.0):
        self.stopped += 1
        if not self.started:
            return
        rows = [SAMPLE_HEADER]
        for i in range(1000):                      # 60 fps over 16.7 s from the start of capture; busy 8.0, 16.667 ms frame, alternate swapchains are not used
            t = self.t0 + i / 60.0
            rows.append(f"G.exe,1,0xA,D3D11,1,0,0,Flip,Application,{int(t * 1e7)},40.0,3,13,1.0,8.2,8.0,1,0,20,16.7,0,0,0,NA,NA,NA")
        Path(self.out_csv).write_text("\n".join(rows) + "\n")


class FakeNvml:
    def __init__(self, clock):
        self.clock = clock

    def energy_mj(self):
        return self.clock.now() * 90_000.0

    def temp_c(self):
        return 61.0

    def vram_used_mb(self):
        return 2048.0


class FakeSampler:
    def __init__(self, clock):
        self.clock = clock
        self.t = [1000.0 + i * 0.05 for i in range(2000)]
        self.sm = [1500] * 2000
        self.throttle = [0] * 10 + [4] * 1990
        self.temp = [60] * 2000

    def start(self):
        pass

    def stop(self):
        pass


def exec_line(env):
    dev = "AMD Radeon(TM) 780M Graphics" if env["RG_BACKEND"] == "vulkan" else "FAKE"
    return f"EXEC_MODE {env['RG_BACKEND']} device={dev} offloaded=29/29 n_layer=28 duty={env['RG_DUTY']}"


def make_deps(cfg, clock, llm=None, capture_fail=False, prio=None, get_prio=None, order=None):
    order = order if order is not None else []
    llm_box = {}

    def spawn(cmd, env, out_prefix):
        order.append(("spawn", env.get("RG_BACKEND"), env.get("RG_DUTY")))
        llm_box["l"] = llm or FakeLlm(clock, out_prefix, exec_line(env))
        return llm_box["l"]

    def mk_cap(cfg_, out_csv, session):
        order.append(("capture", session))
        return FakeCapture(clock, out_csv, fail_start=capture_fail)

    d = c.Deps(probes=FakeProbes(), clock=clock.now, sleep=clock.sleep, spawn_llm=spawn, make_capture=mk_cap, nvml=FakeNvml(clock),
               make_sampler=lambda nv: FakeSampler(clock), set_and_verify=prio or (lambda pid, cls: {"set_status": 0, "readback": cls, "ok": True}),
               get_priority=get_prio or (lambda pid: CLASSES["IDLE"]), shared_mem=lambda pid: 123 * 2**20, qpc_hz=1e7, qpc_counter=lambda: int(clock.now() * 1e7))
    return d, llm_box


def test_run_cell_ungated_writes_everything(tmp_path):
    clock, order = Clock(), []
    cfg = make_cfg(tmp_path)
    d, box = make_deps(cfg, clock, order=order)
    out = tmp_path / "cell"
    res = c.run_cell("UNGATED", 1, out, cfg, d)
    for f in ("result.json", "meta.json", "frames.csv", "driver.log"):
        assert (out / f).exists(), f
    assert json.loads((out / "result.json").read_text()) == json.loads(json.dumps(res))
    assert order[0] == ("spawn", "cuda", "0") and order[1][0] == "capture"          # LLM ready before capture starts
    assert len(box["l"].sent) == 1 and box["l"].sent[0].startswith("GO ") and float(box["l"].sent[0].split()[1]) == pytest.approx(res["t_close"])
    assert res["t_close"] - res["t_open"] == pytest.approx(6.0) and res["tok_s"] == pytest.approx(100.0, rel=0.02)
    assert res["power_w"] == pytest.approx(90.0) and res["energy_j"] == pytest.approx(540.0)
    assert res["frame"]["n"] == pytest.approx(360, abs=2) and res["frame"]["p99"] == pytest.approx(40.0) and res["frame"]["hitch_share"] == 100.0
    assert res["gpu_busy_ms_median"] == 8.0 and res["temp_c"]["start"] == 61.0 and res["vram_mb"]["end"] == 2048.0
    assert res["shared_gpu_mem_bytes"]["start"] == 123 * 2**20
    assert res["throttle_mask_or"] == 4 and res["exec_mode"].startswith("EXEC_MODE cuda") and res["qpc_hz"] == 1e7
    assert box["l"].killed and FakeCapture.instances[-1].stopped >= 1


def test_run_cell_solo_has_no_llm_and_llm_alone_no_capture(tmp_path):
    clock, order = Clock(), []
    cfg = make_cfg(tmp_path)
    d, _ = make_deps(cfg, clock, order=order)
    res = c.run_cell("SOLO", 0, tmp_path / "solo", cfg, d)
    assert [o[0] for o in order] == ["capture"] and res["tok_s"] is None and res["frame"]["n"] > 0
    assert res["throttle_mask_or"] == 4 and res["sm_clock_mhz_median"] == 1500          # sampler runs in SOLO too
    order.clear()
    d.probes = FakeProbes(game=False)
    res = c.run_cell("LLM_ALONE", 0, tmp_path / "alone", cfg, d)
    assert [o[0] for o in order] == ["spawn"] and res["frame"] is None and res["tok_s"] > 0 and not (tmp_path / "alone" / "frames.csv").exists()


def test_run_cell_arm_environment(tmp_path):
    clock, order = Clock(), []
    cfg = make_cfg(tmp_path)
    d, _ = make_deps(cfg, clock, order=order, llm=None)
    c.run_cell("DUTY50", 0, tmp_path / "d", cfg, d)
    assert order[0] == ("spawn", "cuda", "1")
    order.clear()
    d, _ = make_deps(cfg, clock, order=order, llm=None)
    d.spawn_llm = lambda cmd, env, p: (order.append(("spawn", env["RG_BACKEND"], env["RG_DUTY"])), FakeLlm(clock, p, exec_line(env)))[1]
    c.run_cell("IGPU", 0, tmp_path / "i", cfg, d)
    assert order[0] == ("spawn", "vulkan", "0")


def test_run_cell_wrong_backend_in_exec_mode_fails_loudly(tmp_path):
    clock = Clock()
    cfg = make_cfg(tmp_path)
    d, _ = make_deps(cfg, clock)
    d.spawn_llm = lambda cmd, env, p: FakeLlm(clock, p, "EXEC_MODE vulkan device=X offloaded=1/1 n_layer=1 duty=0")
    with pytest.raises(RuntimeError, match="EXEC_MODE"):
        c.run_cell("UNGATED", 0, tmp_path / "x", cfg, d)


def test_run_cell_prio_idle_set_and_read_back_twice(tmp_path):
    clock, calls = Clock(), []
    cfg = make_cfg(tmp_path)
    d, _ = make_deps(cfg, clock, prio=lambda pid, cls: (calls.append((pid, cls)), {"set_status": 0, "readback": cls, "ok": True})[1],
                     get_prio=lambda pid: (calls.append(("get", pid)), 0)[1])
    res = c.run_cell("PRIO_IDLE", 0, tmp_path / "p", cfg, d)
    assert calls == [(555, 0), ("get", 555)]
    assert res["prio_readbacks"] == [0, 0] and res["prio_valid"] is True


def test_run_cell_prio_readback_mismatch_voids_but_cell_completes(tmp_path):
    clock = Clock()
    cfg = make_cfg(tmp_path)

    def bad(pid, cls):
        raise PriorityError("readback mismatch", set_status=0, readback=2)
    d, _ = make_deps(cfg, clock, prio=bad, get_prio=lambda pid: 2)
    res = c.run_cell("PRIO_IDLE", 0, tmp_path / "p", cfg, d)
    assert res["prio_valid"] is False and res["prio_readbacks"] == [2, 2]


def test_run_cell_prio_failed_status_fails_the_cell(tmp_path):
    clock = Clock()
    cfg = make_cfg(tmp_path)

    def bad(pid, cls):
        raise PriorityError("status", set_status=-1073741790, readback=None)
    d, box = make_deps(cfg, clock, prio=bad)
    with pytest.raises(PriorityError):
        c.run_cell("PRIO_IDLE", 0, tmp_path / "p", cfg, d)
    assert box["l"].killed and not (tmp_path / "p" / "result.json").exists()


def test_run_cell_cleanup_when_capture_fails(tmp_path):
    clock = Clock()
    cfg = make_cfg(tmp_path)
    d, box = make_deps(cfg, clock, capture_fail=True)
    with pytest.raises(RuntimeError, match="presentmon start failed"):
        c.run_cell("UNGATED", 0, tmp_path / "x", cfg, d)
    assert box["l"].killed and FakeCapture.instances[-1].stopped >= 1 and not (tmp_path / "x" / "result.json").exists()


def test_run_cell_unknown_arm(tmp_path):
    with pytest.raises(ValueError):
        c.run_cell("BOGUS", 0, tmp_path / "x", make_cfg(tmp_path), None)


def test_arms_constant():
    assert c.ARMS == ("SOLO", "UNGATED", "PRIO_IDLE", "DUTY50", "IGPU", "LLM_ALONE")
