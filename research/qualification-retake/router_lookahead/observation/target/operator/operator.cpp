// Private CPU diagnostic: both paths consume the same immutable bank and occupancy.
#include "../projector.h"
#include <ctime>

using namespace target_probe;
extern "C" void scipy_cblas_sgemm64_(int, int, int, int64_t, int64_t, int64_t, float,
                                     const float *, int64_t, const float *, int64_t,
                                     float, float *, int64_t);

namespace {
alignas(64) float normalized[32*width], scores[32*experts];
uint64_t clock_ns() {
    timespec t{};
    require(clock_gettime(CLOCK_MONOTONIC_RAW,&t)==0,"clock");
    return uint64_t(t.tv_sec)*1000000000U+t.tv_nsec;
}

void fast(const float *x, const float *source, const float *dest, const float *matrix,
          const float *bias, bool half, const int *indices, int n, int *ids) {
    for (int j=0;j<n;++j) {
        const float *row=x+indices[j]*width;
        for(int k=0;k<width;++k) {
            finite(row[k]); finite(source[k]); finite(dest[k]);
            require(source[k]!=0,"zero gamma");
            const float v=(row[k]/source[k])*dest[k];
            finite(v); float u=half?tf32(v):v; finite(u);
            normalized[j*width+k]=u;
        }
    }
    // CBLAS row-major (101), no-transpose (111), transpose (112), OpenBLAS ILP64.
    scipy_cblas_sgemm64_(101,111,112,n,experts,width,1.f,normalized,width,matrix,width,
                         0.f,scores,experts);
    for (int j=0;j<n;++j) {
        int *top=ids+j*4; std::fill(top,top+4,-1);
        std::array<float,4> best{};
        for (int e=0;e<experts;++e) {
            float v=scores[j*experts+e]+bias[e]; finite(v);
            for (int p=0;p<4;++p) {
                if(top[p]>=0 && v<=best[p]) continue;
                for (int l=3;l>p;--l) { top[l]=top[l-1]; best[l]=best[l-1]; }
                top[p]=e; best[p]=v; break;
            }
        }
    }
}
}

// mode 0 = the original scalar header; 1 = one site-wide CBLAS SGEMM.
// The coordinator checks every returned rank, selection and length outside the clock.
extern "C" int site(int mode, int timed, int target, int rows, const float *x,
                    const float *gamma0, const float *gamma1, const float *matrix,
                    const float *bias, const uint8_t *mask,const uint8_t *occupied,
                    int *ids, int *offers, uint64_t *elapsed) {
    try {
        require(rows>=1 && rows<=32 && (mode==0 || mode==1),"shape or mode");
        const auto begin=timed?clock_ns():0;
        int indices[32], n=0;
        for(int i=0;i<rows;++i) if(mask[i]) indices[n++]=i;
        require(n>0,"empty output mask");
        bool half=reduced(target,n);
        if (mode==0) {
            for (int j=0;j<n;++j) {
                auto row=project(x+indices[j]*width,gamma0,gamma1,matrix,bias,half);
                std::copy(row.begin(),row.end(),ids+4*j);
            }
        } else {
            fast(x,gamma0,gamma1,matrix,bias,half,indices,n,ids);
        }
        int freq[experts]{};
        for(int i=0;i<4*n;++i) ++freq[ids[i]];
        for(int j=0;j<4;++j) {
            int best=-1;
            for(int e=0;e<experts;++e)
                if(!occupied[e] && freq[e]>0 && (best<0||freq[e]>freq[best])) best=e;
            offers[j]=best;
            if(best>=0) freq[best]=0;
        }
        *elapsed=timed?clock_ns()-begin:0;
        return n;
    } catch(...) { return -1; }
}
