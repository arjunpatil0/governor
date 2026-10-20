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

static int launch_unit(int kind, int units, int blocks)
{
    if (kind == 1) fma_kernel<<<blocks, kThreads, 0, g_s>>>(dOut, units, 0.9999f, 1e-4f);
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

// Background: launch+sync slices back to back until QPC time t_stop. units[] is cycled. Per slice: host start (just before
// launch), host end (just after sync), CUDA-event gpu ms. kind 0 = mem (units = 64 KiB chunks, see launch_unit), 1 = fma (units = iterations;
// blocks = SMs * blocks_per_sm). duty in (0,1]: after each slice spin-wait so busy/(busy+idle) = duty. Slices done are returned in *n_done (<= cap).
EXPORT int w2_bg_until(int kind, const int* units, int n_units, int blocks_per_sm, double t_stop,
                       double* t_start, double* t_end, double* gpu_ms, int cap, int* n_done, double duty)
{
    if (!(duty > 0.0 && duty <= 1.0)) { snprintf(g_err, sizeof g_err, "duty must be in (0,1], got %g", duty); return 2; }
    int i = 0;
    while (i < cap && qpc_now() < t_stop) {
        t_start[i] = qpc_now();
        CK(cudaEventRecord(e0, g_s));
        if (launch_unit(kind, units[i % n_units], g_sms * blocks_per_sm)) return 1;
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

// Foreground: request i is released at absolute QPC time arrivals[i] (busy-wait), launched, synced.
// t_launch = host time just before launch, t_complete = host time just after sync. Latency = t_complete - arrivals[i]
// (computed by the caller from the SCHEDULED arrival). A request whose arrival has already passed is launched at once.
EXPORT int w2_fg_run(int kind, int n, const double* arrivals, int units, int blocks_per_sm,
                     double* t_launch, double* t_complete, double* gpu_ms)
{
    for (int i = 0; i < n; ++i) {
        while (qpc_now() < arrivals[i]) { YieldProcessor(); }
        t_launch[i] = qpc_now();
        CK(cudaEventRecord(e0, g_s));
        if (launch_unit(kind, units, g_sms * blocks_per_sm)) return 1;
        CK(cudaEventRecord(e1, g_s));
        CK(cudaEventSynchronize(e1));
        t_complete[i] = qpc_now();
        float ms = 0;
        CK(cudaEventElapsedTime(&ms, e0, e1));
        gpu_ms[i] = ms;
    }
    return 0;
}

EXPORT int w2_free()
{
    if (dA) CK(cudaFree(dA));
    if (dB) CK(cudaFree(dB));
    if (dOut) CK(cudaFree(dOut));
    dA = dB = nullptr; dOut = nullptr;
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
