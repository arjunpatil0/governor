// Greedy decode driver for the W2 llama.cpp validation (experiments/w2_colocation_addendum_llamacpp_2026-10-21.md).
// usage: llama_decode_bench <model.gguf> <prompt.txt> <out.csv> <t_sync_qpc_s> <t_stop_qpc_s> [n_prompt=512]
// Loads the model with every layer on the GPU (aborts otherwise), prefills the first n_prompt tokens of the prompt file (untimed),
// waits for t_sync on the QPC timeline (same clock as time.perf_counter), then decodes one token at a time until t_stop and
// writes "t_tok_end,token" per token. No CPU fallback: any layer left off the GPU is a fatal error.
#include <windows.h>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
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

int main(int argc, char **argv) {
    if (argc < 6) return die("usage: model prompt out t_sync t_stop [n_prompt]");
    const char *model_path = argv[1], *prompt_path = argv[2], *out_path = argv[3];
    double t_sync = atof(argv[4]), t_stop = atof(argv[5]);   // t_sync < 0: start right after prefill and run for t_stop seconds (standalone/sanity use)
    const int n_prompt = argc > 6 ? atoi(argv[6]) : 512;

    llama_log_set(log_cb, nullptr);
    llama_backend_init();
    if (!llama_supports_gpu_offload()) return die("this llama.cpp build has no GPU offload (CPU build)");
    llama_model_params mp = llama_model_default_params();
    mp.n_gpu_layers = 999;
    llama_model *model = llama_model_load_from_file(model_path, mp);
    if (!model) return die("model load failed");
    const int n_layer = llama_model_n_layer(model);
    // execution-mode check: ggml logs "offloaded N/M layers to GPU"; require N == M and a CUDA device
    int off = -1, tot = -1;
    size_t p = g_log.find("offloaded ");
    if (p != std::string::npos) sscanf(g_log.c_str() + p, "offloaded %d/%d layers", &off, &tot);
    if (g_log.find("CUDA") == std::string::npos) return die("no CUDA device in the load log");
    if (off < 0 || off != tot) return die("not all layers offloaded to the GPU");
    printf("EXEC_MODE cuda offloaded=%d/%d n_layer=%d model_size=%llu\n", off, tot, n_layer, (unsigned long long)llama_model_size(model));

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
    llama_token cur = llama_sampler_sample(smpl, ctx, -1);        // first token comes from the prefill logits (untimed)
    std::vector<double> te; std::vector<llama_token> ids; te.reserve(1 << 18); ids.reserve(1 << 18);
    if (t_sync < 0) { t_stop = qpc_now() + t_stop; t_sync = 0; }
    while (qpc_now() < t_sync) Sleep(1);
    while (qpc_now() < t_stop && (int)ids.size() + n_prompt + 2 < (int)cp.n_ctx) {
        if (llama_decode(ctx, llama_batch_get_one(&cur, 1)) != 0) return die("decode failed");
        cur = llama_sampler_sample(smpl, ctx, -1);                // reads logits: synchronises with the GPU
        te.push_back(qpc_now()); ids.push_back(cur);
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
