// CUDART ABI wrappers. Forward to the real linked runtime and retain its result.
#include "hooks.hpp"
#include <cuda_runtime_api.h>
#include <dlfcn.h>
#include <cstdio>
#include <cstdlib>

template <typename T> static T target(const char *name) {
    auto addr = dlsym(RTLD_NEXT, name);
    if (!addr) std::abort();
    return reinterpret_cast<T>(addr);
}

extern "C" cudaError_t cudaMemcpy(void *d, const void *s, size_t n, cudaMemcpyKind k) {
    static auto f = target<decltype(&cudaMemcpy)>("cudaMemcpy");
    const auto rc = f(d, s, n, k);
    observe::transfer("sync", d, s, n, k, rc);
    return rc;
}
extern "C" cudaError_t cudaMemcpyAsync(void *d, const void *s, size_t n, cudaMemcpyKind k, cudaStream_t st) {
    static auto f = target<decltype(&cudaMemcpyAsync)>("cudaMemcpyAsync");
    const auto rc = f(d, s, n, k, st);
    observe::transfer("async", d, s, n, k, rc);
    return rc;
}
static void rows(const char *api, void *d, size_t dp, const void *s, size_t sp,
                 size_t width, size_t height, cudaMemcpyKind k, cudaError_t rc) {
    for (size_t r = 0; r < height; ++r)
        observe::transfer(api, static_cast<char *>(d) + r*dp,
                          static_cast<const char *>(s) + r*sp, width, k, rc);
}
extern "C" cudaError_t cudaMemcpy2D(void *d, size_t dp, const void *s, size_t sp,
                                   size_t width, size_t height, cudaMemcpyKind k) {
    static auto f = target<decltype(&cudaMemcpy2D)>("cudaMemcpy2D");
    const auto rc = f(d, dp, s, sp, width, height, k);
    rows("sync2d", d, dp, s, sp, width, height, k, rc);
    return rc;
}
extern "C" cudaError_t cudaMemcpy2DAsync(void *d, size_t dp, const void *s, size_t sp,
                                        size_t width, size_t height, cudaMemcpyKind k, cudaStream_t st) {
    static auto f = target<decltype(&cudaMemcpy2DAsync)>("cudaMemcpy2DAsync");
    const auto rc = f(d, dp, s, sp, width, height, k, st);
    rows("async2d", d, dp, s, sp, width, height, k, rc);
    return rc;
}
extern "C" cudaError_t cudaHostRegister(void *p, size_t n, unsigned flags) {
    static auto f = target<decltype(&cudaHostRegister)>("cudaHostRegister");
    const auto rc = f(p, n, flags);
    if (observe::phase) std::printf("REG %d %zu %zu %lld %u %d\n", observe::phase,
                                    uintptr_t(p), n, (long long)observe::file_offset(p,n), flags, int(rc));
    return rc;
}
