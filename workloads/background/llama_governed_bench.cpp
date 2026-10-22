// Governed greedy decode driver (W4-5): llama_decode_bench.cpp plus governor-controlled pacing through shared memory. The original driver stays untouched so the W2 L results
// remain reproducible. Same GPU-only guards: every layer must be offloaded to a CUDA device or the program aborts (no CPU fallback), and EXEC_MODE is printed.
// usage: llama_governed_bench <model.gguf> <prompt.txt> <out.csv> <t_sync_qpc_s> <t_stop_qpc_s> <n_prompt> <ctrl_block> <pace_block> <token_ring> <ring_capacity>
//   t_sync < 0: start right after prefill and run for t_stop seconds (standalone use).
//   ctrl_block (governor -> driver, 3 doubles): [pacing (0 unaligned duty, 1 aligned slack filling), duty, guard_ms]
//   pace_block (fg -> driver, 3 doubles): [fg_busy (0/1), t_next_arrival_s, t_updated_s]; older than 100 ms = the fg is idle -> the background runs free
//   token_ring (driver -> daemon, 1 double per token): QPC end time of each token (seconds)
// Pacing decisions are the shared pure functions in pacing.h (mirror of sim/pacing.py): unaligned = gap of measured_token_time * (1/duty - 1) after each token;
// aligned = start a token only while no fg frame is busy and now + token_estimate + guard <= next fg arrival AND the duty gap since the previous token has passed (duty 1 = no gap; used as the power-budget throttle).
#include <windows.h>
#include <intrin.h>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <limits>
#include <sstream>
#include <string>
#include <vector>
#include "llama.h"
#include "pacing.h"
#include "shm.h"

static std::string g_log;
static void log_cb(ggml_log_level, const char *text, void *) { g_log += text; }

static double qpc_now() {
    static LARGE_INTEGER f = [] { LARGE_INTEGER x; QueryPerformanceFrequency(&x); return x; }();
    LARGE_INTEGER c; QueryPerformanceCounter(&c);
    return (double)c.QuadPart / (double)f.QuadPart;
}

static int die(const char *msg) { fprintf(stderr, "FATAL %s\n", msg); return 2; }

static void sleep_until_ms(double t_ms) {                       // coarse Sleep(1) far from the target, spin for the last 2 ms
    for (;;) {
        double rem = t_ms - qpc_now() * 1000.0;
        if (rem <= 0) return;
        if (rem > 3.0) Sleep(1); else YieldProcessor();
    }
}

int main(int argc, char **argv) {
    if (argc < 11) return die("usage: model prompt out t_sync t_stop n_prompt ctrl_block pace_block token_ring ring_capacity");
    const char *model_path = argv[1], *prompt_path = argv[2], *out_path = argv[3];
    double t_sync = atof(argv[4]), t_stop = atof(argv[5]);
    const int n_prompt = atoi(argv[6]);
    shm::Block ctrl, pace; shm::Ring ring;
    if (!ctrl.open(argv[7], 3) || !pace.open(argv[8], 3)) return die("cannot open the control / pace shared memory (the governor creates them first)");
    if (!ring.open(argv[9], (uint64_t)atoll(argv[10]), 1)) return die("cannot open the token ring");

    llama_log_set(log_cb, nullptr);
    llama_backend_init();
    if (!llama_supports_gpu_offload()) return die("this llama.cpp build has no GPU offload (CPU build)");
    llama_model_params mp = llama_model_default_params();
    mp.n_gpu_layers = 999;
    llama_model *model = llama_model_load_from_file(model_path, mp);
    if (!model) return die("model load failed");
    const int n_layer = llama_model_n_layer(model);
    int off = -1, tot = -1;
    size_t p = g_log.find("offloaded ");
    if (p != std::string::npos) sscanf(g_log.c_str() + p, "offloaded %d/%d layers", &off, &tot);
    if (g_log.find("CUDA") == std::string::npos) return die("no CUDA device in the load log");
    if (off < 0 || off != tot) return die("not all layers offloaded to the GPU");
    printf("EXEC_MODE cuda offloaded=%d/%d n_layer=%d model_size=%llu governed=1\n", off, tot, n_layer, (unsigned long long)llama_model_size(model));

    llama_context_params cp = llama_context_default_params();
    cp.n_ctx = 2048; cp.n_batch = 512; cp.no_perf = true;
    llama_context *ctx = llama_init_from_model(model, cp);
    if (!ctx) return die("context creation failed");
    const llama_vocab *vocab = llama_model_get_vocab(model);

    std::ifstream f(prompt_path, std::ios::binary); std::stringstream ss; ss << f.rdbuf(); std::string text = ss.str();
    if (text.empty()) return die("empty prompt file");
    std::vector<llama_token> toks(text.size() + 8);
    int n = llama_tokenize(vocab, text.c_str(), (int32_t)text.size(), toks.data(), (int32_t)toks.size(), true, false);
    if (n < n_prompt) return die("prompt file has fewer tokens than n_prompt");
    toks.resize(n_prompt);
    if (llama_decode(ctx, llama_batch_get_one(toks.data(), (int32_t)toks.size())) != 0) return die("prefill failed");

    llama_sampler *smpl = llama_sampler_chain_init(llama_sampler_chain_default_params());
    llama_sampler_chain_add(smpl, llama_sampler_init_greedy());
    llama_token cur = llama_sampler_sample(smpl, ctx, -1);
    std::vector<double> te; std::vector<llama_token> ids; te.reserve(1 << 18); ids.reserve(1 << 18);
    if (t_sync < 0) { t_stop = qpc_now() + t_stop; t_sync = 0; }
    while (qpc_now() < t_sync) Sleep(1);

    // the governor must have written a control block within 10 s of the start, otherwise decoding would run unpaced against a deadline task
    double c[3] = {0, 0, 0}, pc[3] = {0, 0, 0};
    double t_wait0 = qpc_now();
    while (!ctrl.read(c)) {
        if (qpc_now() - t_wait0 > 10.0) return die("no control block written by the governor within 10 s");
        Sleep(5);
    }
    double tok_est_ms = 0.0, wake_ms = 0.0;
    bool have_est = false;
    const double inf = std::numeric_limits<double>::infinity();
    while (qpc_now() < t_stop && (int)ids.size() + n_prompt + 2 < (int)cp.n_ctx) {
        ctrl.read(c);
        if (c[0] >= 0.5) {                                        // aligned: wait for slack
            for (;;) {
                double now_s = qpc_now();
                if (now_s >= t_stop) break;
                ctrl.read(c);
                if (c[0] < 0.5) break;                            // the governor switched to duty pacing
                bool busy = false; double next_ms = inf;
                if (pace.read(pc) && now_s - pc[2] <= 0.1) { busy = pc[0] != 0.0; next_ms = pc[1] * 1000.0; }
                if (c[1] > 0.0 && now_s * 1000.0 >= wake_ms && pacing::aligned_may_start(now_s * 1000.0, busy, have_est ? tok_est_ms : 0.0, c[2], next_ms)) break;     // aligned also honours the duty gap (power budget throttle)
                YieldProcessor();
            }
        } else {                                                  // unaligned duty cycle
            while (qpc_now() < t_stop) {
                ctrl.read(c);
                if (c[0] >= 0.5) break;
                if (c[1] <= 0.0) { Sleep(5); continue; }          // duty 0: paused until the governor raises it
                if (qpc_now() * 1000.0 >= wake_ms) break;
                sleep_until_ms(wake_ms < qpc_now() * 1000.0 + 5.0 ? wake_ms : qpc_now() * 1000.0 + 5.0);
            }
        }
        if (qpc_now() >= t_stop) break;
        double t0 = qpc_now();
        if (llama_decode(ctx, llama_batch_get_one(&cur, 1)) != 0) return die("decode failed");
        cur = llama_sampler_sample(smpl, ctx, -1);                // reads logits: synchronises with the GPU
        double t1 = qpc_now();
        te.push_back(t1); ids.push_back(cur);
        ring.push(&t1);
        double tok_ms = (t1 - t0) * 1000.0;
        tok_est_ms = have_est ? 0.9 * tok_est_ms + 0.1 * tok_ms : tok_ms;
        have_est = true;
        ctrl.read(c);
        wake_ms = pacing::unaligned_wake(t0 * 1000.0, t1 * 1000.0, c[1]);
    }
    FILE *o = fopen(out_path, "w");
    if (!o) return die("cannot open output");
    fprintf(o, "t_tok_end,token\n");
    for (size_t i = 0; i < te.size(); i++) fprintf(o, "%.9f,%d\n", te[i], (int)ids[i]);
    fclose(o);
    printf("DONE tokens=%zu t_first=%.6f t_last=%.6f ctx_end=%d\n", te.size(), te.empty() ? 0.0 : te.front(), te.empty() ? 0.0 : te.back(), n_prompt + (int)ids.size());
    llama_sampler_free(smpl); llama_free(ctx); llama_model_free(model); llama_backend_free();
    return 0;
}
