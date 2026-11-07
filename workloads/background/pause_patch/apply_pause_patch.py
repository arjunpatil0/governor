import re, sys
from pathlib import Path
root = Path(sys.argv[1])
cu = root / "ggml/src/ggml-cuda/ggml-cuda.cu"
h = root / "ggml/include/ggml-cuda.h"
s = open(cu, encoding="utf-8", newline="").read()
nl = "\r\n" if "\r\n" in s else "\n"
s = s.replace("\r\n", "\n")
old = "static enum ggml_status ggml_backend_cuda_graph_compute(ggml_backend_t backend, ggml_cgraph * cgraph) {"
assert s.count(old) == 1
s = s.replace(old, "static enum ggml_status ggml_backend_cuda_graph_compute_whole(ggml_backend_t backend, ggml_cgraph * cgraph) {")
marker = "static void ggml_backend_cuda_event_record(ggml_backend_t backend, ggml_backend_event_t event) {"
assert s.count(marker) == 1
wrapper = r'''// ---- v2 pause-cost experiment (docs/V2_SPRINT1_PAUSE_COST.md) -------------------------------------------------------------------------------
// GGML_CUDA_PAUSE_GROUPS=G (G > 1) splits one token's compute graph into G groups of layers (cut after the node named l_out-<layer>), runs each group through the
// unchanged capture / launch path (each group has its own first node, so its own CUDA graph), synchronises the stream after each group and calls a host hook with the
// group's host launch time, host completion time (both seconds on the steady clock) and its GPU time between two CUDA events. Unset or 1 = stock behaviour, untouched.
static ggml_backend_cuda_group_hook_t g_pause_hook = nullptr;
static void * g_pause_hook_user = nullptr;

void ggml_backend_cuda_set_group_hook(ggml_backend_cuda_group_hook_t hook, void * user) {
    g_pause_hook = hook;
    g_pause_hook_user = user;
}

static double ggml_cuda_pause_now_s() {
    return std::chrono::duration<double>(std::chrono::steady_clock::now().time_since_epoch()).count();
}

static enum ggml_status ggml_backend_cuda_graph_compute(ggml_backend_t backend, ggml_cgraph * cgraph) {
    static const int n_groups_req = [] { const char * e = getenv("GGML_CUDA_PAUSE_GROUPS"); return e ? atoi(e) : 1; }();
    if (n_groups_req <= 1) {
        return ggml_backend_cuda_graph_compute_whole(backend, cgraph);
    }
    std::vector<int> ends;                                   // index of the last node of each layer
    for (int i = 0; i < cgraph->n_nodes; i++) {
        if (strncmp(cgraph->nodes[i]->name, "l_out-", 6) == 0) {
            ends.push_back(i);
        }
    }
    const int n_layers = (int) ends.size();
    if (n_layers < n_groups_req) {                           // a split without the layer stack (or fewer layers than groups): run whole
        return ggml_backend_cuda_graph_compute_whole(backend, cgraph);
    }
    ggml_backend_cuda_context * cuda_ctx = (ggml_backend_cuda_context *) backend->context;
    ggml_cuda_set_device(cuda_ctx->device);
    static cudaEvent_t ev0 = nullptr, ev1 = nullptr;
    if (ev0 == nullptr) {
        CUDA_CHECK(cudaEventCreate(&ev0));
        CUDA_CHECK(cudaEventCreate(&ev1));
    }
    int start = 0;
    for (int g = 0; g < n_groups_req; g++) {
        const int end = (g == n_groups_req - 1) ? cgraph->n_nodes - 1 : ends[(g + 1) * n_layers / n_groups_req - 1];
        ggml_cgraph view = *cgraph;                              // same fields as ggml_graph_view (not exported from ggml-base.dll): a view of nodes [start, end]
        view.size = 0; view.n_nodes = end + 1 - start; view.n_leafs = 0; view.nodes = cgraph->nodes + start;
        view.grads = nullptr; view.grad_accs = nullptr; view.leafs = nullptr; view.uid = 0;
        const double t_launch = ggml_cuda_pause_now_s();
        CUDA_CHECK(cudaEventRecord(ev0, cuda_ctx->stream()));
        const enum ggml_status st = ggml_backend_cuda_graph_compute_whole(backend, &view);
        CUDA_CHECK(cudaEventRecord(ev1, cuda_ctx->stream()));
        CUDA_CHECK(cudaStreamSynchronize(cuda_ctx->stream()));   // the pause point: the GPU is idle for us from here until the next group is launched
        const double t_done = ggml_cuda_pause_now_s();
        float gpu_ms = 0.0f;
        CUDA_CHECK(cudaEventElapsedTime(&gpu_ms, ev0, ev1));
        if (g_pause_hook != nullptr) {
            g_pause_hook(g, n_groups_req, t_launch, t_done, gpu_ms, g_pause_hook_user);
        }
        if (st != GGML_STATUS_SUCCESS) {
            return st;
        }
        start = end + 1;
    }
    return GGML_STATUS_SUCCESS;
}

'''
s = s.replace("#include <vector>", "#include <vector>\n#include <chrono>\n#include <cstring>", 1)
s = s.replace(marker, wrapper + marker)
open(cu, "w", encoding="utf-8", newline="").write(s.replace("\n", nl))
t = open(h, encoding="utf-8", newline="").read()
nl2 = "\r\n" if "\r\n" in t else "\n"; t = t.replace("\r\n", "\n")
decl = "GGML_BACKEND_API ggml_backend_t ggml_backend_cuda_init(int device);"
assert t.count(decl) == 1
t = t.replace(decl, '''// v2 pause-cost experiment: hook called after each layer group when GGML_CUDA_PAUSE_GROUPS > 1 (see ggml-cuda.cu)
typedef void (*ggml_backend_cuda_group_hook_t)(int group, int n_groups, double t_launch_s, double t_done_s, float gpu_ms, void * user);
GGML_BACKEND_API void ggml_backend_cuda_set_group_hook(ggml_backend_cuda_group_hook_t hook, void * user);

''' + decl)
open(h, "w", encoding="utf-8", newline="").write(t.replace("\n", nl2))
print("patched", cu, h)
