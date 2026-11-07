// v2 sprint 1 (docs/V2_SPRINT1_PAUSE_COST.md): greedy decode with per-group timing for the layer-group split of the PATCHED llama.cpp (third_party/llama.cpp_v2).
// usage: llama_pause_bench <model.gguf> <prompt.txt> <out_prefix> <n_prompt> <n_tokens> <n_warm>
// The number of groups G is taken from the environment (GGML_CUDA_PAUSE_GROUPS, read by the patched ggml-cuda; unset or 1 = whole-token graph; GGML_CUDA_DISABLE_GRAPHS=1 = graphs off).
// Every layer must be offloaded (no CPU fallback). Prefill n_prompt tokens (untimed), then decode n_warm + n_tokens tokens one at a time. For each token the wall time of
// llama_decode + greedy sample (the sample reads the logits and so synchronises) is recorded; with G > 1 the group hook records per group the host launch time, the host completion time
// (after the stream synchronise), the GPU time between two CUDA events, and the cost of one frame-hint check done at the pause point (a seqlock read of a local shared-memory record,
// the protocol of docs/FRAME_HINT_SPEC.md, here always "app idle"). Writes <out_prefix>_tokens.csv and <out_prefix>_groups.csv. The v1 driver llama_decode_bench.cpp is not touched.
#include <windows.h>
#include <cstdint>
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

struct GroupRec { int token, group; double t_launch, t_done; float gpu_ms; double hint_us; };
static std::vector<GroupRec> g_groups;
static int g_token = 0;
static volatile uint64_t *g_hint = nullptr;      // local frame-hint record (40 bytes): the hook reads it like a worker would at a pause point

static int read_hint(double out[3]) {            // seqlock read, docs/FRAME_HINT_SPEC.md section 5
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

static void group_hook(int group, int, double t_launch, double t_done, float gpu_ms, void *) {
    const double a = qpc_now();
    double v[3] = {0, 0, 0}; int ok = read_hint(v);
    volatile int sink = ok + (int)v[0]; (void)sink;
    const double b = qpc_now();
    g_groups.push_back({g_token, group, t_launch, t_done, gpu_ms, (b - a) * 1e6});
}

typedef void (*hook_fn)(int, int, double, double, float, void *);
typedef void (*set_hook_fn)(hook_fn, void *);

int main(int argc, char **argv) {
    if (argc < 7) return die("usage: model prompt out_prefix n_prompt n_tokens n_warm");
    const char *model_path = argv[1], *prompt_path = argv[2];
    const std::string prefix = argv[3];
    const int n_prompt = atoi(argv[4]), n_tokens = atoi(argv[5]), n_warm = atoi(argv[6]);

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
    const char *ge = getenv("GGML_CUDA_PAUSE_GROUPS");
    const char *gd = getenv("GGML_CUDA_DISABLE_GRAPHS");
    printf("EXEC_MODE cuda offloaded=%d/%d n_layer=%d groups=%s graphs_disabled=%s\n", off, tot, llama_model_n_layer(model), ge ? ge : "1", gd ? gd : "0");

    HMODULE m = GetModuleHandleA("ggml-cuda.dll");
    if (!m) m = LoadLibraryA("ggml-cuda.dll");
    set_hook_fn set_hook = m ? (set_hook_fn)GetProcAddress(m, "ggml_backend_cuda_set_group_hook") : nullptr;
    const bool want_groups = ge && atoi(ge) > 1;
    if (want_groups && !set_hook) return die("GGML_CUDA_PAUSE_GROUPS > 1 but ggml-cuda.dll does not export ggml_backend_cuda_set_group_hook (not the patched build)");
    HANDLE hm = CreateFileMappingA(INVALID_HANDLE_VALUE, NULL, PAGE_READWRITE, 0, 40, NULL);
    g_hint = (volatile uint64_t *)MapViewOfFile(hm, FILE_MAP_ALL_ACCESS, 0, 0, 40);
    { double v[3] = {0.0, 1e300, qpc_now()}; g_hint[1] = 3; memcpy((unsigned char *)g_hint + 16, v, 24); g_hint[0] = 2; }   // published once: not busy, next deadline far away
    if (want_groups) set_hook(group_hook, nullptr);

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
    if (n_prompt + n_warm + n_tokens + 2 >= (int)cp.n_ctx) return die("n_prompt + n_warm + n_tokens exceeds the context");
    g_token = -1;                                                  // the prefill's groups (if the split applies to it) are recorded under token -1 and ignored
    if (llama_decode(ctx, llama_batch_get_one(toks.data(), (int32_t)toks.size())) != 0) return die("prefill failed");
    llama_sampler *smpl = llama_sampler_chain_init(llama_sampler_chain_default_params());
    llama_sampler_chain_add(smpl, llama_sampler_init_greedy());
    llama_token cur = llama_sampler_sample(smpl, ctx, -1);

    std::vector<double> tot_ms; std::vector<llama_token> ids;
    for (int i = 0; i < n_warm + n_tokens; i++) {
        g_token = i;
        const double t0 = qpc_now();
        if (llama_decode(ctx, llama_batch_get_one(&cur, 1)) != 0) return die("decode failed");
        cur = llama_sampler_sample(smpl, ctx, -1);                 // reads logits: synchronises with the GPU
        tot_ms.push_back((qpc_now() - t0) * 1e3); ids.push_back(cur);
    }
    FILE *o = fopen((prefix + "_tokens.csv").c_str(), "w");
    if (!o) return die("cannot open tokens output");
    fprintf(o, "token,warm,total_ms,token_id\n");
    for (size_t i = 0; i < tot_ms.size(); i++) fprintf(o, "%zu,%d,%.6f,%d\n", i, (int)i < n_warm, tot_ms[i], (int)ids[i]);
    fclose(o);
    o = fopen((prefix + "_groups.csv").c_str(), "w");
    if (!o) return die("cannot open groups output");
    fprintf(o, "token,group,t_launch_s,t_done_s,gpu_ms,hint_check_us\n");
    for (const GroupRec &r : g_groups) if (r.token >= 0) fprintf(o, "%d,%d,%.9f,%.9f,%.6f,%.3f\n", r.token, r.group, r.t_launch, r.t_done, (double)r.gpu_ms, r.hint_us);
    fclose(o);
    printf("DONE tokens=%zu group_records=%zu\n", tot_ms.size(), g_groups.size());
    llama_sampler_free(smpl); llama_free(ctx); llama_model_free(model); llama_backend_free();
    return 0;
}
