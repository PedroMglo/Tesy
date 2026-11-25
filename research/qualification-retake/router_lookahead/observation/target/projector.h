// Scalar shadow reference. Its summation order has its own calibration gate.
#pragma once
#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <stdexcept>
#include <vector>

namespace target_probe __attribute__((visibility("hidden"))) {
constexpr int width=2880, experts=128;
inline void require(bool ok, const char *reason) {
    if (!ok) throw std::runtime_error(reason);
}
inline float tf32(float value) {
    uint32_t bits;
    std::memcpy(&bits, &value, sizeof(bits));
    bits = (bits + 0xfffu + ((bits >> 13u) & 1u)) & ~0x1fffu;
    std::memcpy(&value, &bits, sizeof(bits));
    return value;
}
inline bool reduced(int target, int rows) {
    return target >= 25 && (rows == 29 || rows == 32);
}
inline void finite(float x) { require(std::isfinite(x), "router probe nonfinite"); }

inline void prepare_matrix(std::vector<float>& w, bool half) {
    for (float &v : w) {
        finite(v);
        if (half) { v=tf32(v); finite(v); }
    }
}
inline std::array<int,4> project(const float *x, const float *src_gamma, const float *dst_gamma,
                                const float *w, const float *bias, bool half) {
    std::array<float,width> lhs;
    for (int k=0; k<width; ++k) {
        finite(x[k]); finite(src_gamma[k]); finite(dst_gamma[k]);
        require(src_gamma[k]!=0, "router probe zero gamma");
        float v=(x[k]/src_gamma[k])*dst_gamma[k];
        finite(v); lhs[k]=half ? tf32(v) : v; finite(lhs[k]);
    }
    std::array<int,4> ids{{-1,-1,-1,-1}};
    std::array<float,4> scores{};
    for (int i=0; i<experts; ++i) {
        float sum=0;
        for (int k=0; k<width; ++k) sum+=lhs[k]*w[i*width+k];
        sum+=bias[i]; finite(sum);
        for (int j=0; j<4; ++j) {
            if (ids[j]>=0 && sum<=scores[j]) continue;
            for (int l=3; l>j; --l) { ids[l]=ids[l-1]; scores[l]=scores[l-1]; }
            ids[j]=i; scores[j]=sum; break;
        }
    }
    return ids;
}
inline int source_layer(const char *name) {
    constexpr char prefix[]="attn_post_norm-";
    if (std::strncmp(name,prefix,sizeof(prefix)-1)!=0) return -1;
    const char *s=name+sizeof(prefix)-1;
    if (!s[0] || s[0]<'0' || s[0]>'9' || (s[0]=='0' && s[1])) return -1;
    int n=s[0]-'0';
    if (s[1]) {
        if (s[1]<'0' || s[1]>'9' || s[2]) return -1;
        n=n*10+(s[1]-'0');
    }
    return n<35 ? n : -1;
}
template<class Batch> inline bool selected(const Batch& batch,int n_outputs,int target,int i) {
    return target!=35 || n_outputs==int(batch.n_tokens) || (batch.output && batch.output[i]);
}
} // namespace target_probe
