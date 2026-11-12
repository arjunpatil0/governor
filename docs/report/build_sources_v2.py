"""Builds docs/report/SOURCES_V2.md: for every number (or group of numbers) in docs/report/REPORT_V2.md, the file and line that carry it. A claim row is (section, claim, tokens, file, regex): the first line of
the file that matches the regex AND contains every token is the source; if there is none the build fails, so a number that no committed file carries cannot stay in the table. Numbers that are arithmetic on
sourced numbers are listed under 'Derived'. The v1 numbers quoted in section 1 are sourced to docs/report/REPORT.md (the v1 report's own sources are in docs/report/SOURCES.md).
   python docs/report/build_sources_v2.py"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
S1, S2, S3, S4 = ("docs/V2_SPRINT1_PAUSE_COST.md", "docs/V2_SPRINT2_HANDOVER.md", "docs/V2_SPRINT3_JITTER.md", "docs/V2_SPRINT4_LOW_SLACK.md")
V1 = "docs/report/REPORT.md"

C = [  # (section, claim in the report, tokens that must be on the source line, file, regex locating the line)
    ("1", "clean 3B token 10.1 ms; frame of 7 ms nominal leaves 9.67 ms; no token fits", ["10.1 ms", "9.67 ms"], V1, r"A clean 3B token takes"),
    ("1", "no token in any of the 40 cells of S0 and S5 (aligned pacing, best fixed and idle-rule settings)", ["40 cells", "S0 and S5"], V1, r"A clean 3B token takes"),
    ("1", "S1: the same setting delivered 19.97 tok/s", ["19.97"], V1, r"A clean 3B token takes"),
    ("1", "governor unaligned pacing: 17.5 tok/s in S0, 7.8 in S5", ["17.5", "7.8"], V1, r"That recovers tokens"),
    ("1", "late frames 1.72% in S1 and 4.72% in S5, limit 1%", ["1.72%", "4.72%"], V1, r"That recovers tokens"),
    ("2", "14 groups +2.2%, longest piece 1.95 ms (3B)", ["14", "2.2%", "1.95 ms"], S1, r"^\| 14 \| 12\.6%"),
    ("2", "28 groups +4.3%, longest piece 1.63 ms (3B)", ["28", "4.3%", "1.63 ms"], S1, r"^\| 28 \| 26\.3%"),
    ("2", "G = 1 token 10.14 ms", ["10.14 ms"], S1, r"^\| 1 \| 0% \| 0% \(token 10\.14 ms\)"),
    ("2", "cost per boundary 16 to 31 microseconds (forecast 100)", ["16 to 31 microseconds", "100"], S1, r"The cost per boundary is"),
    ("2", "graphs off +14.2% (11.58 ms)", ["14.2%", "11.58 ms"], S1, r"^\| graphs off"),
    ("2", "output head about 1.3 ms for the 3B (forecast 0.8)", ["1.3 ms", "0.8"], S1, r"output projection in the last group costs"),
    ("2", "tokens identical to the stock run in all nine configurations", ["identical", "nine configurations"], S1, r"The tokens it produces are identical"),
    ("2", "forced 2 ms wait: G = 4 rises 6.07 ms against 6.0 expected", ["6.0 ms", "6.07 ms"], S1, r"^\| G = 4 with 2 ms per boundary"),
    ("2", "8B: 14 groups +1.4%, longest 3.61 ms", ["1.4%", "3.61 ms"], S2, r"^\| 14 \| 21\.32 ms"),
    ("2", "8B 28 groups +2.9%, longest group 2.99 ms", ["2.9%", "2.99 ms"], S2, r"^\| 28 \| 21\.62 ms"),
    ("2", "8B output projection about 2.4 ms against 1.3 ms for the 3B and 1.8 forecast", ["2.4 ms", "1.3 ms", "1.8 ms"], S2, r"A layer takes about 0.63 ms"),
    ("2", "pinned llama.cpp commit 620d2225c, version 0.7.0", ["620d2225c", "0.7.0"], S1, r"Feasibility reading"),
    ("2", "ggml_graph_view not exported from ggml-base.dll", ["ggml_graph_view", "not exported"], S1, r"One correction to the plan"),
    ("2", "per-group estimate: median of the last 8 clean durations", ["median", "8"], S2, r"one estimate per group index"),
    ("3", "sprint 1 forecast committed as 83db807", ["83db807"], S1, r"forecast was committed \(83db807\)"),
    ("3", "sprint 2 forecast committed as 09a0cd0", ["09a0cd0"], S2, r"committed \(09a0cd0\)"),
    ("3", "sprint 3 forecast commit 447105e and sprint 4 forecast commit b24edae (git history; the changelog names the sprints)", ["Jitter study"], "CHANGELOG.md", r"Jitter study"),
    ("3", "jitter model: CV 0.15 moderate, 0.30 heavy, 2x spikes in 2% of heavy; bursts 0.5 to 1.5 ms in 5% and 10%", ["0.15", "0.30", "2%", "5%", "10%"], S3, r"^Jitter on the synthetic 60 fps foreground"),
    ("3", "sprint 3: 28 cells", ["28 cells"], "CHANGELOG.md", r"^- 28 cells"),
    ("3", "sprint 4: 2 levels x 6 arms x 2 reps = 24 cells of 60 s, 5 s warm-up", ["24 cells", "5 s warm-up"], S4, r"2 levels x 6 arms x 2 reps"),
    ("3", "sprint 2: 12 cells, 60 s windows after a 5 s warm-up, 1800 MHz, guard 0", ["12 cells", "5 s warm-up", "1800 MHz", "guard 0"], S2, r"^12 cells, 60 s measured windows"),
    ("3", "power_rejected 0 in all end-to-end cells", ["power_rejected", "0 in all 28"], S3, r"power_rejected"),
    ("4", "first-kernel delay: whole token mid-token median 0.477 ms, p99 0.874, max 1.69, n = 6,172", ["6,172", "0.477", "0.874", "1.69"], S2, r"^\| whole token \(G = 1\), free \| mid-token"),
    ("4", "14 groups mid-group median 0.477 ms", ["0.477", "6,193"], S2, r"^\| 14 groups, free \| mid-group"),
    ("4", "WDDM slice 0.374 ms and switch gap 0.148 ms", ["0.374", "0.148"], S2, r"quantum of about 0.37 ms"),
    ("4", "sprint 2 forecast: whole-token wait about 10 ms, 14 groups about 2 ms plus the switch", ["10 ms", "2 ms"], S2, r"^Stated forecast for handover latency"),
    ("4", "S1 3B whole token 19.95 tok/s, 0.00% late", ["19.95", "0.00%"], S2, r"^\| S1, 3B \| whole token"),
    ("4", "S1 3B 14 groups 47.9 tok/s", ["47.9", "0.00%"], S2, r"^\| S1, 3B \| 14 groups"),
    ("4", "S5 8B whole token 0.0 tok/s", ["0.0", "0.00%"], S2, r"^\| S5, 8B \| whole token"),
    ("4", "S5 8B 14 groups 24.2 tok/s", ["24.2", "0.00%"], S2, r"^\| S5, 8B \| 14 groups"),
    ("4", "whole-token gate reproduces the registered v1 setting 19.97 tok/s", ["19.95", "19.97"], S2, r"Sanity check on the baseline"),
    ("4", "all 12 cells 0.00% late frames", ["0.00% late frames", "12 end-to-end"], S2, r"^WIN on throughput"),
    ("4", "sprint 3 moderate: 3B 14 groups 48.2 tok/s, excess 0.00 pp", ["48.2", "0.00"], S3, r"^\| moderate \| 3B 14 groups"),
    ("4", "sprint 3 moderate whole token 21.9 tok/s", ["21.9", "0.00"], S3, r"^\| moderate \| 3B whole token"),
    ("4", "sprint 3 heavy: 14 groups 45.9 tok/s, excess 0.08 pp", ["45.9", "0.08"], S3, r"^\| heavy \| 3B 14 groups"),
    ("4", "sprint 3 heavy whole token 23.3 tok/s", ["23.3", "0.00"], S3, r"^\| heavy \| 3B whole token"),
    ("4", "sprint 3 limits 1 pp (moderate) and 2 pp (heavy); PASS", ["PASS", "1 and 2"], S3, r"^PASS by the decision rule"),
    ("4", "group gate touches 16% to 35% of frames (0.1% to 0.8% without jitter)", ["16% to 35%", "0.1% to 0.8%"], S3, r"Without jitter decode touched"),
    ("4", "touched-frame slowdown p99 1.2 to 1.7", ["1.2 to 1.7"], S3, r"The group gate's touches are short"),
    ("4", "97% of late frames at heavy are the app's own", ["97%"], S3, r"^PASS by the decision rule"),
    ("4", "sprint 3 frames have 8 to 11 ms of slack", ["8 to 11 ms"], "CHANGELOG.md", r"8 to 11 ms of slack"),
    ("4", "sprint 4 SOLO medians 12.68 ms and 14.70 ms, free 3.99 and 1.97 ms", ["12.68 ms", "14.70 ms", "3.99 ms", "1.97 ms"], S4, r"^PASS at both slack levels|SOLO median frame times came out"),
    ("4", "SOLO late 3.85% at TIGHT and 29.3% at VERY TIGHT", ["3.85%", "29.3%"], S4, r"^PASS at both slack levels"),
    ("4", "Table 1 row 3B whole token at TIGHT: 0.0, +0.03", ["0.0", "+0.03"], S4, r"^\| 3B whole token \| 0\.0 \| 3\.88"),
    ("4", "Table 1 row 3B whole token at VERY TIGHT: 0.0, -0.26", ["0.0", "-0.26"], S4, r"^\| 3B whole token \| 0\.0 \| 29\.07"),
    ("4", "Table 1 row 3B 14 groups guard 0 at TIGHT: 17.5, +0.28", ["17.5", "+0.28"], S4, r"^\| 3B 14 groups, guard 0 \| 17\.5"),
    ("4", "Table 1 row 3B 14 groups guard 0 at VERY TIGHT: 7.2, +1.71", ["7.2", "+1.71"], S4, r"^\| 3B 14 groups, guard 0 \| 7\.2"),
    ("4", "Table 1 row 3B 14 groups guard 1.0 at TIGHT: 13.3, +0.03", ["13.3", "+0.03"], S4, r"^\| 3B 14 groups, guard 1\.0 \| 13\.3"),
    ("4", "Table 1 row 3B 14 groups guard 1.0 at VERY TIGHT: 4.6, -0.19", ["4.6", "-0.19"], S4, r"^\| 3B 14 groups, guard 1\.0 \| 4\.6"),
    ("4", "Table 1 row 8B 14 groups guard 1.0 at TIGHT: 5.4, +0.15", ["5.4", "+0.15"], S4, r"^\| 8B 14 groups, guard 1\.0 \| 5\.4"),
    ("4", "Table 1 row 8B 14 groups guard 1.0 at VERY TIGHT: 1.5, +0.53", ["1.5", "+0.53"], S4, r"^\| 8B 14 groups, guard 1\.0 \| 1\.5"),
    ("4", "Table 1 row 8B 28 groups guard 1.0 at TIGHT: 6.2, -0.03", ["6.2", "-0.03"], S4, r"^\| 8B 28 groups, guard 1\.0 \| 6\.2"),
    ("4", "Table 1 row 8B 28 groups guard 1.0 at VERY TIGHT: 2.0, -0.08", ["2.0", "-0.08"], S4, r"^\| 8B 28 groups, guard 1\.0 \| 2\.0"),
    ("4", "7,200 frames per arm and level, two reps pooled", ["7200"], S4, r"Two reps pooled per cell"),
    ("4", "VERY TIGHT rep 1 +2.28 pp, rep 2 +1.14 pp", ["+2.28", "+1.14"], S4, r"^\| 3B 14 groups, guard 0 \| 7\.2"),
    ("4", "PASS rests on the mean of two reps with rep 1 over the limit", ["+2.28 pp in rep 1", "2 pp limit"], S4, r"The VERY TIGHT pass is thin"),
    ("4", "8B VERY TIGHT 1.5 and 2.0 tok/s", ["1.5 to 2.0"], S4, r"^PASS at both slack levels"),
    ("4", "margin: decode-attributed late frames 21 to 2 and 80 to 3; tok/s kept 76% and 64%", ["21 to 2", "80 to 3", "76%", "64%"], S4, r"^\| MARGIN WORKS"),
    ("4", "guard-0 attributed late frames at VERY TIGHT: 54 overlap, 17 early, 9 burst", ["54", "17", "9"], S4, r"^\| 3B 14 groups, guard 0 \| 2235"),
    ("4", "guard-0 arm adds 21 decode-attributed late frames at TIGHT and 80 at VERY TIGHT", ["21", "80"], S4, r"The guard-0 arm adds 21 decode-attributed"),
    ("4", "calibration cells 12.457 and 14.473 ms", ["12.457", "14.473"], S4, r"^Calibration \(a 10 s SOLO cell"),
    ("5", "sprint 4 forecast: SOLO late about 3% and about 17%", ["3%", "17%"], S4, r"^SOLO late frames: about 3%"),
    ("5", "sprint 4 forecast guard 0: about +2 and +6 pp; about 20 tok/s (14 to 24)", ["about 20 (14 to 24)", "+2 pp", "+6 pp"], S4, r"^\| 3B 14 groups, guard 0 \| about 20"),
    ("5", "sprint 4 forecast guard 1.0: 13 (9 to 17) and 1 (0 to 3)", ["about 13 (9 to 17)", "about 1 (0 to 3)"], S4, r"^\| 3B 14 groups, guard 1\.0 \| about 13"),
    ("5", "sprint 4 forecast margin loss about 35% against 15% allowed; forecast PASS arm guard 1.0 at TIGHT", ["35%", "15%", "PASS arm"], S4, r"^Decision rule forecast"),
    ("5", "sprint 4 forecast 8B collapses at VERY TIGHT", ["8B", "collapse"], S4, r"^Reasoning in one place"),
    ("5", "sprint 3 forecast vs measured: SOLO heavy about 3% vs 1.31%", ["about 3%", "1.31%"], S3, r"^\| SOLO late frames, heavy"),
    ("5", "sprint 3 14-group excess heavy forecast about 0.8 pp (0.2 to 2), measured 0.08 pp", ["0.8 pp", "0.08 pp"], S3, r"^\| 14-group \(3B\) excess late, heavy"),
    ("5", "sprint 3 whole-token tok/s at heavy forecast 10 to 15, measured 23.3", ["10 to 15", "23.3"], S3, r"^\| whole-token tok/s at heavy"),
    ("5", "sprint 3 verdict PASS, no FAIL, forecast and measured", ["PASS"], S3, r"^\| decision rule \|"),
    ("5", "sprint 1 forecast: 100 us per boundary, head 0.8 ms", ["100 microseconds", "0.8 ms"], S1, r"^Forecast committed before measuring"),
    ("5", "sprint 2 forecast: 3B little difference within a few percent; 8B few to ten tok/s", ["few percent", "few to ten"], S2, r"^For the end-to-end cells"),
    ("5", "sprint 2 8B whole token about 0 tok/s forecast", ["about 0 tok/s"], S2, r"^For the end-to-end cells"),
    ("5", "SOLO late at heavy 1.31%", ["1.31"], S3, r"^\| heavy \| SOLO"),
    ("6", "8B 14 groups 60.3 W at level none", ["60.3"], S3, r"^\| none \| 8B 14 groups"),
    ("6", "3B 14 groups 57.9 W in sprint 2", ["57.9 W"], S2, r"^\| S1, 3B \| 14 groups"),
    ("6", "8B 14 groups 59.2 W in sprint 2", ["59.2 W"], S2, r"^\| S5, 8B \| 14 groups"),
    ("6", "prefill was not split", ["Prefill was not split"], S1, r"Prefill was not split"),
]

DERIVED = [
    ("5", "5.7 times too high (overhead at 14 groups)", "12.6 / 2.2", "Sprint 1 table"),
    ("5", "6.1 times too high (overhead at 28 groups)", "26.3 / 4.3", "Sprint 1 table"),
    ("5", "about 6 times too high (cost per boundary)", "100 us / 17 us at 14 groups (range 3 to 6 over the other G)", "Sprint 1 table"),
    ("5", "about 20 times too high (foreground wait)", "10 ms / 0.477 ms = 21", "Sprint 2 handover table"),
    ("5", "loss of 24% and 36% (margin)", "1 - 0.76 and 1 - 0.64", "Sprint 4 margin row"),
    ("abstract, 4", "47.9 / 19.95 = 2.4 times, so 'more than doubles'", "47.9 / 19.95", "Sprint 2 end-to-end table"),
    ("4", "7,200 frames per arm", "2 reps x 60 s x 60 fps", "Sprint 4 setup"),
    ("1", "free time = 16.67 ms minus the SOLO median", "1000 / 60", "sim/scenarios.py PERIOD_MS"),
    ("abstract", "1.4% to 2.2% slower per token", "8B 14 groups +1.4%, 3B 14 groups +2.2% in token time", "Sprint 1 and 2 tables"),
]

EXTERNAL = [  # (cited as, URL, what the report says about it and where in the source; rows marked [12 Nov] were read on 2026-11-12)
    ("ConServe, arXiv 2410.01228", "https://arxiv.org/abs/2410.01228", "co-serves online and offline LLM requests; sub-iteration, layer-wise preemption lets offline work yield on online load spikes"),
    ("QLLM, arXiv 2503.09304", "https://arxiv.org/abs/2503.09304", "preempts best-effort MoE inference at expert granularity to cut time to first token of latency-sensitive requests; drops iteration-level scheduling so it can preempt at any layer"),
    ("LayerLoom, arXiv 2611.00652", "https://arxiv.org/abs/2611.00652", "schedules LoRA backward work at layer rather than iteration granularity, within the latency slack of in-flight inference requests"),
    ("Ripple, arXiv 2611.01067", "https://arxiv.org/abs/2611.01067", "unified-memory edge device; splits inference into pausable layer-based units, converts CPU job deadline slack into a GPU-byte budget; SGLang engine hooks and a central scheduler; evaluated on DGX Spark"),
    ("Ripple margin and guard [12 Nov]", "https://arxiv.org/html/2611.01067", "margin that adapts after every job; tight-deadline guard withholds probe and floor f. Method text (section 4, margin; rank endpoints and the tight-deadline guard): \"The margin is a rank among the retained residuals whose level alpha adapts after every job\"; \"At the tightest deadlines Ripple adds one rule: if the predicted delay from GPU volume f exceeds a job's remaining slack ... then that job gets neither the probe nor the floor f nor a crossing into its release\""),
    ("REEF, OSDI 2022", "https://www.usenix.org/conference/osdi22/presentation/han", "microsecond-scale preemption by resetting idempotent kernels; evaluated on an AMD GPU with a restricted NVIDIA port"),
    ("Hummingbird, arXiv 2601.04071", "https://arxiv.org/abs/2601.04071", "microsecond-granularity preemption on closed-source GPUs"),
    ("GCAPS, arXiv 2406.05221", "https://arxiv.org/abs/2406.05221", "GPU context scheduling at the driver level for real-time tasks; response-time analysis; Jetson results"),
    ("FIKIT, arXiv 2311.10359", "https://arxiv.org/abs/2311.10359", "lets low-priority tasks run in the idle gaps between kernels of high-priority tasks"),
    ("VUDA, arXiv 2605.01352", "https://arxiv.org/abs/2605.01352", "controlled spatial sharing of CUDA compute and Vulkan graphics on NVIDIA GPUs without modifying drivers (abstract)"),
    ("VUDA section 7.5 [12 Nov]", "https://arxiv.org/html/2605.01352", "section 7.5 (Figure 15, AI gaming): \"a 4K, nine-pass offscreen Vulkan renderer paced at 60 Hz and Qwen2.5 inference through unmodified llama.cpp. The inference workload continuously prefills 2,048-token prompts\"; RTX 4090 1.5B and 7B Q4_K_M, A800 7B and 14B FP16; \"Partitioning lowers GPU-time p99 to 13.44-14.98 ms on RTX 4090 and completion-latency p99 to 15.32-15.67 ms on A800\"; \"VUDA-full retains 39-64% of baseline prefill throughput\"; section 7 platforms: \"under Linux\"; \"inter-SM partitioning with a compute quota q, measured in TPCs\""),
    ("EdgePace, arXiv 2610.37307 [12 Nov]", "https://arxiv.org/abs/2610.37307", "abstract: \"creates safe suspension points across prefill and decode, monitors foreground memory demand and stalls at low cost, and schedules inference according to contention risk, deadline slack, and output freshness\"; OnePlus 13 and three Jetson platforms; \"reduces foreground deadline misses by 24.1%--96.1% while retaining 64.9%--98.5% of LLM throughput\""),
    ("Nixie, arXiv 2601.11743 [12 Nov]", "https://arxiv.org/abs/2601.11743", "abstract: \"efficient and transparent temporal multiplexing on consumer GPUs without requiring any application or driver changes\"; \"coordinates GPU memory allocation and kernel launch behavior\"; \"MLFQ-inspired techniques\"; \"improves latency of real interactive code-completion tasks by up to 3.8x\""),
    ("NVIGI, GPU Scheduling for AI, SDK 1.7.0 [12 Nov]", "https://docs.nvidia.com/nvigi-sdk/1.7.0/docs/nvigi_core/docs/GpuSchedulingForAI.html", "whole page read. \"NVIGI's GPU scheduling uses D3D async compute for D3D plugins and CUDA in Graphics (CIG) for CUDA plugins. It also takes advantage of a driver interface for setting relative priorities of CUDA vs D3D graphics workloads\" (Supported Graphics APIs); modes kPrioritizeGraphics, kPrioritizeCompute, kBalance, \"these modes are hints to the GPU scheduling hardware\" (How to Set the Relative Priority); GPT plugin `nvigi::plugin::gpt::ggml::cuda` (Supported Plugins); \"fill in a D3D12Parameters struct\" with the graphics queue (How to Use); \"CUDA requires that Hardware scheduling be enabled in Windows 11\" (table note)"),
    ("Kang, arXiv 2606.16106 [12 Nov]", "https://arxiv.org/abs/2606.16106", "title \"Edge-Inference Governors Need Memory-Clock State\" (Jaehoon Kang, cs.PF, v3 of 8 Jul 2026); abstract: \"an EMC-blind GPU-only fit misses 25-28% of cycles at tight deadlines, whereas an EMC-aware two-cell refit holds misses to <=0.9%\"; \"a dispersion-banded guard, validated on held-out trials\"; Jetson Orin"),
]


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


def main():
    rows, bad = [], []
    for sec, claim, tokens, file, regex in C:
        n = find(file, regex, tokens)
        if n is None:
            bad.append((sec, claim, file, regex))
        rows.append((sec, claim, file, n))
    out = ["# Claim-to-source table for docs/report/REPORT_V2.md", "",
           "Generated by docs/report/build_sources_v2.py. Each row names the first line of the file that matches the locator and carries every listed number; the build fails otherwise. Paths are relative to the repository root.", "",
           "| Section | Claim in the report | File | Line |", "|---|---|---|---|"]
    out += [f"| {s} | {c} | {f} | {n} |" for s, c, f, n in rows]
    out += ["", "## Derived numbers (arithmetic on sourced numbers; the inputs are in the rows above)", "", "| Section | Number | Arithmetic | Inputs from |", "|---|---|---|---|"]
    out += [f"| {s} | {a} | {b} | {c} |" for s, a, b, c in DERIVED]
    out += ["", "## Related work (section 8): abstracts read on 2026-11-08; rows marked [12 Nov] read on 2026-11-12 (extracted passages or the full page, not the full papers)", "", "| Cited as | URL | What section 8 says, and where in the source |", "|---|---|---|"]
    out += [f"| {a} | {b} | {c} |" for a, b, c in EXTERNAL]
    (HERE / "SOURCES_V2.md").write_text("\n".join(out) + "\n", encoding="utf-8")
    if bad:
        print("UNSOURCED:")
        for b in bad:
            print("  ", b)
        sys.exit(1)
    print(f"{len(rows)} claims, all sourced")


if __name__ == "__main__":
    main()
