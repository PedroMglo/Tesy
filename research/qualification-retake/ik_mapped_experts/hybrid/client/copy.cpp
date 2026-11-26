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

extern "C" cudaError_t cudaMemset(void *d, int value, size_t n) {
    static auto f = target<decltype(&cudaMemset)>("cudaMemset");
    const auto rc = f(d, value, n);
    if (observe::phase) std::printf("MEMSET %d sync %zu %d %zu %d\n",
                                    observe::phase, uintptr_t(d), value, n, int(rc));
    return rc;
}

extern "C" cudaError_t cudaMemsetAsync(void *d, int value, size_t n, cudaStream_t stream) {
    static auto f = target<decltype(&cudaMemsetAsync)>("cudaMemsetAsync");
    const auto rc = f(d, value, n, stream);
    if (observe::phase) std::printf("MEMSET %d async %zu %d %zu %d\n",
                                    observe::phase, uintptr_t(d), value, n, int(rc));
    return rc;
}

extern "C" cudaError_t cudaMemcpyPeerAsync(void *d, int devd, const void *s, int devs,
                                           size_t n, cudaStream_t stream) {
    static auto f = target<decltype(&cudaMemcpyPeerAsync)>("cudaMemcpyPeerAsync");
    const auto rc = f(d, devd, s, devs, n, stream);
    if (observe::phase) std::printf("PEER %d linear %d %d %zu %d\n",
                                    observe::phase, devs, devd, n, int(rc));
    return rc;
}

extern "C" cudaError_t cudaMemcpy3DPeerAsync(const cudaMemcpy3DPeerParms *p, cudaStream_t stream) {
    static auto f = target<decltype(&cudaMemcpy3DPeerAsync)>("cudaMemcpy3DPeerAsync");
    const auto rc = f(p, stream);
    // Array element size is not implied by cudaExtent::width, so no byte claim for 3D arrays.
    if (observe::phase) std::printf("PEER %d 3d %d %d %zu %d\n", observe::phase,
                                    p ? p->srcDevice : -1, p ? p->dstDevice : -1,
                                    !p || p->srcArray || p->dstArray ? size_t(0) :
                                        p->extent.width * p->extent.height * p->extent.depth, int(rc));
    return rc;
}
