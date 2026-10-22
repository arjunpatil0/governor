// w2_kernels.cu - W2 co-location workloads, built as a DLL and driven from Python (ctypes).
//   bg slices : back-to-back launch+sync of fma (units = loop iterations) or mem (units = 64 KiB chunks) slices, each timestamped
//   fg frames : requests released at absolute QPC times, latency measured from the SCHEDULED arrival by the caller
//   decode    : transformer-shaped decode proxy (Llama-3.2-3B shapes: hidden 3072, ffn 8192, 24 heads / 8 kv heads, head_dim 128),
//               8 kernel launches per layer, fp16 or int4(group 32) weights, optional CUDA-graph capture per token
// Build: build.bat w2_kernels.cu build\w2_kernels.dll -shared   (always -arch=sm_89; no CPU fallback: init fails if CUDA is absent)
// All times are QueryPerformanceCounter seconds = Python time.perf_counter() on Windows, so two processes share one timeline.
// Softmax in attn_decode has no max-subtraction: the synthetic scores are small and bounded; timing is unaffected.
#include <windows.h>
#include <cuda_fp16.h>
#include <cuda_runtime.h>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <vector>

#define EXPORT extern "C" __declspec(dllexport)

static char g_err[512] = "";
#define CK(x)                                                                          \
    do {                                                                               \
        cudaError_t e_ = (x);                                                          \
        if (e_ != cudaSuccess) {                                                       \
            snprintf(g_err, sizeof g_err, "%s:%d %s", __FILE__, __LINE__,              \
                     cudaGetErrorString(e_));                                          \
            return 1;                                                                  \
        }                                                                              \
    } while (0)

static double qpc_now()
{
    static LARGE_INTEGER f = [] { LARGE_INTEGER x; QueryPerformanceFrequency(&x); return x; }();
    LARGE_INTEGER c; QueryPerformanceCounter(&c);
    return (double)c.QuadPart / (double)f.QuadPart;
}

// ------------------------------------------------------------------ synthetic kernels (same bodies as bench_kernels.cu)
static const size_t kArrayBytes = 256ull << 20;
static const size_t kN4 = kArrayBytes / sizeof(float4);
static const int kThreads = 256;
static float4 *dA = nullptr, *dB = nullptr;
static float* dOut = nullptr;
static int g_sms = 0;
static cudaStream_t g_s = nullptr;
static cudaEvent_t e0, e1;

__global__ void stream_kernel(const float4* __restrict__ a, float4* __restrict__ b, size_t n4, float s)
{
    size_t i = blockIdx.x * (size_t)blockDim.x + threadIdx.x;
    size_t stride = (size_t)gridDim.x * blockDim.x;
    for (; i < n4; i += stride) {
        float4 v = a[i];
        v.x = v.x * s + 1.f; v.y = v.y * s + 1.f; v.z = v.z * s + 1.f; v.w = v.w * s + 1.f;
        b[i] = v;
    }
}

__global__ void fma_kernel(float* out, int iters, float a, float b)
{
    float x0 = threadIdx.x * 1e-3f, x1 = x0 + 1e-3f, x2 = x0 + 2e-3f, x3 = x0 + 3e-3f;
    float x4 = x0 + 4e-3f, x5 = x0 + 5e-3f, x6 = x0 + 6e-3f, x7 = x0 + 7e-3f;
    for (int i = 0; i < iters; ++i) {
        x0 = fmaf(x0, a, b); x1 = fmaf(x1, a, b); x2 = fmaf(x2, a, b); x3 = fmaf(x3, a, b);
        x4 = fmaf(x4, a, b); x5 = fmaf(x5, a, b); x6 = fmaf(x6, a, b); x7 = fmaf(x7, a, b);
    }
    out[blockIdx.x * blockDim.x + threadIdx.x] = x0 + x1 + x2 + x3 + x4 + x5 + x6 + x7;
}

// ---- Experiment G instrumentation (experiments/w2_colocation_addendum_globaltimer_2026-10-22.md). A separate kernel, so the
// uninstrumented fma_kernel above is byte-for-byte what A, A2, B and C ran. Per thread block: %globaltimer at start and end, %smid, and a
// gap detector: lane 0 of every warp reads %globaltimer every kGapStride loop iterations and keeps the largest gap between consecutive
// reads (and where it began); the block keeps the largest over its warps. A block descheduled mid-execution shows up as a large gap.
static int g_gap_stride = 64;      // power of two; runtime-settable (w2_set_gap_stride) so the pre-check can measure the cost of the reads
// Rec: t0/t1 = earliest warp start / latest warp end; tg0 = thread 0's own start (the origin of the logged gap offsets); gmax/gbeg = largest
// gap; ngaps = gaps stored in the gap list, novf = gaps over the per-block limit K (counted, not stored); nreads = gap reads by thread 0.
struct Rec { unsigned long long t0, t1, tg0, gmax, gbeg; unsigned int smid, tag, blk, nreads, ngaps, novf; };
struct GapEnt { unsigned int rec_idx, off, len; };   // off = gap start - tg0 (ns), len = gap length (ns)

__device__ __forceinline__ unsigned long long gtimer_ns()
{
    unsigned long long t;
    asm volatile("mov.u64 %0, %%globaltimer;" : "=l"(t));
    return t;
}
__device__ __forceinline__ unsigned int smid_now()
{
    unsigned int s;
    asm volatile("mov.u32 %0, %%smid;" : "=r"(s));
    return s;
}

// Log one gap (start `st`, length `ln`) of thread 0's block: stored while the block has fewer than gap_k, else counted in novf; a full global list also counts as novf.
#define LOG_GAP(st, ln)                                                                                              \
    do {                                                                                                             \
        if (ngaps < (unsigned int)gap_k) {                                                                           \
            unsigned int gi_ = atomicAdd(gcount, 1u);                                                                \
            if (gi_ < gcap) { GapEnt ge_; ge_.rec_idx = rec_base + blockIdx.x; ge_.off = (unsigned int)((st) - t0);   \
                              ge_.len = (unsigned int)(ln); glist[gi_] = ge_; ++ngaps; }                              \
            else ++novf;                                                                                             \
        } else ++novf;                                                                                               \
    } while (0)

__global__ void fma_kernel_rec(float* out, int iters, float a, float b, Rec* rec, unsigned int tag, int stride_mask,
                               GapEnt* glist, unsigned int* gcount, unsigned int gcap, unsigned int rec_base, int gap_k, unsigned int log_thr)
{
    __shared__ unsigned long long s_gmax[kThreads / 32], s_gbeg[kThreads / 32], s_t0[kThreads / 32], s_t1[kThreads / 32];
    const unsigned long long t0 = gtimer_ns();
    const bool lane0 = (threadIdx.x & 31) == 0;
    unsigned long long last = t0, gmax = 0, gbeg = t0;
    unsigned int nreads = 0, ngaps = 0, novf = 0;
    float x0 = threadIdx.x * 1e-3f, x1 = x0 + 1e-3f, x2 = x0 + 2e-3f, x3 = x0 + 3e-3f;
    float x4 = x0 + 4e-3f, x5 = x0 + 5e-3f, x6 = x0 + 6e-3f, x7 = x0 + 7e-3f;
    // chunked loop: the FMA body stays branch-free (a branch inside it costs ~1.6x by breaking the scheduling of the 8 chains); %globaltimer
    // is read between chunks of `stride` iterations, then once more after the remainder.
    const int stride = stride_mask + 1;
    int done = 0;
    while (done + stride <= iters) {
        for (int j = 0; j < stride; ++j) {
            x0 = fmaf(x0, a, b); x1 = fmaf(x1, a, b); x2 = fmaf(x2, a, b); x3 = fmaf(x3, a, b);
            x4 = fmaf(x4, a, b); x5 = fmaf(x5, a, b); x6 = fmaf(x6, a, b); x7 = fmaf(x7, a, b);
        }
        done += stride;
        if (lane0) {
            ++nreads;
            unsigned long long t = gtimer_ns(), g = t - last;
            if (g > gmax) { gmax = g; gbeg = last; }
            if (threadIdx.x == 0 && g > log_thr) LOG_GAP(last, g);
            last = t;
        }
    }
    for (; done < iters; ++done) {
        x0 = fmaf(x0, a, b); x1 = fmaf(x1, a, b); x2 = fmaf(x2, a, b); x3 = fmaf(x3, a, b);
        x4 = fmaf(x4, a, b); x5 = fmaf(x5, a, b); x6 = fmaf(x6, a, b); x7 = fmaf(x7, a, b);
    }
    out[blockIdx.x * blockDim.x + threadIdx.x] = x0 + x1 + x2 + x3 + x4 + x5 + x6 + x7;
    if (lane0) {
        unsigned long long t = gtimer_ns(), g = t - last;
        if (g > gmax) { gmax = g; gbeg = last; }
        if (threadIdx.x == 0 && g > log_thr) LOG_GAP(last, g);
        s_gmax[threadIdx.x >> 5] = gmax; s_gbeg[threadIdx.x >> 5] = gbeg; s_t0[threadIdx.x >> 5] = t0; s_t1[threadIdx.x >> 5] = t;
    }
    __syncthreads();
    if (threadIdx.x == 0) {
        // block start = earliest warp start, block end = latest warp end (warps of a block do not start at the same instant)
        unsigned long long m = 0, mb = s_t0[0], b0 = s_t0[0], b1 = s_t1[0];
        for (int w = 0; w < kThreads / 32; ++w) {
            if (s_gmax[w] > m) { m = s_gmax[w]; mb = s_gbeg[w]; }
            if (s_t0[w] < b0) b0 = s_t0[w];
            if (s_t1[w] > b1) b1 = s_t1[w];
        }
        Rec r;
        r.t0 = b0; r.t1 = b1; r.tg0 = t0; r.ngaps = ngaps; r.novf = novf; r.gmax = m; r.gbeg = mb; r.smid = smid_now(); r.tag = tag; r.blk = blockIdx.x; r.nreads = nreads + 1;   // gap reads by thread 0 (loop reads + the final one)
        rec[blockIdx.x] = r;
    }
}

static Rec* dRec = nullptr;
static GapEnt* dGap = nullptr;
static unsigned int* dGapCount = nullptr;
static size_t g_rec_cap = 0, g_rec_used = 0, g_rec_dropped = 0, g_gap_cap = 0;
static int g_gap_k = 8;                        // per-block gap limit for the current recording call
static unsigned int g_log_thr_ns = 20000;     // logging threshold (addendum 2: 20 us)
static cudaStream_t g_s2 = nullptr;

__global__ void gt_read_loop(unsigned long long* out, int n) { for (int i = 0; i < n; ++i) out[i] = gtimer_ns(); }
__global__ void gt_read_once(unsigned long long* out) { *out = gtimer_ns(); }

// Reserve record space for one launch of `blocks` blocks; nullptr (and a count) when the buffer is full or recording is off.
static Rec* rec_take(int blocks)
{
    if (!dRec) return nullptr;
    if (g_rec_used + (size_t)blocks > g_rec_cap) { ++g_rec_dropped; return nullptr; }
    Rec* r = dRec + g_rec_used;
    g_rec_used += (size_t)blocks;
    return r;
}

static int launch_unit(int kind, int units, int blocks, Rec* rec = nullptr, unsigned int tag = 0, cudaStream_t st = nullptr)
{
    if (!st) st = g_s;
    if (kind == 1 && rec) fma_kernel_rec<<<blocks, kThreads, 0, st>>>(dOut, units, 0.9999f, 1e-4f, rec, tag, g_gap_stride - 1, dGap, dGapCount, (unsigned int)g_gap_cap,
                                                     (unsigned int)(rec - dRec), g_gap_k, g_log_thr_ns);
    else if (kind == 1) fma_kernel<<<blocks, kThreads, 0, st>>>(dOut, units, 0.9999f, 1e-4f);
    else {   // mem: units = chunks of 4096 float4 (64 KiB read + 64 KiB written); one full pass = kN4/4096 = 4096 chunks
        const int per_pass = (int)(kN4 / 4096);
        for (int left = units; left > 0; left -= per_pass)
            stream_kernel<<<g_sms * 16, kThreads, 0, g_s>>>(dA, dB, (size_t)(left < per_pass ? left : per_pass) * 4096, 1.0f);
    }
    CK(cudaGetLastError());
    return 0;
}

EXPORT const char* w2_last_error() { return g_err; }
EXPORT double w2_qpc_now() { return qpc_now(); }

// Spin-wait sync (lowest wake-up latency); the flag must be set before the context is created.
EXPORT int w2_init(int* sm_count)
{
    int n = 0;
    CK(cudaGetDeviceCount(&n));
    if (n < 1) { snprintf(g_err, sizeof g_err, "no CUDA device"); return 1; }
    CK(cudaSetDeviceFlags(cudaDeviceScheduleSpin));
    cudaDeviceProp p;
    CK(cudaGetDeviceProperties(&p, 0));
    g_sms = p.multiProcessorCount;
    *sm_count = g_sms;
    CK(cudaStreamCreateWithFlags(&g_s, cudaStreamNonBlocking));
    CK(cudaEventCreate(&e0));
    CK(cudaEventCreate(&e1));
    CK(cudaMalloc(&dA, kArrayBytes));
    CK(cudaMalloc(&dB, kArrayBytes));
    CK(cudaMalloc(&dOut, (size_t)g_sms * 64 * kThreads * sizeof(float)));
    CK(cudaMemset(dA, 0x3F, kArrayBytes));
    CK(cudaMemset(dB, 0, kArrayBytes));
    return 0;
}

static int bg_loop(int kind, const int* units, int n_units, int blocks_per_sm, double t_stop,
                   double* t_start, double* t_end, double* gpu_ms, int cap, int* n_done, double duty, bool rec, double t_rec0)
{
    if (!(duty > 0.0 && duty <= 1.0)) { snprintf(g_err, sizeof g_err, "duty must be in (0,1], got %g", duty); return 2; }
    int i = 0;
    while (i < cap && qpc_now() < t_stop) {
        t_start[i] = qpc_now();
        CK(cudaEventRecord(e0, g_s));
        Rec* rb = (rec && t_start[i] >= t_rec0) ? rec_take(g_sms * blocks_per_sm) : nullptr;
        if (launch_unit(kind, units[i % n_units], g_sms * blocks_per_sm, rb, (unsigned int)i)) return 1;
        CK(cudaEventRecord(e1, g_s));
        CK(cudaEventSynchronize(e1));
        t_end[i] = qpc_now();
        float ms = 0;
        CK(cudaEventElapsedTime(&ms, e0, e1));
        gpu_ms[i] = ms;
        if (duty < 1.0) {   // idle gap (CPU spin, GPU idle) so that busy / (busy + idle) = duty
            double until = t_end[i] + (t_end[i] - t_start[i]) * (1.0 / duty - 1.0);
            while (qpc_now() < until) { YieldProcessor(); }
        }
        ++i;
    }
    *n_done = i;
    return 0;
}

// Background: launch+sync slices back to back until QPC time t_stop. units[] is cycled. Per slice: host start (just before
// launch), host end (just after sync), CUDA-event gpu ms. kind 0 = mem (units = 64 KiB chunks, see launch_unit), 1 = fma (units = iterations;
// blocks = SMs * blocks_per_sm). duty in (0,1]: after each slice spin-wait so busy/(busy+idle) = duty. Slices done are returned in *n_done (<= cap).
EXPORT int w2_bg_until(int kind, const int* units, int n_units, int blocks_per_sm, double t_stop,
                       double* t_start, double* t_end, double* gpu_ms, int cap, int* n_done, double duty)
{
    return bg_loop(kind, units, n_units, blocks_per_sm, t_stop, t_start, t_end, gpu_ms, cap, n_done, duty, false, 0.0);
}

// Same, with the instrumented fma kernel for slices that START at or after t_rec0 (QPC) while the record buffer (w2_rec_init) has room;
// later slices run the plain kernel and are counted in w2_rec_dropped(). fma only (kind 1).
EXPORT int w2_bg_until_rec(int kind, const int* units, int n_units, int blocks_per_sm, double t_stop,
                           double* t_start, double* t_end, double* gpu_ms, int cap, int* n_done, double duty, double t_rec0, int gap_k)
{
    g_gap_k = gap_k;
    if (kind != 1) { snprintf(g_err, sizeof g_err, "recording supports the fma kernel only"); return 4; }
    return bg_loop(kind, units, n_units, blocks_per_sm, t_stop, t_start, t_end, gpu_ms, cap, n_done, duty, true, t_rec0);
}

static int fg_loop(int kind, int n, const double* arrivals, int units, int blocks_per_sm,
                   double* t_launch, double* t_complete, double* gpu_ms, bool rec, int rec_from)
{
    for (int i = 0; i < n; ++i) {
        while (qpc_now() < arrivals[i]) { YieldProcessor(); }
        t_launch[i] = qpc_now();
        CK(cudaEventRecord(e0, g_s));
        Rec* rb = (rec && i >= rec_from) ? rec_take(g_sms * blocks_per_sm) : nullptr;
        if (launch_unit(kind, units, g_sms * blocks_per_sm, rb, (unsigned int)i)) return 1;
        CK(cudaEventRecord(e1, g_s));
        CK(cudaEventSynchronize(e1));
        t_complete[i] = qpc_now();
        float ms = 0;
        CK(cudaEventElapsedTime(&ms, e0, e1));
        gpu_ms[i] = ms;
    }
    return 0;
}

// Foreground: request i is released at absolute QPC time arrivals[i] (busy-wait), launched, synced.
// t_launch = host time just before launch, t_complete = host time just after sync. Latency = t_complete - arrivals[i]
// (computed by the caller from the SCHEDULED arrival). A request whose arrival has already passed is launched at once.
EXPORT int w2_fg_run(int kind, int n, const double* arrivals, int units, int blocks_per_sm,
                     double* t_launch, double* t_complete, double* gpu_ms)
{
    return fg_loop(kind, n, arrivals, units, blocks_per_sm, t_launch, t_complete, gpu_ms, false, 0);
}

// Same, recording requests with index >= rec_from (fma only).
EXPORT int w2_fg_run_rec(int kind, int n, const double* arrivals, int units, int blocks_per_sm,
                         double* t_launch, double* t_complete, double* gpu_ms, int rec_from, int gap_k)
{
    g_gap_k = gap_k;
    if (kind != 1) { snprintf(g_err, sizeof g_err, "recording supports the fma kernel only"); return 4; }
    return fg_loop(kind, n, arrivals, units, blocks_per_sm, t_launch, t_complete, gpu_ms, true, rec_from);
}

// ---- record buffer and %globaltimer probes (Experiment G pre-checks)
EXPORT int w2_rec_init(size_t cap_blocks, size_t gap_cap)
{
    if (dRec) { CK(cudaFree(dRec)); dRec = nullptr; }
    if (dGap) { CK(cudaFree(dGap)); dGap = nullptr; }
    if (dGapCount) { CK(cudaFree(dGapCount)); dGapCount = nullptr; }
    CK(cudaMalloc(&dRec, cap_blocks * sizeof(Rec)));
    CK(cudaMalloc(&dGap, gap_cap * sizeof(GapEnt)));
    CK(cudaMalloc(&dGapCount, sizeof(unsigned int)));
    CK(cudaMemset(dGapCount, 0, sizeof(unsigned int)));
    g_rec_cap = cap_blocks; g_rec_used = 0; g_rec_dropped = 0; g_gap_cap = gap_cap;
    return 0;
}
EXPORT int w2_set_log_thr(unsigned int ns) { g_log_thr_ns = ns; return 0; }
// Number of gaps the kernels tried to store (more than the list capacity means some were lost; they are counted in the blocks' novf).
EXPORT size_t w2_gap_count()
{
    unsigned int c = 0;
    if (!dGapCount || cudaDeviceSynchronize() != cudaSuccess || cudaMemcpy(&c, dGapCount, sizeof c, cudaMemcpyDeviceToHost) != cudaSuccess) return 0;
    return c;
}
EXPORT int w2_gap_fetch(unsigned int* rec_idx, unsigned int* off, unsigned int* len)
{
    CK(cudaDeviceSynchronize());
    size_t n = w2_gap_count();
    if (n > g_gap_cap) n = g_gap_cap;
    std::vector<GapEnt> h(n);
    if (n) CK(cudaMemcpy(h.data(), dGap, n * sizeof(GapEnt), cudaMemcpyDeviceToHost));
    for (size_t i = 0; i < n; ++i) { rec_idx[i] = h[i].rec_idx; off[i] = h[i].off; len[i] = h[i].len; }
    return 0;
}
EXPORT int w2_set_gap_stride(int stride)
{
    if (stride < 1 || (stride & (stride - 1))) { snprintf(g_err, sizeof g_err, "gap stride must be a power of two, got %d", stride); return 2; }
    g_gap_stride = stride;
    return 0;
}
EXPORT size_t w2_rec_used() { return g_rec_used; }
EXPORT size_t w2_rec_dropped() { return g_rec_dropped; }
EXPORT int w2_rec_fetch(unsigned long long* t0, unsigned long long* t1, unsigned long long* tg0, unsigned long long* gmax, unsigned long long* gbeg,
                        unsigned int* smid, unsigned int* tag, unsigned int* blk, unsigned int* nreads, unsigned int* ngaps, unsigned int* novf)
{
    CK(cudaDeviceSynchronize());
    std::vector<Rec> h(g_rec_used);
    if (g_rec_used) CK(cudaMemcpy(h.data(), dRec, g_rec_used * sizeof(Rec), cudaMemcpyDeviceToHost));
    for (size_t i = 0; i < h.size(); ++i) {
        t0[i] = h[i].t0; t1[i] = h[i].t1; tg0[i] = h[i].tg0; ngaps[i] = h[i].ngaps; novf[i] = h[i].novf; gmax[i] = h[i].gmax; gbeg[i] = h[i].gbeg; smid[i] = h[i].smid; tag[i] = h[i].tag; blk[i] = h[i].blk; nreads[i] = h[i].nreads;
    }
    return 0;
}

// n consecutive %globaltimer reads by a single thread (pre-check i: timer resolution).
EXPORT int w2_gt_resolution(int n, unsigned long long* out)
{
    unsigned long long* d = nullptr;
    CK(cudaMalloc(&d, (size_t)n * 8));
    gt_read_loop<<<1, 1, 0, g_s>>>(d, n);
    CK(cudaGetLastError());
    CK(cudaStreamSynchronize(g_s));
    CK(cudaMemcpy(out, d, (size_t)n * 8, cudaMemcpyDeviceToHost));
    CK(cudaFree(d));
    return 0;
}

// n host/GPU timer sample pairs: QPC just before the launch, QPC just after the sync, %globaltimer read inside the kernel (pre-check ii).
EXPORT int w2_gt_sync(int n, double* qpc_before, double* qpc_after, unsigned long long* gt)
{
    unsigned long long* d = nullptr;
    CK(cudaMalloc(&d, 8));
    for (int i = 0; i < n; ++i) {
        qpc_before[i] = qpc_now();
        gt_read_once<<<1, 1, 0, g_s>>>(d);
        CK(cudaStreamSynchronize(g_s));
        qpc_after[i] = qpc_now();
        CK(cudaMemcpy(&gt[i], d, 8, cudaMemcpyDeviceToHost));
    }
    CK(cudaFree(d));
    return 0;
}

// Single-process, two-stream test of the shared timebase (pre-check ii): a recording kernel A (tag 0) on the bg stream, then, after
// delay_s of host time, a recording kernel B (tag 1) on a second stream. times = {a_launch, a_done, b_launch, b_done} (QPC).
// Requires w2_rec_init with room for two launches.
EXPORT int w2_two_streams_rec(int units_a, int units_b, double delay_s, double* times)
{
    if (!dRec) { snprintf(g_err, sizeof g_err, "w2_rec_init first"); return 5; }
    if (!g_s2) CK(cudaStreamCreateWithFlags(&g_s2, cudaStreamNonBlocking));
    const int blocks = g_sms * 6;
    Rec* ra = rec_take(blocks);
    Rec* rb = rec_take(blocks);
    if (!ra || !rb) { snprintf(g_err, sizeof g_err, "record buffer too small"); return 6; }
    times[0] = qpc_now();
    if (launch_unit(1, units_a, blocks, ra, 0, g_s)) return 1;
    double until = qpc_now() + delay_s;
    while (qpc_now() < until) { YieldProcessor(); }
    times[2] = qpc_now();
    if (launch_unit(1, units_b, blocks, rb, 1, g_s2)) return 1;
    CK(cudaStreamSynchronize(g_s2));
    times[3] = qpc_now();
    CK(cudaStreamSynchronize(g_s));
    times[1] = qpc_now();
    return 0;
}

EXPORT int w2_free()
{
    if (dA) CK(cudaFree(dA));
    if (dB) CK(cudaFree(dB));
    if (dOut) CK(cudaFree(dOut));
    if (dRec) CK(cudaFree(dRec));
    if (dGap) CK(cudaFree(dGap));
    if (dGapCount) CK(cudaFree(dGapCount));
    dA = dB = nullptr; dOut = nullptr; dRec = nullptr; dGap = nullptr; dGapCount = nullptr; g_rec_cap = g_rec_used = g_rec_dropped = g_gap_cap = 0;
    return 0;
}

// ------------------------------------------------------------------ decode proxy
static const int HID = 3072, FFN = 8192, NH = 24, NKV = 8, HD = 128, QKV_N = HID + 2 * NKV * HD;  // 5120
enum { V_FP16 = 0, V_Q4 = 1 };

struct Layer { void *wqkv, *wo, *wgu, *wd; __half *sqkv, *so, *sgu, *sd; __half *kc, *vc; };
static std::vector<Layer> g_layers;
static int g_variant = 0, g_ctx = 512;
static __half *dx, *dxn, *dqkv, *dattn, *dgu, *dact;
static cudaStream_t g_ds = nullptr;
static cudaGraphExec_t g_gexec = nullptr;

__global__ void fill_half(__half* p, size_t n, uint32_t seed, float amp)
{
    for (size_t i = blockIdx.x * (size_t)blockDim.x + threadIdx.x; i < n; i += (size_t)gridDim.x * blockDim.x) {
        uint32_t h = (uint32_t)i * 2654435761u ^ seed; h ^= h >> 15; h *= 2246822519u; h ^= h >> 13;
        p[i] = __float2half(((h & 0xFFFF) / 65535.f - 0.5f) * 2.f * amp);
    }
}
__global__ void fill_u32(uint32_t* p, size_t n, uint32_t seed)
{
    for (size_t i = blockIdx.x * (size_t)blockDim.x + threadIdx.x; i < n; i += (size_t)gridDim.x * blockDim.x) {
        uint32_t h = (uint32_t)i * 2654435761u ^ seed; h ^= h >> 15; h *= 2246822519u; h ^= h >> 13; p[i] = h;
    }
}

// y[row] = W[row,:] . x (+ resid). One warp per row; fp16 weights, 16 B per lane per step.
__global__ void gemv_f16(const uint4* __restrict__ W, const __half* __restrict__ x, __half* __restrict__ y, int N, int K,
                         const __half* __restrict__ resid)
{
    int row = (blockIdx.x * blockDim.x + threadIdx.x) >> 5, lane = threadIdx.x & 31;
    if (row >= N) return;
    const uint4* w = W + (size_t)row * (K / 8);
    float acc = 0.f;
    for (int i = lane; i < K / 8; i += 32) {
        uint4 v = w[i];
        const __half2* h = (const __half2*)&v;
        const __half2* xv = (const __half2*)(x + i * 8);
#pragma unroll
        for (int j = 0; j < 4; ++j) { float2 a = __half22float2(h[j]), b = __half22float2(xv[j]); acc += a.x * b.x + a.y * b.y; }
    }
    for (int o = 16; o; o >>= 1) acc += __shfl_xor_sync(0xffffffffu, acc, o);
    if (lane == 0) y[row] = __float2half(acc + (resid ? __half2float(resid[row]) : 0.f));
}

// int4, group size 32: one 16 B load = 32 weights = one scale. Dequantise (nibble-8)*scale, then fma with x.
__global__ void gemv_q4(const uint4* __restrict__ W, const __half* __restrict__ S, const __half* __restrict__ x,
                        __half* __restrict__ y, int N, int K, const __half* __restrict__ resid)
{
    int row = (blockIdx.x * blockDim.x + threadIdx.x) >> 5, lane = threadIdx.x & 31;
    if (row >= N) return;
    const uint4* w = W + (size_t)row * (K / 32);
    const __half* s = S + (size_t)row * (K / 32);
    float acc = 0.f;
    for (int g = lane; g < K / 32; g += 32) {
        uint4 v = w[g];
        float sc = __half2float(s[g]);
        const uint32_t* words = (const uint32_t*)&v;
        const __half2* xv = (const __half2*)(x + g * 32);
        float a = 0.f;
#pragma unroll
        for (int q = 0; q < 4; ++q) {
            uint32_t u = words[q];
#pragma unroll
            for (int k = 0; k < 4; ++k) {     // two nibbles per half2 of x
                float2 xx = __half22float2(xv[q * 4 + k]);
                a += (float)((int)((u >> (8 * k)) & 0xF) - 8) * xx.x + (float)((int)((u >> (8 * k + 4)) & 0xF) - 8) * xx.y;
            }
        }
        acc += a * sc;
    }
    for (int o = 16; o; o >>= 1) acc += __shfl_xor_sync(0xffffffffu, acc, o);
    if (lane == 0) y[row] = __float2half(acc + (resid ? __half2float(resid[row]) : 0.f));
}

__global__ void rmsnorm(const __half* __restrict__ x, __half* __restrict__ out, int n)
{
    __shared__ float red[32];
    float ss = 0.f;
    for (int i = threadIdx.x; i < n; i += blockDim.x) { float v = __half2float(x[i]); ss += v * v; }
    for (int o = 16; o; o >>= 1) ss += __shfl_xor_sync(0xffffffffu, ss, o);
    if ((threadIdx.x & 31) == 0) red[threadIdx.x >> 5] = ss;
    __syncthreads();
    if (threadIdx.x < 32) {
        float t = threadIdx.x < (blockDim.x >> 5) ? red[threadIdx.x] : 0.f;
        for (int o = 16; o; o >>= 1) t += __shfl_xor_sync(0xffffffffu, t, o);
        if (threadIdx.x == 0) red[0] = rsqrtf(t / n + 1e-5f);
    }
    __syncthreads();
    float r = red[0];
    for (int i = threadIdx.x; i < n; i += blockDim.x) out[i] = __float2half(__half2float(x[i]) * r);
}

// One block (128 threads) per query head: scores over `ctx` cached positions (ctx multiple of 128), softmax, weighted V sum.
__global__ void attn_decode(const __half* __restrict__ qkv, const __half* __restrict__ kc, const __half* __restrict__ vc,
                            __half* __restrict__ out, int ctx)
{
    extern __shared__ float sc[];
    __shared__ float red;
    int h = blockIdx.x, kvh = h / (NH / NKV);
    const __half* q = qkv + h * HD;
    const __half* K = kc + (size_t)kvh * ctx * HD;
    const __half* V = vc + (size_t)kvh * ctx * HD;
    float sum = 0.f;
    for (int p = threadIdx.x; p < ctx; p += blockDim.x) {
        float d = 0.f;
        for (int j = 0; j < HD; j += 2) {
            float2 a = __half22float2(*(const __half2*)(K + (size_t)p * HD + j)), b = __half22float2(*(const __half2*)(q + j));
            d += a.x * b.x + a.y * b.y;
        }
        float e = __expf(d * 0.08838834764f);   // 1/sqrt(128)
        sc[p] = e; sum += e;
    }
    for (int o = 16; o; o >>= 1) sum += __shfl_xor_sync(0xffffffffu, sum, o);
    if (threadIdx.x == 0) red = 0.f;
    __syncthreads();
    if ((threadIdx.x & 31) == 0) atomicAdd(&red, sum);
    __syncthreads();
    float inv = 1.f / red;
    float acc = 0.f;
    for (int p = 0; p < ctx; ++p) acc += sc[p] * __half2float(V[(size_t)p * HD + threadIdx.x]);
    out[h * HD + threadIdx.x] = __float2half(acc * inv);
}

__global__ void silu_mul(const __half* __restrict__ gu, __half* __restrict__ out, int n)
{
    int i = blockIdx.x * blockDim.x + threadIdx.x;
    if (i < n) { float g = __half2float(gu[i]), u = __half2float(gu[n + i]); out[i] = __float2half(g / (1.f + __expf(-g)) * u); }
}

static void gemv(void* W, __half* S, const __half* x, __half* y, int N, int K, const __half* resid)
{
    int blocks = (N * 32 + 255) / 256;
    if (g_variant == V_FP16) gemv_f16<<<blocks, 256, 0, g_ds>>>((const uint4*)W, x, y, N, K, resid);
    else gemv_q4<<<blocks, 256, 0, g_ds>>>((const uint4*)W, S, x, y, N, K, resid);
}

// One token: norm, qkv, attn, o+resid, norm, gate/up, silu_mul, down+resid = 8 launches per layer.
static void enqueue_token()
{
    for (const Layer& L : g_layers) {
        rmsnorm<<<1, 1024, 0, g_ds>>>(dx, dxn, HID);
        gemv(L.wqkv, L.sqkv, dxn, dqkv, QKV_N, HID, nullptr);
        attn_decode<<<NH, 128, g_ctx * sizeof(float), g_ds>>>(dqkv, L.kc, L.vc, dattn, g_ctx);
        gemv(L.wo, L.so, dattn, dx, HID, HID, dx);
        rmsnorm<<<1, 1024, 0, g_ds>>>(dx, dxn, HID);
        gemv(L.wgu, L.sgu, dxn, dgu, 2 * FFN, HID, nullptr);
        silu_mul<<<(FFN + 255) / 256, 256, 0, g_ds>>>(dgu, dact, FFN);
        gemv(L.wd, L.sd, dact, dx, HID, FFN, dx);
    }
}

static size_t wbytes(int N, int K) { return g_variant == V_FP16 ? (size_t)N * K * 2 : (size_t)N * K / 2; }

// variant 0 = fp16, 1 = int4. layers: how many of the 28 layers to instantiate (fp16 x 28 = 5.6 GB, so the caller chooses and
// logs it; never silently reduced). ctx must be a multiple of 128. *bytes_per_token = weights + KV cache read per token.
EXPORT int w2_decode_init(int variant, int layers, int ctx, double* bytes_per_token)
{
    if (ctx % 128 != 0) { snprintf(g_err, sizeof g_err, "ctx must be a multiple of 128"); return 2; }
    g_variant = variant; g_ctx = ctx;
    size_t need = 0;
    int dims[4][2] = {{QKV_N, HID}, {HID, HID}, {2 * FFN, HID}, {HID, FFN}};
    for (auto& d : dims) need += wbytes(d[0], d[1]);
    need = need * layers + (size_t)layers * 2 * NKV * ctx * HD * 2;
    size_t fr = 0, tot = 0;
    CK(cudaMemGetInfo(&fr, &tot));
    if (need + (256ull << 20) > fr) { snprintf(g_err, sizeof g_err, "need %zu MiB, free %zu MiB", need >> 20, fr >> 20); return 3; }
    CK(cudaStreamCreateWithFlags(&g_ds, cudaStreamNonBlocking));
    CK(cudaMalloc(&dx, HID * 2)); CK(cudaMalloc(&dxn, HID * 2)); CK(cudaMalloc(&dqkv, QKV_N * 2));
    CK(cudaMalloc(&dattn, HID * 2)); CK(cudaMalloc(&dgu, 2 * FFN * 2)); CK(cudaMalloc(&dact, FFN * 2));
    fill_half<<<8, 256>>>(dx, HID, 1, 0.5f);
    for (int l = 0; l < layers; ++l) {
        Layer L{};
        void** ws[4] = {&L.wqkv, &L.wo, &L.wgu, &L.wd};
        __half** ss[4] = {&L.sqkv, &L.so, &L.sgu, &L.sd};
        for (int i = 0; i < 4; ++i) {
            size_t b = wbytes(dims[i][0], dims[i][1]);
            CK(cudaMalloc(ws[i], b));
            if (variant == V_FP16) fill_half<<<g_sms * 8, 256>>>((__half*)*ws[i], b / 2, 100 + l * 8 + i, 0.02f);
            else {
                fill_u32<<<g_sms * 8, 256>>>((uint32_t*)*ws[i], b / 4, 100 + l * 8 + i);
                size_t ns = (size_t)dims[i][0] * dims[i][1] / 32;
                CK(cudaMalloc(ss[i], ns * 2));
                fill_half<<<g_sms * 8, 256>>>(*ss[i], ns, 7 + i, 0.004f);
            }
        }
        size_t kv = (size_t)NKV * ctx * HD;
        CK(cudaMalloc(&L.kc, kv * 2)); CK(cudaMalloc(&L.vc, kv * 2));
        fill_half<<<g_sms * 8, 256>>>(L.kc, kv, 11 + l, 0.5f);
        fill_half<<<g_sms * 8, 256>>>(L.vc, kv, 13 + l, 0.5f);
        g_layers.push_back(L);
    }
    CK(cudaGetLastError());
    CK(cudaDeviceSynchronize());
    *bytes_per_token = (double)need;
    return 0;
}

// Runs tokens (one host sync per token) until QPC t_stop and records each token's host end time. use_graph: capture one
// token's kernels once and replay with cudaGraphLaunch. Tokens done are returned in *n_done (<= cap).
EXPORT int w2_decode_run(int use_graph, double t_stop, double* t_tok_end, int cap, int* n_done)
{
    if (use_graph && !g_gexec) {
        cudaGraph_t g;
        CK(cudaStreamBeginCapture(g_ds, cudaStreamCaptureModeGlobal));
        enqueue_token();
        CK(cudaStreamEndCapture(g_ds, &g));
        CK(cudaGraphInstantiate(&g_gexec, g, 0));
        CK(cudaGraphDestroy(g));
    }
    int i = 0;
    while (i < cap && qpc_now() < t_stop) {
        if (use_graph) CK(cudaGraphLaunch(g_gexec, g_ds)); else enqueue_token();
        CK(cudaGetLastError());
        CK(cudaStreamSynchronize(g_ds));
        t_tok_end[i++] = qpc_now();
    }
    *n_done = i;
    return 0;
}

// Finite-ness check of the residual stream (NaN/Inf would not change timing but would mean the proxy is broken).
EXPORT int w2_decode_state_finite(int* finite)
{
    std::vector<__half> h(HID);
    CK(cudaMemcpy(h.data(), dx, HID * 2, cudaMemcpyDeviceToHost));
    *finite = 1;
    for (auto v : h) if (!std::isfinite(__half2float(v))) { *finite = 0; break; }
    return 0;
}

EXPORT int w2_decode_free()
{
    CK(cudaDeviceSynchronize());
    if (g_gexec) { CK(cudaGraphExecDestroy(g_gexec)); g_gexec = nullptr; }
    for (Layer& L : g_layers) {
        cudaFree(L.wqkv); cudaFree(L.wo); cudaFree(L.wgu); cudaFree(L.wd);
        if (L.sqkv) { cudaFree(L.sqkv); cudaFree(L.so); cudaFree(L.sgu); cudaFree(L.sd); }
        cudaFree(L.kc); cudaFree(L.vc);
    }
    g_layers.clear();
    cudaFree(dx); cudaFree(dxn); cudaFree(dqkv); cudaFree(dattn); cudaFree(dgu); cudaFree(dact);
    return 0;
}
