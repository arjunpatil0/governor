// v2 sprint 2 (docs/V2_SPRINT2_HANDOVER.md): greedy decode driver for the PATCHED llama.cpp (third_party/llama.cpp_v2) that can gate its work on the LIVE frame hint, per token (G = 1, the v1
// whole-token gate) or per layer group (GGML_CUDA_PAUSE_GROUPS = G > 1, the pausable gate, with the hook reading the hint before each group is launched).
// usage: llama_handover_bench <model.gguf> <prompt.txt> <out_prefix> <n_prompt>
// env:   GGML_CUDA_PAUSE_GROUPS=G (default 1)   HINT_NAME=<named mapping of the frame hint, docs/FRAME_HINT_SPEC.md>   GATE=1 (wait until the unit fits the slack)   GUARD_MS (default 0.5)
// Flow: load the model (every layer on the GPU or abort), prefill n_prompt tokens, print READY, read "GO <t_stop_qpc_s>" on stdin, then decode until t_stop (QPC seconds, the clock of
// time.perf_counter). Gate rule = v1 / FRAME_HINT_SPEC section 7: start a unit only while the app is not busy and now + estimate + guard <= next deadline; the estimate of a unit is the median of its
// last 8 clean durations (a unit is clean if it ended before the deadline it was gated against), EWMA 0.9/0.1 before the first clean one; one estimate per group index (one for the whole token at G = 1).
// Writes <out_prefix>_tokens.csv (t_tok_end_s, dur_ms, gate_wait_ms) and <out_prefix>_groups.csv (token, group, t_launch_s, t_done_s, gate_wait_ms). Gate off: units start back to back (free-running).
#include <windows.h>
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <iostream>
#include <sstream>
#include <string>
#include <vector>
#include "llama.h"

static std::string g_log;
static void log_cb(ggml_log_level, const char *text, void *) { g_log += text; }
static double qpc_now() {
    static LARGE_INTEGER f = [] { LARGE_INTEGER x; QueryPerformanceFrequency(&x); return x; }();
    LARGE_INTEGER c; QueryPerformanceCounter(&c);
    return (double)c.QuadPart / (double)f.QuadPart;
}
static int die(const char *msg) { fprintf(stderr, "FATAL %s\n", msg); return 2; }

// ---- frame hint reader (docs/FRAME_HINT_SPEC.md sections 5): last good record kept, stale after 0.1 s = idle
static volatile uint64_t *g_hint = nullptr;
static double g_last[3] = {0, 0, 0};
static bool g_have = false;
static int read_hint(double out[3]) {
    for (int i = 0; i < 200; i++) {
        uint64_t s1 = g_hint[0];
        if (s1 == 0) return 0;
        if (s1 & 1) continue;
        memcpy(out, (const unsigned char *)g_hint + 16, 24);
        MemoryBarrier();
        if (g_hint[0] == s1) return 1;
    }
    return 0;
}
static void get_hint(double now, bool *busy, double *next) {
    double v[3];
    if (read_hint(v)) { memcpy(g_last, v, sizeof v); g_have = true; }
    *busy = false; *next = INFINITY;
    if (g_have && now - g_last[2] <= 0.1) { *busy = g_last[0] != 0.0; *next = g_last[1]; }
}

// ---- per-unit duration estimate
struct Est {
    std::vector<double> clean; double ewma = 0; bool have = false;
    void push(double d, bool overlapped) {
        ewma = have ? 0.9 * ewma + 0.1 * d : d; have = true;
        if (!overlapped) { clean.push_back(d); if (clean.size() > 8) clean.erase(clean.begin()); }
    }
    double value() const {
        if (clean.empty()) return have ? ewma : 0.0;
        std::vector<double> s = clean; std::sort(s.begin(), s.end());
        size_t n = s.size(); return n % 2 ? s[n / 2] : 0.5 * (s[n / 2 - 1] + s[n / 2]);
    }
};

static bool g_gate = false;
static double g_guard_s = 0.0005;
static int g_G = 1;
static std::vector<Est> g_est;
static double g_next_at_start = INFINITY;       // the deadline the current unit was gated against (INFINITY = app idle)
static int g_token = 0;
static double g_pending_wait_ms = 0.0;
struct GroupRec { int token, group; double t_launch, t_done, wait_ms; };
static std::vector<GroupRec> g_groups;

// Wait until a unit of estimated duration est_s fits; returns the wait in ms. Records the deadline the unit is gated against.
static double gate_wait(double est_s) {
    const double t0 = qpc_now();
    for (;;) {
        const double now = qpc_now();
        bool busy; double next;
        get_hint(now, &busy, &next);
        if (!busy && now + est_s + g_guard_s <= next + 1e-12) { g_next_at_start = next; return (now - t0) * 1e3; }
        if (next - now > 0.004) Sleep(1); else YieldProcessor();
    }
}

// Called by the patched ggml-cuda after group g has completed (stream synchronised), before the next group is launched.
static void group_hook(int group, int n_groups, double t_launch, double t_done, float, void *) {
    const double dur = t_done - t_launch;
    const bool overlapped = std::isfinite(g_next_at_start) ? t_done > g_next_at_start : false;
    g_est[group].push(dur, overlapped);
    g_groups.push_back({g_token, group, t_launch, t_done, g_pending_wait_ms});
    g_pending_wait_ms = 0.0;
    if (g_gate && group < n_groups - 1) g_pending_wait_ms = gate_wait(g_est[group + 1].value());
}

typedef void (*hook_fn)(int, int, double, double, float, void *);
typedef void (*set_hook_fn)(hook_fn, void *);

int main(int argc, char **argv) {
    if (argc < 5) return die("usage: model prompt out_prefix n_prompt");
    const char *model_path = argv[1], *prompt_path = argv[2];
    const std::string prefix = argv[3];
    const int n_prompt = atoi(argv[4]);
    const char *ge = getenv("GGML_CUDA_PAUSE_GROUPS"), *hn = getenv("HINT_NAME"), *gt = getenv("GATE"), *gu = getenv("GUARD_MS");
    g_G = ge ? (std::max)(1, atoi(ge)) : 1;
    g_gate = gt && atoi(gt) == 1;
    if (gu) g_guard_s = atof(gu) * 1e-3;
    g_est.assign(g_G, Est());

    llama_log_set(log_cb, nullptr);
    llama_backend_init();
    if (!llama_supports_gpu_offload()) return die("this llama.cpp build has no GPU offload (CPU build)");
    llama_model_params mp = llama_model_default_params();
    mp.n_gpu_layers = 999;
    llama_model *model = llama_model_load_from_file(model_path, mp);
    if (!model) return die("model load failed");
    int off = -1, tot = -1;
    size_t p = g_log.find("offloaded ");
    if (p != std::string::npos) sscanf(g_log.c_str() + p, "offloaded %d/%d layers", &off, &tot);
    if (g_log.find("CUDA") == std::string::npos) return die("no CUDA device in the load log");
    if (off < 0 || off != tot) return die("not all layers offloaded to the GPU");
    printf("EXEC_MODE cuda offloaded=%d/%d n_layer=%d groups=%d gate=%d guard_ms=%.2f\n", off, tot, llama_model_n_layer(model), g_G, (int)g_gate, g_guard_s * 1e3);

    if (g_gate) {
        if (!hn) return die("GATE=1 needs HINT_NAME");
        HANDLE hm = OpenFileMappingA(FILE_MAP_ALL_ACCESS, FALSE, hn);
        if (!hm) return die("cannot open the frame hint mapping (the foreground creates it first)");
        g_hint = (volatile uint64_t *)MapViewOfFile(hm, FILE_MAP_ALL_ACCESS, 0, 0, 40);
        if (!g_hint || g_hint[1] != 3) return die("frame hint geometry mismatch");
    }
    if (g_G > 1) {
        HMODULE m = GetModuleHandleA("ggml-cuda.dll");
        if (!m) m = LoadLibraryA("ggml-cuda.dll");
        set_hook_fn set_hook = m ? (set_hook_fn)GetProcAddress(m, "ggml_backend_cuda_set_group_hook") : nullptr;
        if (!set_hook) return die("GGML_CUDA_PAUSE_GROUPS > 1 but ggml-cuda.dll does not export ggml_backend_cuda_set_group_hook (not the patched build)");
        set_hook(group_hook, nullptr);
    }

    llama_context_params cp = llama_context_default_params();
    cp.n_ctx = 6144; cp.n_batch = 512; cp.no_perf = true;
    llama_context *ctx = llama_init_from_model(model, cp);
    if (!ctx) return die("context creation failed");
    const llama_vocab *vocab = llama_model_get_vocab(model);
    std::ifstream f(prompt_path, std::ios::binary); std::stringstream ss; ss << f.rdbuf(); std::string text = ss.str();
    if (text.empty()) return die("empty prompt file");
    std::vector<llama_token> toks(text.size() + 8);
    int n = llama_tokenize(vocab, text.c_str(), (int32_t)text.size(), toks.data(), (int32_t)toks.size(), true, false);
    if (n < n_prompt) return die("prompt file has fewer tokens than n_prompt");
    toks.resize(n_prompt);
    g_token = -1;
    if (llama_decode(ctx, llama_batch_get_one(toks.data(), (int32_t)toks.size())) != 0) return die("prefill failed");
    llama_sampler *smpl = llama_sampler_chain_init(llama_sampler_chain_default_params());
    llama_sampler_chain_add(smpl, llama_sampler_init_greedy());
    llama_token cur = llama_sampler_sample(smpl, ctx, -1);
    // three ungated warm-up tokens so that the graphs exist and the estimates have a first value before the clock starts
    const bool gate_saved = g_gate; g_gate = false;
    for (int i = 0; i < 3; i++) { g_token = -1; if (llama_decode(ctx, llama_batch_get_one(&cur, 1)) != 0) return die("warm-up decode failed"); cur = llama_sampler_sample(smpl, ctx, -1); }
    g_gate = gate_saved;
    g_groups.clear();
    printf("READY\n"); fflush(stdout);
    char line[128] = {0};
    if (!fgets(line, sizeof line, stdin)) return die("no GO line on stdin");
    double t_stop = 0; if (sscanf(line, "GO %lf", &t_stop) != 1) return die("expected 'GO <t_stop_qpc_s>'");

    struct Tok { double t_end, dur_ms, wait_ms; };
    std::vector<Tok> te; te.reserve(1 << 16);
    while (qpc_now() < t_stop && (int)te.size() + n_prompt + 8 < (int)cp.n_ctx) {
        g_token = (int)te.size();
        double wait_ms = 0.0;
        if (g_gate) wait_ms = gate_wait(g_est[0].value());           // before the first group (or the whole token at G = 1)
        g_pending_wait_ms = wait_ms;
        const double t0 = qpc_now();
        if (llama_decode(ctx, llama_batch_get_one(&cur, 1)) != 0) return die("decode failed");
        cur = llama_sampler_sample(smpl, ctx, -1);                     // reads logits: synchronises with the GPU
        const double t1 = qpc_now();
        if (g_G == 1) {
            g_est[0].push(t1 - t0, std::isfinite(g_next_at_start) ? t1 > g_next_at_start : false);
            g_groups.push_back({g_token, 0, t0, t1, wait_ms});
        }
        te.push_back({t1, (t1 - t0) * 1e3, wait_ms});
    }
    FILE *o = fopen((prefix + "_tokens.csv").c_str(), "w");
    if (!o) return die("cannot open tokens output");
    fprintf(o, "t_tok_end_s,dur_ms,gate_wait_ms\n");
    for (const Tok &t : te) fprintf(o, "%.9f,%.6f,%.6f\n", t.t_end, t.dur_ms, t.wait_ms);
    fclose(o);
    o = fopen((prefix + "_groups.csv").c_str(), "w");
    if (!o) return die("cannot open groups output");
    fprintf(o, "token,group,t_launch_s,t_done_s,gate_wait_ms\n");
    for (const GroupRec &r : g_groups) fprintf(o, "%d,%d,%.9f,%.9f,%.6f\n", r.token, r.group, r.t_launch, r.t_done, r.wait_ms);
    fclose(o);
    printf("DONE tokens=%zu groups=%zu ctx_end=%d\n", te.size(), g_groups.size(), n_prompt + (int)te.size());
    llama_sampler_free(smpl); llama_free(ctx); llama_model_free(model); llama_backend_free();
    return 0;
}
