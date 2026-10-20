// bench_kernels.cu - two calibration kernels for the W1 downclock experiment.
//   mem: float4 streaming copy-scale over two 256 MiB arrays (>> L2)  -> work in GB moved
//   fma: 8 independent fmaf chains per thread                          -> work in GFLOP
// Built as a DLL and driven from Python (ctypes) so NVML energy reads bracket each call.
// Build: build.bat bench_kernels.cu build\bench_kernels.dll -shared
// Every CUDA call is checked; failure returns nonzero and bench_last_error() says why.
// There is no CPU fallback: if CUDA is unavailable, bench_init fails.
#include <chrono>
#include <cmath>
#include <cstdio>
#include <cuda_runtime.h>

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

static const size_t kArrayBytes = 256ull << 20;          // per array
static const size_t kN4 = kArrayBytes / sizeof(float4);
static const int kMemLaunchesPerChunk = 20;
static const int kFmaIters = 1 << 20;
static const int kFmaChainsPerThread = 8;
static const int kThreads = 256;

static float4 *dA = nullptr, *dB = nullptr;
static float* dOut = nullptr;
static int g_sms = 0, g_fmaBlocks = 0, g_memBlocks = 0;
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

EXPORT const char* bench_last_error() { return g_err; }

EXPORT int bench_init(int* sm_count)
{
    int n = 0;
    CK(cudaGetDeviceCount(&n));
    if (n < 1) { snprintf(g_err, sizeof g_err, "no CUDA device"); return 1; }
    cudaDeviceProp p;
    CK(cudaGetDeviceProperties(&p, 0));
    g_sms = p.multiProcessorCount;
    g_fmaBlocks = g_sms * 6;
    g_memBlocks = g_sms * 16;
    *sm_count = g_sms;
    CK(cudaMalloc(&dA, kArrayBytes));
    CK(cudaMalloc(&dB, kArrayBytes));
    CK(cudaMalloc(&dOut, (size_t)g_fmaBlocks * kThreads * sizeof(float)));
    CK(cudaMemset(dA, 0x3F, kArrayBytes));
    CK(cudaMemset(dB, 0, kArrayBytes));
    CK(cudaEventCreate(&e0));
    CK(cudaEventCreate(&e1));
    return 0;
}

// kind: 0 = mem, 1 = fma. Runs chunks until `seconds` of wall time elapse.
// work: GB moved (mem) or GFLOP (fma). gpu_ms: summed CUDA-event time. checksum: finite sanity value.
EXPORT int bench_run(int kind, double seconds, double* work, double* gpu_ms, double* wall_s, double* checksum)
{
    double w = 0, total_ms = 0;
    auto t0 = std::chrono::steady_clock::now();
    double elapsed = 0;
    do {
        CK(cudaEventRecord(e0));
        if (kind == 0) {
            for (int k = 0; k < kMemLaunchesPerChunk; ++k)
                stream_kernel<<<g_memBlocks, kThreads>>>(dA, dB, kN4, 1.0f);
            w += kMemLaunchesPerChunk * 2.0 * kArrayBytes / 1e9;
        } else {
            fma_kernel<<<g_fmaBlocks, kThreads>>>(dOut, kFmaIters, 0.9999f, 1e-4f);
            w += (double)g_fmaBlocks * kThreads * kFmaIters * kFmaChainsPerThread * 2.0 / 1e9;
        }
        CK(cudaGetLastError());
        CK(cudaEventRecord(e1));
        CK(cudaEventSynchronize(e1));
        float ms = 0;
        CK(cudaEventElapsedTime(&ms, e0, e1));
        total_ms += ms;
        elapsed = std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();
    } while (elapsed < seconds);

    float h[4] = {0, 0, 0, 0};
    if (kind == 0) CK(cudaMemcpy(h, dB, sizeof h, cudaMemcpyDeviceToHost));
    else           CK(cudaMemcpy(h, dOut, sizeof h, cudaMemcpyDeviceToHost));
    double cs = h[0] + h[1] + h[2] + h[3];
    if (!std::isfinite(cs)) { snprintf(g_err, sizeof g_err, "non-finite checksum"); return 2; }
    *work = w; *gpu_ms = total_ms; *wall_s = elapsed; *checksum = cs;
    return 0;
}

EXPORT int bench_free()
{
    CK(cudaFree(dA)); CK(cudaFree(dB)); CK(cudaFree(dOut));
    dA = dB = nullptr; dOut = nullptr;
    return 0;
}
