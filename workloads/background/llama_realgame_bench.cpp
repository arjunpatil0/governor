// Greedy decode driver for sprint R1 (real-game co-location). Runs STOCK llama.cpp (third_party/llama.cpp, unpatched) on the CUDA or the Vulkan backend.
// usage: llama_realgame_bench <model.gguf> <prompt.txt> <out_prefix> <n_prompt>
// env:   RG_BACKEND=cuda|vulkan (default cuda), RG_DUTY=0|1 (1: after each token sleep for that token's own measured decode time), RG_NCTX (default 12288),
//        RG_DEVICE_MATCH=<substring> (case-insensitive): load the model on the first GPU/IGPU device of the backend whose ggml description contains it (device ORDER is not stable
//        across shells/processes, so an index is never used); FATAL naming the available descriptions if nothing matches. EXEC_MODE prints the device actually used.
// Flow:  load model (every layer offloaded, right backend in the load log, else abort), prefill n_prompt tokens, print EXEC_MODE and READY, read "GO <t_stop_qpc_s>" on stdin
//        (QPC seconds = time.perf_counter on Windows), decode greedily until t_stop. When the context is full: llama_memory_clear, re-prefill n_prompt tokens, continue;
//        every reset is a row of kind=reset (time, duration) and its time is not decode time. Writes <out_prefix>_tokens.csv: t_tok_end_s,dur_ms,kind.
// The driver sets no process/thread priority and does not touch any clock (no timeBeginPeriod).
#include <windows.h>
#include <algorithm>
#include <cstdio>
#include <cstdlib>
#include <cctype>
#include <cstring>
#include <fstream>
#include <sstream>
#include <string>
#include <vector>
#include "llama.h"
#include "ggml-backend.h"

static std::string g_log;
static void log_cb(ggml_log_level, const char *text, void *) { g_log += text; }

static double qpc_now() {
    static LARGE_INTEGER f = [] { LARGE_INTEGER x; QueryPerformanceFrequency(&x); return x; }();
    LARGE_INTEGER c; QueryPerformanceCounter(&c);
    return (double)c.QuadPart / (double)f.QuadPart;
}

#ifndef CREATE_WAITABLE_TIMER_HIGH_RESOLUTION
#define CREATE_WAITABLE_TIMER_HIGH_RESOLUTION 0x00000002
#endif
// DUTY50 sleep: a high-resolution waitable timer (no global timer-resolution change). If the OS lacks it (CreateWaitableTimerExW fails) the fallback is spin + Sleep(1).
static HANDLE g_hr_timer = CreateWaitableTimerExW(nullptr, nullptr, CREATE_WAITABLE_TIMER_HIGH_RESOLUTION, TIMER_ALL_ACCESS);

// block until qpc_now() >= until (QPC seconds)
static void sleep_until_qpc(double until) {
    for (;;) {
        double rem = until - qpc_now();
        if (rem <= 0) return;
        if (g_hr_timer) {
            if (rem > 1.0e-3) {                              // wait for all but the last ~0.7 ms on the timer, spin the rest (timer wake-up jitter)
                LARGE_INTEGER due; due.QuadPart = -(LONGLONG)((rem - 0.7e-3) * 1.0e7);
                if (SetWaitableTimer(g_hr_timer, &due, 0, nullptr, nullptr, FALSE)) { WaitForSingleObject(g_hr_timer, INFINITE); continue; }
            }
        } else if (rem > 1.5e-3) Sleep(1);                   // fallback: Sleep(1) until 1.5 ms remain, then spin
    }
}

static int die(const char *msg) { fprintf(stderr, "FATAL %s\n", msg); return 2; }

static std::string lower(std::string s) { for (char &ch : s) ch = (char)tolower((unsigned char)ch); return s; }

// GPU / IGPU devices of the registry whose registry name starts with the backend's prefix ("Vulkan" or "CUDA"), in registry order
static std::vector<ggml_backend_dev_t> backend_gpu_devices(bool vk) {
    std::vector<ggml_backend_dev_t> out;
    for (size_t i = 0; i < ggml_backend_dev_count(); i++) {
        ggml_backend_dev_t d = ggml_backend_dev_get(i);
        enum ggml_backend_dev_type ty = ggml_backend_dev_type(d);
        if (ty != GGML_BACKEND_DEVICE_TYPE_GPU && ty != GGML_BACKEND_DEVICE_TYPE_IGPU) continue;
        if (std::string(ggml_backend_dev_name(d)).rfind(vk ? "Vulkan" : "CUDA", 0) == 0) out.push_back(d);
    }
    return out;
}

// prefill the tokens in chunks of at most n_batch; returns false on failure
static bool prefill(llama_context *ctx, std::vector<llama_token> &toks, int n_batch) {
    for (int i = 0; i < (int)toks.size(); i += n_batch) {
        int c = (std::min)(n_batch, (int)toks.size() - i);
        if (llama_decode(ctx, llama_batch_get_one(toks.data() + i, c)) != 0) return false;
    }
    return true;
}

int main(int argc, char **argv) {
    if (argc < 5) return die("usage: model prompt out_prefix n_prompt");
    const char *model_path = argv[1], *prompt_path = argv[2];
    const std::string prefix = argv[3];
    const int n_prompt = atoi(argv[4]);
    const char *eb = getenv("RG_BACKEND"), *ed = getenv("RG_DUTY"), *en = getenv("RG_NCTX");
    const std::string backend = eb ? eb : "cuda";
    if (backend != "cuda" && backend != "vulkan") return die("RG_BACKEND must be cuda or vulkan");
    const bool vk = backend == "vulkan";
    const int duty = ed ? atoi(ed) : 0;
    if (duty != 0 && duty != 1) return die("RG_DUTY must be 0 or 1");
    const int n_ctx = en ? atoi(en) : 12288;
    if (n_prompt <= 0 || n_ctx <= n_prompt + 2) return die("need 0 < n_prompt and n_ctx > n_prompt + 2");

    llama_log_set(log_cb, nullptr);
    llama_backend_init();
    if (!llama_supports_gpu_offload()) return die("this llama.cpp build has no GPU offload (CPU build)");
    llama_model_params mp = llama_model_default_params();
    mp.n_gpu_layers = 999;
    const char *edm = getenv("RG_DEVICE_MATCH");
    const std::string match = edm ? lower(edm) : "";
    ggml_backend_dev_t chosen = nullptr;
    ggml_backend_dev_t dev_list[2] = {nullptr, nullptr};          // NULL-terminated list for llama_model_params.devices
    if (!match.empty()) {
        std::string avail;
        for (ggml_backend_dev_t d : backend_gpu_devices(vk)) {
            std::string desc = ggml_backend_dev_description(d);
            avail += (avail.empty() ? "'" : ", '") + desc + "'";
            if (!chosen && lower(desc).find(match) != std::string::npos) chosen = d;
        }
        if (!chosen) {
            std::string msg = std::string("RG_DEVICE_MATCH '") + edm + "' matches no " + backend + " device; available: " + (avail.empty() ? "(none)" : avail);
            return die(msg.c_str());
        }
        dev_list[0] = chosen;
        mp.devices = dev_list;
        mp.split_mode = LLAMA_SPLIT_MODE_NONE;
        mp.main_gpu = 0;
    }
    llama_model *model = llama_model_load_from_file(model_path, mp);
    if (!model) return die("model load failed");
    const int n_layer = llama_model_n_layer(model);
    int off = -1, tot = -1;
    size_t p = g_log.find("offloaded ");
    if (p != std::string::npos) sscanf(g_log.c_str() + p, "offloaded %d/%d layers", &off, &tot);
    if (g_log.find(vk ? "Vulkan" : "CUDA") == std::string::npos) return die(vk ? "no Vulkan device in the load log" : "no CUDA device in the load log");
    if (off < 0 || off != tot) return die("not all layers offloaded to the GPU");
    // device name from the ggml device registry: first GPU device whose registry name starts with the requested backend
    // with RG_DEVICE_MATCH: the selected device (the one the model was loaded on); without it the old behaviour (the first registry device of the backend)
    std::string devname;
    if (chosen) devname = ggml_backend_dev_description(chosen);
    else { std::vector<ggml_backend_dev_t> all = backend_gpu_devices(vk); if (!all.empty()) devname = ggml_backend_dev_description(all[0]); }
    if (devname.empty()) return die("no GPU device of the requested backend in the ggml device registry");
    printf("EXEC_MODE %s device=%s offloaded=%d/%d n_layer=%d duty=%d\n", backend.c_str(), devname.c_str(), off, tot, n_layer, duty);

    llama_context_params cp = llama_context_default_params();
    cp.n_ctx = (uint32_t)n_ctx; cp.n_batch = 512; cp.no_perf = true;
    llama_context *ctx = llama_init_from_model(model, cp);
    if (!ctx) return die("context creation failed");
    const llama_vocab *vocab = llama_model_get_vocab(model);
    std::ifstream f(prompt_path, std::ios::binary); std::stringstream ss; ss << f.rdbuf(); std::string text = ss.str();
    if (text.empty()) return die("empty prompt file");
    std::vector<llama_token> toks(text.size() + 8);
    int n = llama_tokenize(vocab, text.c_str(), (int32_t)text.size(), toks.data(), (int32_t)toks.size(), true, false);
    if (n < n_prompt) return die("prompt file has fewer tokens than n_prompt");
    toks.resize(n_prompt);
    if (!prefill(ctx, toks, (int)cp.n_batch)) return die("prefill failed");
    llama_sampler *smpl = llama_sampler_chain_init(llama_sampler_chain_default_params());
    llama_sampler_chain_add(smpl, llama_sampler_init_greedy());
    llama_token cur = llama_sampler_sample(smpl, ctx, -1);   // first token from the prefill logits (untimed)
    int n_past = n_prompt;                                   // tokens in the KV cache

    printf("READY\n"); fflush(stdout);
    char line[128] = {0};
    if (!fgets(line, sizeof line, stdin)) return die("no GO line on stdin");
    double t_stop = 0; if (sscanf(line, "GO %lf", &t_stop) != 1) return die("expected 'GO <t_stop_qpc_s>'");

    struct Row { double t_end, dur_ms; bool reset; };
    std::vector<Row> rows; rows.reserve(1 << 16);
    size_t n_tok = 0, n_reset = 0;
    double sum_decode = 0, sum_sleep = 0;
    while (qpc_now() < t_stop) {
        if (n_past + 1 >= n_ctx) {                           // context full: clear and re-prefill (not decode time)
            double r0 = qpc_now();
            llama_memory_clear(llama_get_memory(ctx), true);
            if (!prefill(ctx, toks, (int)cp.n_batch)) return die("re-prefill after reset failed");
            cur = llama_sampler_sample(smpl, ctx, -1);
            n_past = n_prompt;
            double r1 = qpc_now();
            rows.push_back({r1, (r1 - r0) * 1e3, true}); n_reset++;
            continue;
        }
        double t0 = qpc_now();
        if (llama_decode(ctx, llama_batch_get_one(&cur, 1)) != 0) return die("decode failed");
        cur = llama_sampler_sample(smpl, ctx, -1);           // reads logits: synchronises with the GPU
        double t1 = qpc_now();
        n_past++;
        rows.push_back({t1, (t1 - t0) * 1e3, false}); n_tok++;
        sum_decode += t1 - t0;
        if (duty) {                                          // sleep for this token's own decode time (high-resolution waitable timer, else spin + Sleep(1))
            sleep_until_qpc(t1 + (t1 - t0));
            sum_sleep += qpc_now() - t1;
        }
    }
    FILE *o = fopen((prefix + "_tokens.csv").c_str(), "w");
    if (!o) return die("cannot open output");
    fprintf(o, "t_tok_end_s,dur_ms,kind\n");
    for (const Row &r : rows) fprintf(o, "%.9f,%.6f,%s\n", r.t_end, r.dur_ms, r.reset ? "reset" : "token");
    fclose(o);
    printf("DONE tokens=%zu resets=%zu\n", n_tok, n_reset);
    if (duty) printf("DUTY_ACHIEVED %.4f decode_s=%.6f sleep_s=%.6f\n", sum_decode + sum_sleep > 0 ? sum_decode / (sum_decode + sum_sleep) : 0.0, sum_decode, sum_sleep);
    llama_sampler_free(smpl); llama_free(ctx); llama_model_free(model); llama_backend_free();
    return 0;
}
