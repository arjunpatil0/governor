"""Builds docs/report/SOURCES.md: for every number (or group of numbers) in docs/report/REPORT.md, the file and line that carry it. A claim row is (section, claim, tokens, file, regex): the first line of the file that
matches the regex AND contains every token is the source; if there is none the build fails, so a number that no file carries cannot stay in the table. Numbers that are arithmetic on sourced numbers are listed under
'Derived'. Table 1 of the report is checked cell by cell against data/w5b/eval_descriptive.md. Files outside the repository are not used.
   python docs/report/build_sources.py"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent

C = [  # (section, claim in the report, tokens that must be on the source line, file, regex locating the line)
    ("1", "36 SMs, RTX 4070 Laptop, Windows 11", ["36 SMs", "Windows 11"], "docs/W2_SUMMARY.md", r"Hardware: RTX 4070 Laptop"),
    ("1", "8 GB (8188 MiB)", ["8188 MiB"], "CLAUDE.md", r"8188 MiB"),
    ("1", "no MPS, no MIG on Windows", ["no MPS, no MIG"], "CLAUDE.md", r"no MPS, no MIG"),
    ("1", "WDDM driver model", ["WDDM"], "docs/report/evidence/nvidia_smi_2026-11-06.txt", r"WDDM"),
    ("1", "MIG mode not available (N/A)", ["N/A"], "docs/report/evidence/nvidia_smi_2026-11-06.txt", r"Current\s+: N/A"),
    ("1", "60 Hz frame loop (period 1000/60 ms = 16.67 ms deadline)", ["1000.0 / 60.0"], "sim/scenarios.py", r"PERIOD_MS ="),
    ("1", "nominal frame cost 7 ms at 1800 MHz", ["7.0", "1800"], "sim/scenarios.py", r"C0_MS = 7.0"),
    ("1", "Llama-3.2-3B model", ["Llama-3.2-3B"], "data/w2_L_results.md", r"Engine: llama.cpp pinned"),
    ("1", "Phi-3.5-mini among the models", ["phi35_mini"], "data/llama/models.json", r"phi35_mini"),
    ("1", "a 1B model among the models", ["llama32_1b"], "data/llama/models.json", r"llama32_1b"),
    ("1", "held-out Llama-3.1-8B", ["Llama-3.1-8B"], "docs/W5B_EVALUATION.md", r"held-out Llama-3.1-8B"),
    ("1", "60 W primary, 35 W exploratory budgets", ["60 W", "35 W"], "docs/W5B_EVALUATION.md", r"60 W \(primary\)|60 W primary|35 W cells|35 W family|exploratory 35 W cells"),
    ("1", "at most 1% late frames", ["0.01"], "analysis/w5_analysis.py", r"^SLO = 0.01"),
    ("1", "uncontrolled S1: 34.10% late, 89.9 W (10 cells)", ["10", "34.10", "89.9"], "data/w5b/eval_descriptive.md", r"^\s*S1\s+a\s+10"),
    ("1", "uncontrolled S5: 34.65% late, 90.5 W", ["34.65", "90.5"], "data/w5b/eval_descriptive.md", r"^\s*S5\s+a\s+10"),
    ("1", "uncontrolled S0: 0.00% late, 90.5 W", ["0.00", "90.5"], "data/w5b/eval_descriptive.md", r"^\s*S0\s+a\s+10"),
    ("1", "uncontrolled S2: 0.00% late, 91.6 W", ["0.00", "91.6"], "data/w5b/eval_descriptive.md", r"^\s*S2\s+a\s+10"),
    ("2", "clock law: 1.999 / 1.500 / 1.203 at 900 / 1200 / 1500 MHz, predicted 2.000 / 1.500 / 1.202", ["1.999", "1.500", "1.203", "2.000", "1.202"], "docs/W2_SUMMARY.md", r"B: clock lock vs compute-bound fg"),
    ("2", "1500 MHz 97.25 tok/s at 56.3 W vs 101.1 tok/s at 92.0 W unlocked", ["97.25", "56.3", "101.1", "92.0"], "docs/W2_SUMMARY.md", r"L: llama.cpp validation"),
    ("2", "energy per token 0.526 J at 1050 MHz vs 0.915 J unlocked", ["0.526", "0.915", "1050"], "docs/W2_SUMMARY.md", r"L: llama.cpp validation"),
    ("2", "relative throughput at 1500 MHz 0.959 (96%)", ["0.959462"], "data/w2_L_results.md", r"^\s*1500\s"),
    ("2", "fp16 proxy knee 1050 MHz, real engine knee 1500 MHz", ["1050", "1500"], "data/w2_L_results.md", r"knee 1500 MHz"),
    ("2", "WDDM slice 0.374 ms, switch gap 0.148 ms", ["0.374", "0.148"], "docs/W2_SUMMARY.md", r"G: %globaltimer timeline"),
    ("2", "token overlapped by a frame 2.05x, frame 1.95x", ["2.05x", "1.95x"], "journal/0042_2026-10-23_w45-correction-granularity-clean-token-estimate.md", r"token 2\.05x"),
    ("2", "queueing hypothesis HA1 not supported", ["HA1", "NOT supported"], "docs/W2_SUMMARY.md", r"A: residual-wait model"),
    ("2", "wait levels off near 0.26 ms, independent of arrival phase (exploratory fit)", ["0.260", "independent of arrival phase"], "docs/W2_SUMMARY.md", r"A2: secondary"),
    ("3", "40-byte shared-memory record", ["40 bytes"], "docs/SPEC_FRAME_SLACK_HINTS.md", r"One named file mapping of 40 bytes"),
    ("3", "busy published about 1 ms before the frame", ["1.0"], "workloads/foreground/frame_loop.py", r"lead_ms=1.0"),
    ("3", "record older than 100 ms means the app is idle", ["100 ms"], "docs/SPEC_FRAME_SLACK_HINTS.md", r"C5 staleness"),
    ("3", "slackhint library and binding: 22 tests", ["(22)"], "journal/0067_2026-11-06_reference-design-slackhint.md", r"Tests, all passing \(22\)"),
    ("3", "control block of three values (pacing mode, duty, guard)", ["3 doubles"], "workloads/background/llama_governed_bench.cpp", r"ctrl_block \(governor -> driver"),
    ("3", "median of the last 8 tokens not overlapped by a frame", ["median of the last 8"], "workloads/background/tok_estimate.h", r"median of the last 8"),
    ("3", "governor ticks ten times a second (0.1 s)", ["0.1"], "experiments/w5b/executors.py", r"tick \+= 0\.1"),
    ("3", "predicted 95th-percentile frame time (q95) is the controller's safety quantity", ["q95"], "controllers/model.py", r"q95 = alone"),
    ("3", "safety margin 0.3 (limit 0.7 of the deadline)", ["0.3"], "data/w5b/constants.json", r'"margin"'),
    ("3", "limit = (1 - margin) x deadline in the controller", ["safety=1.0 - float"], "experiments/w5b/executors.py", r"safety=1\.0 - float"),
    ("3", "headroom 2.692 W", ["2.692"], "docs/W5B_ADDENDUM_O7.md", r"2\.692"),
    ("3", "steering parameter 59.080 W at 60 W (budget minus headroom, divided by 0.97)", ["59.080"], "docs/W5B_EVALUATION.md", r"59\.080 W at 60 W"),
    ("3", "controllers aim at 97% of their power-budget parameter: parameter = steering target / 0.97", ["/ 0.97"], "experiments/w5b/tune_lib.py", r"steering target / 0.97"),
    ("3", "extra margin +1 ms up to 6 ms, decay 0.1 ms per tick", ["1.0, 6.0", "0.1"], "controllers/model.py", r"self\.extra = min\(self\.extra \+ 1\.0, 6\.0\)"),
    ("3", "decay of the extra margin 0.1", ["0.1"], "controllers/model.py", r"self\.extra = max\(self\.extra - 0\.1"),
    ("3", "mode switch needs 1.2x + 2 tok/s", ["1.2", "2.0"], "controllers/hybrid.py", r"^MORE_FACTOR, MORE_ABS"),
    ("3", "two consecutive one-second checks (10 ticks, hold 2)", ["10, 2"], "controllers/hybrid.py", r"^SWITCH_EVERY, SWITCH_HOLD"),
    ("3", "five idle ticks", ["5"], "controllers/common.py", r"^IDLE_TICKS = 5"),
    ("3", "idle clock 1500 MHz (the knee)", ["1500 MHz"], "controllers/common.py", r"journal 0027: 1500 MHz"),
    ("3", "clock service commands LOCK, RESET, HB, PING", ["LOCK <mhz>", "RESET", "HB", "PING"], "actuators/clock_helper.py", r"Verbs: LOCK"),
    ("3", "lock changes rate limited to one per second; watchdog 3 s", ["watchdog_s=3.0", "min_interval_s=1.0"], "actuators/clock_helper.py", r"def __init__\(self, backend, allowed_mhz"),
    ("3", "high-severity finding: a failed reset was forgotten", ["HIGH-1", "failed reset was forgotten"], "docs/W45_CLOCK_HELPER_SECURITY.md", r"HIGH-1"),
    ("3", "review by a model-based agent, not a human audit", ["not a human audit"], "docs/W45_CLOCK_HELPER_SECURITY.md", r"model output, not a human audit"),
    ("3", "713 passing tests, 1 skipped, build test excluded", ["713 passed", "1 skipped"], "journal/0068_2026-11-06_live-dashboard.md", r"713 passed"),
    ("3", "preflight: stated Armoury mode, AC power, uptime, clean tree, Chrome", ["armoury_mode", "uptime", "chrome"], "experiments/w5b/tune.py", r"def refusal"),
    ("3", "uptime limit two hours (7200 s)", ["7200.0"], "experiments/w5b/evaluate.py", r"--max-uptime-s"),
    ("4", "yaml committed 2026-10-23", ["2026-10-23"], "analysis/w5_analysis.py", r"committed 2026-10-23"),
    ("4", "constants frozen in a hashed file (sha256)", ["f7b99650efe7fea9d392a1aee2e49a18a84a00fe69d56fb4e41bf562cc6fb4a9"], "docs/W5B_EVALUATION.md", r"sha256 f7b99650"),
    ("4", "ten blocks, 30 cells per block at 60 W, 25 more at 35 W in five blocks", ["10 evaluation blocks", "30 primary cells", "25 exploratory 35 W cells"], "docs/W5B_EVALUATION.md", r"10 evaluation blocks"),
    ("4", "cells run in a seeded random order", ["seeded-random"], "docs/W5B_EVALUATION.md", r"seeded-random"),
    ("4", "425 cells in the ten complete blocks", ["425"], "journal/0066_2026-11-06_w5b-registered-analysis.md", r"425 cells"),
    ("4", "5 s warm-up and 60 s measured window", ["5.0, 60.0"], "experiments/w5b/executors.py", r"^WARM_S, MEASURE_S"),
    ("4", "about 100 s per cell", ["100 s"], "docs/W5B_EVALUATION.md", r"Estimate 100 s per cell"),
    ("4", "S1 steps 1.0, 0.7, 1.3, 0.7, 1.0, 1.3 every 10 s", ["1.0, 0.7, 1.3, 0.7, 1.0, 1.3"], "sim/scenarios.py", r"^_STEPS"),
    ("4", "S1 step length 10 s", ["10000.0"], "sim/scenarios.py", r"t // 10000\.0"),
    ("4", "S1d linear drift 0.7 to 1.3 over 60 s", ["0.7 + 0.6", "60000.0"], "sim/scenarios.py", r"0\.7 \+ 0\.6"),
    ("4", "S2 active 0-20 s and 30-50 s", ["20000.0", "30000.0", "50000.0"], "sim/scenarios.py", r"name == \"S2\""),
    ("4", "S5 uses the S1 frame loop with an unseen background (held-out 8B in the evaluation)", ["S1 foreground with an UNSEEN background"], "sim/scenarios.py", r"EXTRA_SCENARIOS"),
    ("4", "feasible: at most 1% late and power within budget; score zero otherwise", ["miss_frac <= SLO", "power_w <= df.budget_w"], "analysis/w5_analysis.py", r"feasible = \(df\.miss_frac"),
    ("4", "feasibility holds with at least 90% of cells feasible and mean miss at most 1%", ["0.9", "SLO"], "analysis/w5_analysis.py", r"g\[\"holds\"\]"),
    ("4", "non-inferiority margin 0.95", ["0.95"], "analysis/w5_analysis.py", r"^NI_MARGIN"),
    ("4", "exact one-sided Wilcoxon, Holm over 3, 90% bootstrap CI", ["Holm over 3", "90%"], "analysis/w5_analysis.py", r"Holm over 3"),
    ("4", "session of two blocks about 2.4 h", ["2.4 h"], "docs/W5B_EVALUATION.md", r"about 2\.4 h"),
    ("4", "block 7 held 31 measured cells of 55, stopped by Ctrl+C", ["31 measured cells", "KeyboardInterrupt"], "journal/0065_2026-10-28_session4-stopped-block7-rerun-as-15.md", r"Block 7 had 32 cell folders|31 with cell\.json"),
    ("4", "block 6 had zero measured cells after three failed starts", ["Zero measured cells", "confirmed"], "journal/0064_2026-10-27_session3-failed-start-and-block6-rerun.md", r"Zero measured cells: confirmed"),
    ("4", "three start attempts of session 3", ["three start attempts"], "journal/0064_2026-10-27_session3-failed-start-and-block6-rerun.md", r"^# 0064"),
    ("4", "reruns as blocks 14 and 15", ["14", "15"], "journal/0065_2026-10-28_session4-stopped-block7-rerun-as-15.md", r"Next free rerun number: 15"),
    ("4", "integrity report: 425 cells, 0 problems", ["425 cells", "0 problems"], "journal/0066_2026-11-06_w5b-registered-analysis.md", r"PASS, 425 cells, 0 problems"),
    ("5", "S2 non-inferiority ratio vs best fixed 1.289 [1.282, 1.310]", ["1.289", "1.282", "1.310"], "data/w5_results.md", r"S2 vs g'B: median ratio"),
    ("5", "S2 non-inferiority ratio vs idle-rule setting 1.310 [1.304, 1.336]", ["1.310", "1.304", "1.336"], "data/w5_results.md", r"S2 vs eB: median ratio"),
    ("5", "clean 3B token 10.1 ms; threshold 6.57 ms", ["10.1 ms", "6.57 ms"], "journal/0042_2026-10-23_w45-correction-granularity-clean-token-estimate.md", r"Granularity finding"),
    ("5", "no token in the measured window in all 40 cells of S0 and S5", ["all 40 cells"], "docs/W5B_RESULTS.md", r"all 40 cells at 60 W"),
    ("5", "smoke 3: 60.0 tok/s at nominal cost 4 ms", ["60.0"], "data/w45_smoke/smoke3_report.md", r"aligned_g0_d1_cost4"),
    ("5", "smoke 3: 59.9 tok/s at nominal cost 7 ms", ["59.9"], "data/w45_smoke/smoke3_report.md", r"aligned_g0_d1_cost7"),
    ("5", "governor ended unaligned in all 75 cells", ["all 75"], "docs/W5B_RESULTS.md", r"all 75 of its cells"),
    ("5", "late share above 1% in every block: S1 1.72%, S5 4.72% (0/10 feasible)", ["1.72", "4.72"], "docs/W5B_RESULTS.md", r"0/10 feasible"),
    ("5", "six-cell tuning mean 0.875%, 3B S1 2.0%, Phi S1 3.25%", ["0.875%", "3.25%"], "docs/W5B_RESULTS.md", r"T3b six-cell means"),
    ("5", "3B S1 tuning miss 2.0% at margin 0.3", ["2.0%", "19.8"], "docs/W5B_RESULTS.md", r"db_llama32_3b_S1_m0\.3"),
    ("5", "S5 superiority inconclusive, all arms tie at 0", ["INCONCLUSIVE", "non-tied blocks 0"], "data/w5_results.md", r"vs c'B-T3b: median diff 0.00"),
    ("5", "S0 non-inferiority vs the primary reactive controller 0.973 [0.943, 0.980], fail", ["0.973", "0.943", "0.980", "pass False"], "data/w5_results.md", r"S0 vs c'B-T3b: median ratio"),
    ("5", "other non-inferiority tests: S0 vs best fixed and vs idle rule vacuous", ["VACUOUS"], "data/w5_results.md", r"S0 vs g'B: median ratio nan"),
    ("5", "S2 vs reactive controller vacuous", ["VACUOUS"], "data/w5_results.md", r"S2 vs c'B-T3b: median ratio nan"),
    ("5", "35 W: governor feasible in 0 of 25 cells; S1 median power 37.7 W", ["0 of 25", "37.7 W"], "docs/W5B_RESULTS.md", r"d'B was feasible in 0 of 25 cells"),
    ("5", "35 W: only the fixed settings hold feasibility, not in every scene", ["g'B (S0, S1, S1d, S5)"], "docs/W5B_RESULTS.md", r"HW1 holds only for g'B"),
    ("5", "learned predictor study: 271 pooled held-out test cells", ["271 test cells"], "journal/0049_2026-10-23_w5a-selection-rerun-result.md", r"271 test cells"),
    ("5", "grey-box model: 39 false-feasible cells (22.5%)", ["39 (22.5%"], "journal/0049_2026-10-23_w5a-selection-rerun-result.md", r"\| G \| 39"),
    ("5", "gradient-boosted model: 1 false-feasible (0.8%), coverage 88.2% vs 90%", ["1 (0.8%", "88.2%"], "journal/0049_2026-10-23_w5a-selection-rerun-result.md", r"\| HGB \| 1"),
    ("5", "no candidate passed the gates; fallback kept the grey-box model", ["nothing passes", "FALLBACK"], "journal/0049_2026-10-23_w5a-selection-rerun-result.md", r"Verdict by the rule"),
    ("6", "diagnostic: counter 114.3 W vs sampled 39.6 W, 10.02 reads/s", ["114.3", "39.6", "10.02"], "docs/W5B_ADDENDUM_O5.md", r"diag_static 41\.1"),
    ("6", "static path 41.1 W counter, 39.7 W sampled", ["41.1", "39.7"], "docs/W5B_ADDENDUM_O5.md", r"diag_static 41\.1"),
    ("6", "no-reads loop 40.6 W counter, 39.9 W sampled", ["40.6", "39.9"], "docs/W5B_ADDENDUM_O5.md", r"diag_static 41\.1"),
    ("6", "reactive controller 5.7 to 12.7 tok/s with the sampled source", ["5.7", "12.7"], "docs/W5B_ADDENDUM_O5.md", r"c'B's throughput rises from 5\.7 to 12\.7"),
    ("6", "per-read phantom energy 7.5 J and 2.7 J; earlier 4.2 J figure failed", ["7.5 J", "2.7 J", "4.2 J"], "docs/W5B_ADDENDUM_O5.md", r"implied figure is 74\.7 W"),
    ("6", "energy counter read only twice per window in governed cells", ["zero times"], "docs/W5B_ADDENDUM_O5.md", r"reads the energy counter zero times"),
    ("6", "sampled power 250 Hz GetPowerUsage", ["250 Hz"], "docs/W5B_ADDENDUM_O4.md", r"250 Hz GetPowerUsage"),
    ("6", "590 W samples in direct NVML reads (590006 mW)", ["590006 mW"], "journal/0068_2026-11-06_live-dashboard.md", r"590006 mW"),
    ("6", "stored power traces are 0.5 s bin means", ["step_s=0.5"], "experiments/w5b/executors.py", r"def trace_bins"),
    ("6", "counter and sampled means within 15% in every cell (integrity check)", ["0.15"], "experiments/w5b/eval_integrity.py", r"abs\(w - s_\)"),
    ("6", "25368 phantom-idle polls in 5 s with the old policy, none with the fix", ["25368"], "journal/0041_2026-10-22_w45-smoke2-analysis-driver-bug-hybrid-dB.md", r"25368 phantom-idle"),
    ("6", "smoke-1 numbers from the buggy driver declared invalid", ["INVALID"], "journal/0042_2026-10-23_w45-correction-granularity-clean-token-estimate.md", r"INVALID \(buggy driver\)"),
    ("6", "reactive controller fallback picked 0.6 tok/s; second comparator added", ["0.6 tok/s"], "docs/W5B_ADDENDUM_O7.md", r"0\.6 tok/s"),
    ("6", "headroom 2.84 W in the confirmation cells vs registered 2.692 W", ["2.84 W", "2.692 W"], "docs/W5B_ADDENDUM_O7.md", r"The six d'B confirmation cells ran with 2\.84 W"),
    ("7", "barrier model R^2 0.97-0.98 and host overhead 2-34 ms per run (earlier chunking project)", ["R^2 0.97-0.98", "2-34 ms/run"], "CLAUDE.md", r"Chunk boundaries are barriers"),
    ("7", "staleness of the token estimate after a clock change never analysed", ["not yet analysed"], "journal/0046_2026-10-23_w5a-collected-verified-helper-ctrlc.md", r"HW7 staleness check data exist"),
    ("7", "hint protocol: no ablation against a run without hints; Windows only", ["Windows"], "docs/SPEC_FRAME_SLACK_HINTS.md", r"Scope: Windows"),
    ("8", "reviewer is a second Claude session; Arjun arbitrates", ["Arjun arbitrates"], "decisions/ADR-0007_review-protocol.md", r"Arjun arbitrates"),
    ("8", "decision records exist for problem definition, Windows, archiving the earlier project", ["ADR-0001"], "decisions/ADR-0001_archive-variance-project.md", r"^# ADR-0001"),
    ("8", "decision record: problem definition", ["ADR-0002"], "decisions/ADR-0002_problem-definition.md", r"^# ADR-0002"),
    ("8", "decision record: Windows as the primary platform", ["ADR-0003"], "decisions/ADR-0003_windows-primary.md", r"^# ADR-0003"),
]

DERIVED = [
    ("1", "16.67 ms deadline = 1000 / 60", "1000 / 60 = 16.67", "sim/scenarios.py (PERIOD_MS)"),
    ("2", "96% of the throughput and 39% less board power at 1500 MHz", "rel_thr 0.959462 (data/w2_L_results.md); 1 - 56.30 / 91.97 = 0.388", "data/w2_L_results.md rows 1500 and unlocked"),
    ("3", "11.7 ms predicted-latency limit", "0.7 x 16.667 ms = 11.67 ms (margin 0.3)", "data/w5b/constants.json, sim/scenarios.py"),
    ("3", "59.08 W steering budget", "(60 - 2.692) / 0.97 = 59.08", "docs/W5B_EVALUATION.md states 59.080 W"),
    ("5", "S1: 20 tok/s from tokens fitting in two of six 10 s segments", "60 tok/s x 2/6 = 20, observed 19.97 (data/w5b/eval_descriptive.md S1 g'B)", "sim/scenarios.py _STEPS"),
    ("4", "twelve blocks started, two discarded", "block numbers 4 to 15 were used (12); blocks 6 and 7 were discarded, 10 complete", "journal/0064 and journal/0065 (discards), journal/0066 (ten complete blocks)"),
    ("5", "below about 6.6 ms (the rounded 6.57 ms)", "round(16.67 - 10.1, 1) = 6.6; journal 0042 gives 6.57 ms", "journal/0042_2026-10-23_w45-correction-granularity-clean-token-estimate.md"),
    ("5", "frame of 7 ms nominal cost leaves 9.67 ms", "16.67 - 7", "sim/scenarios.py"),
    ("6", "one 590 W sample moves a 60 s mean at 250 Hz by about 0.04 W", "590 W / (60 s x 250 Hz) = 0.039 W", "250 Hz: docs/W5B_ADDENDUM_O4.md; 60 s: executors.py"),
]

TABLE_COLS = {"Uncontrolled": "a", "Best fixed setting": "g'B", "Fixed setting with idle rule": "eB", "Reactive controller": "c'B-T3b", "Governor": "d'B"}


def find(file, regex, tokens):
    p = ROOT / file
    lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
    for i, ln in enumerate(lines, 1):
        if re.search(regex, ln) and all(t in ln for t in tokens):
            return i
    for i, ln in enumerate(lines, 1):                                   # multi-line sources: the tokens may sit on the lines right after the match
        if re.search(regex, ln) and all(t in " ".join(lines[i - 1:i + 3]) for t in tokens):
            return i
    return None


def parse_desc():
    """data/w5b/eval_descriptive.md 60 W table -> {(scene, controller): (line number, tok, late, power)}."""
    out, scene = {}, None
    lines = (ROOT / "data" / "w5b" / "eval_descriptive.md").read_text(encoding="utf-8").splitlines()
    in60 = False
    for i, ln in enumerate(lines, 1):
        if ln.startswith("## 60 W"):
            in60 = True
        elif ln.startswith("## 35 W"):
            in60 = False
        if not in60:
            continue
        m = re.match(r"^\s*(S0|S1|S1d|S2|S5)?\s+(a|g'B|eB|c'B-T3b|c'B-T3c|d'B)\s+10\s+\d+\s+\d+\s+\d+\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)", ln)
        if m:
            scene = m.group(1) or scene
            out[(scene, m.group(2))] = (i, float(m.group(3)), float(m.group(4)), float(m.group(5)))
    return out


def main():
    bad, rows = [], []
    for sec, claim, tokens, file, regex in C:
        n = find(file, regex, tokens)
        if n is None:
            bad.append((sec, claim, file, regex))
        rows.append((sec, claim, file, n))
    d = parse_desc()
    rep = (HERE / "REPORT.md").read_text(encoding="utf-8")
    head = [c.strip() for c in next(x for x in rep.splitlines() if x.startswith("| Scene |")).strip("|").split("|")]
    trows = []
    for ln in rep.splitlines():
        m = re.match(r"\| (S0|S1|S1d|S2|S5) \|(.*)\|\s*$", ln)
        if not m:
            continue
        for col, cell in zip(head[1:], [c.strip() for c in m.group(2).split("|")]):
            tok, late, pw = [float(x) for x in cell.split("/")]
            key = (m.group(1), TABLE_COLS[col])
            ln_no, st, sl, sp = d[key]
            ok = abs(st - tok) <= 0.051 and abs(sl - late) <= 0.0051 and abs(sp - pw) <= 0.051
            trows.append((m.group(1), col, cell, ln_no, st, sl, sp, ok))
            if not ok:
                bad.append(("5", f"Table 1 {key}", "data/w5b/eval_descriptive.md", f"{cell} vs {st}/{sl}/{sp}"))
    out = ["# Claim-to-source table for docs/report/REPORT.md", "",
           "Generated by docs/report/build_sources.py. Each row names the first line of the file that matches the locator and carries every listed number; the build fails otherwise. Paths are relative to the repository root.", "",
           "| Section | Claim in the report | File | Line |", "|---|---|---|---|"]
    out += [f"| {s} | {c} | {f} | {n} |" for s, c, f, n in rows]
    out += ["", "## Table 1, checked cell by cell against data/w5b/eval_descriptive.md (60 W, medians over 10 cells)", "",
            "| Scene | Manager | In the report (tok/s / late % / W) | File line | Source (tok/s, late %, W) | Match to the printed rounding |", "|---|---|---|---|---|---|"]
    out += [f"| {s} | {c} | {cell} | data/w5b/eval_descriptive.md:{ln} | {st} / {sl} / {sp} | {'yes' if ok else 'NO'} |" for s, c, cell, ln, st, sl, sp, ok in trows]
    out += ["", "## Derived numbers (arithmetic on sourced numbers; the inputs are in the rows above)", "", "| Section | Number | Arithmetic | Inputs from |", "|---|---|---|---|"]
    out += [f"| {s} | {a} | {b} | {c} |" for s, a, b, c in DERIVED]
    out += ["", "## Not traceable to a file in this repository", "",
            "None of the numbers in the report. One finer figure lives outside the repository: the earlier chunking project's ARCHIVE_NOTE.md (sibling folder variance_gpu_project) gives the barrier-model R-squared as 0.968 to 0.979; the report uses the rounded 0.97 to 0.98 from CLAUDE.md. The 590 W NVML samples were seen in direct reads on 2026-11-06 and recorded in journal/0068; the raw samples of the registered cells were never stored, so their frequency there cannot be sourced (stated as an open check in the report)."]
    (HERE / "SOURCES.md").write_text("\n".join(out) + "\n", encoding="utf-8")
    if bad:
        print("UNSOURCED:")
        for b in bad:
            print("  ", b)
        sys.exit(1)
    print(f"{len(rows)} claims, {len(trows)} table cells, all sourced")


if __name__ == "__main__":
    main()
