"""The Governor's latest decision, published for the live dashboard (tools/dashboard) through a small seqlock shared-memory block (telemetry/ring.py SeqBlock, nfields = len(DECISION_FIELDS)).
OPTIONAL and default off: controllers/runtime.py Governor calls a sink's publish(ctl, action, t_s) after every step only when a sink is set (Governor(telemetry=...) or Governor.default_telemetry);
the sink only READS controller state, so the actions are identical with and without it (tests/test_dashboard_governor_hook.py, golden recorded before the hook existed). No NVML here (never the energy counter).
Fields (doubles, QPC seconds for t_s): tick, t_s, idle (0/1), c_hat_ms (frame-cost estimate at 1800 MHz), options_checked, options_safe (candidate points of the decision step and how many passed the q95 and the
power-budget test; re-evaluated from the controller state after the decision), clock_mhz / mode (1 aligned, 0 unaligned, -1 n/a) / duty / guard_ms (the commanded action), pred_q95_ms / pred_tok_s / pred_power_w
(the chosen plan's prediction; nan where the controller has none), extra_margin_ms, interference (gamma), power_bias_w, limit_ms (safety x deadline), power_cap_w (steering budget; nan if none)."""
import math

from controllers.common import ALLOWED_CLOCKS
from telemetry.ring import SeqBlock

DECISION_FIELDS = ("tick", "t_s", "idle", "c_hat_ms", "options_checked", "options_safe", "clock_mhz", "mode", "duty", "guard_ms", "pred_q95_ms", "pred_tok_s", "pred_power_w",
                   "extra_margin_ms", "interference", "power_bias_w", "limit_ms", "power_cap_w")
NAN = float("nan")


class DecisionBlock:
    """Writer (create=True, the Governor side) or reader (create=False, the dashboard side) of the decision record."""

    def __init__(self, name, create):
        self.name, self.fields = name, DECISION_FIELDS
        self.blk = SeqBlock(name, len(DECISION_FIELDS), create)

    def write(self, vals):
        self.blk.write([float(vals[f]) for f in self.fields])


def read_decision(block, last_good=None):
    """The latest consistent decision as a dict, or last_good (default None) if the block was never written or the writer kept it busy for every retry (a failed read is not information; journal 0041)."""
    v = block.blk.read()
    if v is None:
        return last_good
    return dict(zip(block.fields, v))


def count_options(m, search_all):
    """(candidate points, safe ones) of ModelController m's decision step, re-evaluated from its state: safe = predicted q95 <= safety x deadline and, with a budget, predicted power + bias <= budget."""
    if m.c_hat is None:
        return 0, 0
    clocks = ALLOWED_CLOCKS(m.P) if search_all else (m.clock,)
    total = safe = 0
    for _, c in m._candidates(clocks):
        total += 1
        if c["pred_q95_ms"] > m.safety * m.deadline:
            continue
        if m.power_budget_w is not None and c["pred_power"] + m.pbias > m.power_budget_w:
            continue
        safe += 1
    return total, safe


def _model_of(ctl):
    """The ModelController whose plan was executed: the hybrid's current mode instance, a bare ModelController, else None (static, eB, c'B have no model)."""
    if hasattr(ctl, "model_un") and hasattr(ctl, "model") and hasattr(ctl, "mode"):
        return ctl.model if ctl.mode == "aligned" else ctl.model_un
    if hasattr(ctl, "plan") and hasattr(ctl, "c_hat") and hasattr(ctl, "_candidates"):
        return ctl
    return None


def extract_decision(ctl, action, t_s, tick):
    """The decision record for one Governor step (reads controller state only)."""
    d = dict(tick=tick, t_s=t_s, idle=0.0, c_hat_ms=NAN, options_checked=NAN, options_safe=NAN, clock_mhz=float(action.clock), mode=1.0 if action.pacing == "aligned" else 0.0, duty=float(action.duty),
             guard_ms=float(action.guard_ms), pred_q95_ms=NAN, pred_tok_s=NAN, pred_power_w=NAN, extra_margin_ms=NAN, interference=NAN, power_bias_w=NAN, limit_ms=NAN, power_cap_w=NAN)
    idl = getattr(ctl, "idle", None)
    in_idle = bool(idl is not None and getattr(idl, "k", 0) >= getattr(idl, "n", math.inf))
    d["idle"] = 1.0 if in_idle else 0.0
    m = _model_of(ctl)
    if m is None:
        return d
    d["c_hat_ms"] = NAN if m.c_hat is None else float(m.c_hat)
    d["extra_margin_ms"], d["interference"], d["power_bias_w"] = float(m.extra), float(m.gamma), float(m.pbias)
    d["limit_ms"] = float(m.safety * m.deadline)
    d["power_cap_w"] = NAN if m.power_budget_w is None else float(m.power_budget_w)
    if in_idle or not m.plan or m.plan.get("idle"):
        return d
    p = m.plan
    d["pred_q95_ms"], d["pred_tok_s"], d["pred_power_w"] = float(p["pred_q95_ms"]), float(p["pred_tok"]), float(p["pred_power"])
    total, safe = count_options(m, search_all=(m.tick % m.clock_every == 0))
    d["options_checked"], d["options_safe"] = float(total), float(safe)
    return d


class DecisionPublisher:
    """Governor telemetry sink: publish(ctl, action, t_s) writes the decision record to a DecisionBlock (and keeps the last record in .last for a caller that logs it)."""

    def __init__(self, block):
        self.block, self.tick, self.last = block, 0, None

    def publish(self, ctl, action, t_s):
        self.tick += 1
        self.last = extract_decision(ctl, action, float(t_s), self.tick)
        self.block.write(self.last)
