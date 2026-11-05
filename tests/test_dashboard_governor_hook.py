"""Optional, default-off telemetry hook of the Governor loop and the decision block (telemetry/decision_block.py; used by tools/dashboard).
Instruction (Arjun): "add an OPTIONAL, default-off telemetry hook to the Governor loop ... writes the latest decision (frame-cost estimate, options checked, options safe, chosen clock/mode/duty/guard,
predicted q95/tok/s/power, extra margin, interference factor, power bias) to a small seqlock shared-memory block. Default off, so the evaluation path is byte-for-byte unchanged in behaviour; prove that with a test."
The golden file tests/golden/governor_actions.json was recorded from the Governor and controllers BEFORE the hook existed (git history of this file): the action sequences must stay identical with the hook
absent, with it enabled, and with a failing hook."""
import json
import math
import sys
import uuid
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from controllers.hybrid import HybridController  # noqa: E402
from controllers.pi import SwitchingPIController  # noqa: E402
from controllers.runtime import Governor  # noqa: E402
from controllers.static import IdleDropController  # noqa: E402
from sim.params import load_params  # noqa: E402
from sim.plant import Action  # noqa: E402
from telemetry.obs_builder import ObsBuilder  # noqa: E402

GOLDEN = ROOT / "tests" / "golden" / "governor_actions.json"
PERIOD = 1000.0 / 60.0
TICKS = 320
IDLE_TICKS = range(150, 178)                     # no frames for 2.8 s: the idle branches


class FakeRing:
    def __init__(self, ncols):
        self.ncols = ncols
        self.pending = np.empty((0, ncols))

    def feed(self, rec):
        self.pending = np.asarray(rec, float).reshape(len(rec), self.ncols)

    def read_new(self):
        out, self.pending = self.pending, np.empty((0, self.ncols))
        return out, 0


class RecordingActuator:
    def __init__(self):
        self.actions = []

    def apply(self, a):
        self.actions.append((float(a.clock), a.pacing, round(float(a.duty), 9), round(float(a.guard_ms), 9)))


def make(kind, P):
    if kind == "dB":
        return HybridController(P, 59.08, safety=0.7, switch_gain=2.0, clock_every=20)
    if kind == "cB":
        return SwitchingPIController(P, power_budget_w=59.08, target=0.5, ki=0.15, guard0=0.5, gmin=0.3)
    if kind == "eB":
        return IdleDropController(P, Action(clock=1800.0, pacing="aligned", duty=1.0, guard_ms=0.0))
    raise ValueError(kind)


def drive(kind, telemetry=None, ticks=TICKS, seed=5):
    """The Governor loop against scripted rings: ~6 frames and ~3 tokens per 100 ms tick, a closed clock loop (the commanded clock is read back), an idle stretch, a few late frames."""
    P = load_params(ROOT)
    rng = np.random.default_rng(seed)
    frames, tokens, act = FakeRing(3), FakeRing(2), RecordingActuator()
    gov = Governor(make(kind, P), ObsBuilder(PERIOD, PERIOD), act, frames, tokens, PERIOD, PERIOD, params=P, **({} if telemetry is None else dict(telemetry=telemetry)))
    gov.start(0.0)
    clock, t_s, k_frame = 1800.0, 1000.0, 0
    for i in range(ticks):
        t_s += 0.1
        fr = []
        if i not in IDLE_TICKS:
            for _ in range(6):
                k_frame += 1
                ts = 1000.0 + k_frame / 60.0
                lat = (6.5 + 3.0 * rng.random() + (12.0 if rng.random() < 0.03 else 0.0)) / 1000.0
                fr.append([ts, ts, ts + lat])
        frames.feed(fr)
        tk = [[t_s - 0.02 * j, (10.0 + rng.random()) / 1.0] for j in range(3)]
        tokens.feed(tk)
        pw = 42.0 + 8.0 * rng.random()
        a = gov.step(t_s * 1000.0, 0.0, clock, power_w=pw)
        clock = float(a.clock) if a.clock < P.UNLOCKED_MHZ else float(P.UNLOCKED_MHZ)
    return act.actions, gov


class Sink:
    """A telemetry sink that records what the Governor hands it."""

    def __init__(self):
        self.calls = []

    def publish(self, ctl, action, t_s):
        self.calls.append((type(ctl).__name__, float(action.clock), t_s))


class BrokenSink:
    def publish(self, ctl, action, t_s):
        raise RuntimeError("telemetry sink failure")


def _golden():
    return json.loads(GOLDEN.read_text(encoding="utf-8"))


@pytest.mark.parametrize("kind", ["dB", "cB", "eB"])
def test_actions_without_telemetry_equal_the_golden_recorded_before_the_hook_existed(kind):
    acts, gov = drive(kind)
    assert [list(a) for a in acts] == _golden()[kind]
    assert gov.telemetry is None


@pytest.mark.parametrize("kind", ["dB", "cB", "eB"])
def test_enabling_telemetry_does_not_change_one_action(kind):
    sink = Sink()
    acts, gov = drive(kind, telemetry=sink)
    assert [list(a) for a in acts] == _golden()[kind]
    assert len(sink.calls) == TICKS


def test_a_failing_telemetry_sink_never_breaks_or_changes_the_loop_and_is_switched_off():
    acts, gov = drive("dB", telemetry=BrokenSink())
    assert [list(a) for a in acts] == _golden()["dB"]
    assert gov.telemetry is None and "telemetry sink failure" in gov.telemetry_error


def test_the_default_is_off_and_creates_no_shared_memory():
    assert Governor.default_telemetry is None
    acts, gov = drive("dB")
    assert gov.telemetry is None


def test_default_telemetry_class_attribute_is_picked_up_only_when_set(monkeypatch):
    sink = Sink()
    monkeypatch.setattr(Governor, "default_telemetry", sink)
    acts, gov = drive("dB")
    assert [list(a) for a in acts] == _golden()["dB"] and len(sink.calls) == TICKS


# ---- decision block
def test_decision_block_round_trip_and_field_order():
    from telemetry.decision_block import DECISION_FIELDS, DecisionBlock, read_decision
    name = "Local\\gov_dec_" + uuid.uuid4().hex[:8]
    w = DecisionBlock(name, create=True)
    assert read_decision(DecisionBlock(name, create=False)) is None                      # never written
    vals = {f: float(i) + 0.5 for i, f in enumerate(DECISION_FIELDS)}
    w.write(vals)
    got = read_decision(DecisionBlock(name, create=False))
    assert got == vals and list(got) == list(DECISION_FIELDS)
    assert len(DECISION_FIELDS) == len(set(DECISION_FIELDS))
    for needed in ("c_hat_ms", "options_checked", "options_safe", "clock_mhz", "mode", "duty", "guard_ms", "pred_q95_ms", "pred_tok_s", "pred_power_w", "extra_margin_ms", "interference", "power_bias_w"):
        assert needed in DECISION_FIELDS


def test_decision_block_reader_survives_a_writer_stuck_mid_write():
    import struct
    from telemetry.decision_block import DecisionBlock, read_decision
    name = "Local\\gov_dec_" + uuid.uuid4().hex[:8]
    w = DecisionBlock(name, create=True)
    w.write({f: 1.0 for f in w.fields})
    r = DecisionBlock(name, create=False)
    first = read_decision(r)
    seq = struct.unpack_from("<Q", w.blk.mm, 0)[0]
    struct.pack_into("<Q", w.blk.mm, 0, seq + 1)                                       # odd seq: a writer that never finishes
    assert read_decision(r) is None and read_decision(r, last_good=first) == first       # a failed read keeps the last good record (journal 0041)


def test_decision_block_never_returns_a_torn_record_under_a_fast_writer():
    import threading
    import time
    from telemetry.decision_block import DecisionBlock, read_decision
    name = "Local\\gov_dec_" + uuid.uuid4().hex[:8]
    w = DecisionBlock(name, create=True)
    r = DecisionBlock(name, create=False)
    stop = threading.Event()

    def writer():
        k = 0
        while not stop.is_set():
            k += 1
            w.write({f: float(k) for f in w.fields})                                   # every field of one record carries the same k

    th = threading.Thread(target=writer, daemon=True); th.start()
    ok = bad = 0
    t_end = time.time() + 0.8
    while time.time() < t_end:
        v = read_decision(r)
        if v is None:
            continue
        ok += 1
        bad += len(set(v.values())) != 1
    stop.set(); th.join(2)
    assert ok > 50 and bad == 0, (ok, bad)


def test_publisher_extracts_the_hybrid_decision_with_real_controller_state():
    from telemetry.decision_block import DecisionBlock, DecisionPublisher, read_decision
    name = "Local\\gov_dec_" + uuid.uuid4().hex[:8]
    blk = DecisionBlock(name, create=True)
    pub = DecisionPublisher(blk)
    acts, gov = drive("dB", telemetry=pub, ticks=120)
    d = read_decision(DecisionBlock(name, create=False))
    m = gov.ctl.model if gov.ctl.mode == "aligned" else gov.ctl.model_un
    assert d["tick"] == 120 and d["clock_mhz"] == acts[-1][0] and d["duty"] == acts[-1][2] and d["guard_ms"] == acts[-1][3]
    assert d["mode"] == (1.0 if gov.ctl.mode == "aligned" else 0.0)
    assert d["c_hat_ms"] == pytest.approx(m.c_hat) and d["extra_margin_ms"] == pytest.approx(m.extra) and d["interference"] == pytest.approx(m.gamma) and d["power_bias_w"] == pytest.approx(m.pbias)
    assert d["limit_ms"] == pytest.approx(m.safety * m.deadline) and d["power_cap_w"] == pytest.approx(59.08)
    assert d["options_checked"] >= d["options_safe"] >= 1
    assert d["pred_q95_ms"] <= d["limit_ms"] + 1e-9 and d["pred_power_w"] + d["power_bias_w"] <= 59.08 + 1e-6


def test_publisher_counts_no_safe_option_when_nothing_can_be_safe():
    from telemetry.decision_block import count_options
    acts, gov = drive("dB", ticks=100)
    m = gov.ctl.model
    total, safe = count_options(m, search_all=True)
    assert total > 0 and safe >= 1
    m.safety = 0.01                                                                     # nothing can be safe now
    total, safe = count_options(m, search_all=True)
    assert total > 0 and safe == 0


def test_publisher_handles_controllers_without_a_model_with_nan_predictions():
    from telemetry.decision_block import DecisionBlock, DecisionPublisher, read_decision
    name = "Local\\gov_dec_" + uuid.uuid4().hex[:8]
    pub = DecisionPublisher(DecisionBlock(name, create=True))
    acts, gov = drive("eB", telemetry=pub, ticks=40)
    d = read_decision(DecisionBlock(name, create=False))
    assert d["clock_mhz"] == acts[-1][0] and math.isnan(d["pred_tok_s"]) and math.isnan(d["c_hat_ms"])


def test_the_hook_reads_no_energy_counter_and_the_runtime_source_has_no_dashboard_dependency():
    src = (ROOT / "controllers" / "runtime.py").read_text(encoding="utf-8")
    assert not [ln for ln in src.splitlines() if ln.strip().startswith(("import ", "from ")) and ("tools" in ln or "dashboard" in ln)]       # the loop imports nothing of the dashboard
    blk = (ROOT / "telemetry" / "decision_block.py").read_text(encoding="utf-8")
    assert "EnergyConsumption" not in blk and "nvmlDevice" not in blk and "pynvml" not in blk


if __name__ == "__main__":                                                              # regenerate the golden (only ever done on the code BEFORE the hook)
    GOLDEN.write_text(json.dumps({k: [list(a) for a in drive(k)[0]] for k in ("dB", "cB", "eB")}), encoding="utf-8")
