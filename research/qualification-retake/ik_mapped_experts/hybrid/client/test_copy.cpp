// Forward the production hooks to a host-memory implementation with the exact CUDART ABI.
// No CUDA DSO or driver is linked; this independent test checks nested ownership and 2D pitches.
#include "hooks.hpp"
#include <cuda_runtime_api.h>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <vector>

#ifdef TEST_HOST_ABI
extern "C" cudaError_t cudaMemcpy(void *d,const void*s,size_t n,cudaMemcpyKind) {
    if (!s) return cudaErrorInvalidValue;
    std::memcpy(d,s,n); return cudaSuccess;
}
extern "C" cudaError_t cudaMemcpyAsync(void *d,const void*s,size_t n,cudaMemcpyKind,cudaStream_t) {
    if (!s) return cudaErrorInvalidValue;
    std::memcpy(d,s,n); return cudaSuccess;
}
static cudaError_t pitched(void *d,size_t dp,const void *s,size_t sp,size_t n,size_t height) {
    for(size_t i=0;i<height;i++) std::memcpy((char*)d+i*dp,(const char*)s+i*sp,n);
    return cudaSuccess;
}
extern "C" cudaError_t cudaMemcpy2D(void *d,size_t dp,const void*s,size_t sp,size_t n,size_t h,cudaMemcpyKind) {
    return pitched(d,dp,s,sp,n,h);
}
extern "C" cudaError_t cudaMemcpy2DAsync(void *d,size_t dp,const void*s,size_t sp,size_t n,size_t h,
                                         cudaMemcpyKind,cudaStream_t) { return pitched(d,dp,s,sp,n,h); }
extern "C" cudaError_t cudaHostRegister(void *,size_t n,unsigned) { return n?cudaSuccess:cudaErrorInvalidValue; }
extern "C" cudaError_t cudaMemset(void *d,int v,size_t n) { std::memset(d,v,n); return cudaSuccess; }
extern "C" cudaError_t cudaMemsetAsync(void *d,int v,size_t n,cudaStream_t) { std::memset(d,v,n); return cudaSuccess; }
extern "C" cudaError_t cudaMemcpyPeerAsync(void *d,int,const void*s,int,size_t n,cudaStream_t) {
    std::memcpy(d,s,n); return cudaSuccess;
}
extern "C" cudaError_t cudaMemcpy3DPeerAsync(const cudaMemcpy3DPeerParms *p,cudaStream_t) {
    return p ? cudaSuccess : cudaErrorInvalidValue;
}
#else
struct Call { void*d; const void*s; size_t n; int k,rc; };
static std::vector<Call> calls;
namespace observe {
int phase=1;
thread_local unsigned long owner=17;
int64_t file_offset(const void*,size_t) { return 99; }
void transfer(const char *,void*d,const void*s,size_t n,int k,int rc) {
    if (owner!=17 || phase!=1) std::abort();
    calls.push_back({d,s,n,k,rc});
}
}
static void require(bool ok) { if (!ok) std::abort(); }
int main() {
    unsigned char src[24]{1,2,3,4,5,6,7,8,9}, dst[24]{};
    require(cudaMemcpy(dst,src,2,cudaMemcpyHostToDevice)==cudaSuccess);
    require(cudaMemcpyAsync(dst,src,3,cudaMemcpyDeviceToHost,nullptr)==cudaSuccess);
    require(cudaMemcpy2D(dst,6,src,4,2,2,cudaMemcpyDeviceToDevice)==cudaSuccess);
    require(cudaMemcpy2DAsync(dst,6,src,4,2,2,cudaMemcpyHostToDevice,nullptr)==cudaSuccess);
    require(dst[0]==1 && dst[1]==2 && dst[5]==0 && dst[6]==5 && dst[7]==6 && dst[8]==0);
    require(cudaMemcpyAsync(dst,nullptr,1,cudaMemcpyHostToDevice,nullptr)==cudaErrorInvalidValue);
    require(calls.size()==7 && calls[0].n==2 && calls[1].n==3 && calls[1].k==2);
    for(size_t j=2;j<6;j++) {
        size_t r=(j-2)%2;
        require(calls[j].s==src+r*4 && calls[j].d==dst+r*6 && calls[j].n==2 &&
                calls[j].k==(j<4 ? 3:1));
    }
    require(calls[6].rc==cudaErrorInvalidValue);
    require(cudaHostRegister(src,4,0)==cudaSuccess && cudaHostRegister(src,0,0)==cudaErrorInvalidValue);
    require(cudaMemset(dst,23,2)==cudaSuccess && dst[0]==23);
    require(cudaMemsetAsync(dst,42,1,nullptr)==cudaSuccess && dst[0]==42 && dst[1]==23);
    require(cudaMemcpyPeerAsync(dst,0,src,1,3,nullptr)==cudaSuccess && dst[1]==2);
    require(cudaMemcpy3DPeerAsync(nullptr,nullptr)==cudaErrorInvalidValue);
    std::puts("PASS_HOST_ABI_TRANSFER_PITCH_AND_RC");
}
#endif
