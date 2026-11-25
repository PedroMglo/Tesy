// private-pinned.h contains the unmodified C269 headers, dot declaration,
// hsum_float_8 and mul_add_epi8. The build checks their source and compiler.
#include "private-pinned.h"

#define CONTROL 0
#define SHARED 1
#define SEPARATE 2

#if TESY_FOUR_MODE == SHARED || TESY_FOUR_MODE == SEPARATE

typedef struct {
    __m256i codes;
    float scale;
} activation_block;

static inline activation_block load_activation(const block_q8_0 *block) {
    return (activation_block) {
        _mm256_loadu_si256((const __m256i *)block->qs),
        GGML_CPU_FP16_TO_FP32(block->d),
    };
}

static inline __m256 accumulate(__m256 previous, const block_mxfp4 *w, activation_block y) {
    const __m128i values = _mm_loadu_si128((const __m128i *)kvalues_fp4);
    const __m128i mask = _mm_set1_epi8(0x0f);
    const __m128i packed = _mm_loadu_si128((const __m128i *)w->qs);
    const __m128i low = _mm_shuffle_epi8(values, _mm_and_si128(packed, mask));
    const __m128i high = _mm_shuffle_epi8(values, _mm_and_si128(_mm_srli_epi16(packed, 4), mask));
    const __m256i pair = mul_add_epi8(MM256_SET_M128I(high, low), y.codes);
    const __m256i quad = _mm256_madd_epi16(pair, _mm256_set1_epi16(1));
    const __m256 scale = _mm256_set1_ps(y.scale * GGML_CPU_E8M0_TO_FP32_HALF(w->e));
    return _mm256_fmadd_ps(scale, _mm256_cvtepi32_ps(quad), previous);
}

static inline float finish_odd(float partial, const block_mxfp4 *w, const block_q8_0 *y) {
    const float scale = GGML_CPU_FP16_TO_FP32(y->d) * GGML_CPU_E8M0_TO_FP32_HALF(w->e);
    int lo = 0;
    int hi = 0;
    for (int j = 0; j < QK_MXFP4/2; ++j) {
        lo += y->qs[j] * kvalues_fp4[w->qs[j] & 0xf];
        hi += y->qs[j + QK_MXFP4/2] * kvalues_fp4[w->qs[j] >> 4];
    }
    return partial + scale * (lo + hi);
}
#endif

void tesy_four_rows(int n, int rows, float *out, const void *weights, size_t stride,
                    const void *const q8[4]);

void tesy_four_rows(int n, int rows, float *out, const void *weights, size_t stride,
                    const void *const q8[4]) {
    const unsigned char *base = weights;
    if (rows < 1 || rows > 4 || n <= 0 || n % QK_MXFP4) {
        abort();
    }
    if (TESY_FOUR_MODE == CONTROL || rows != 4) {
        for (int r = 0; r < rows; ++r) {
            const void *y = q8[TESY_FOUR_MODE == SHARED ? 0 : r];
            ggml_vec_dot_mxfp4_q8_0(n, out + r, 0, base + (size_t)r * stride, 0, y, 0, 1);
        }
        return;
    }

#if TESY_FOUR_MODE == SHARED || TESY_FOUR_MODE == SEPARATE
    const block_mxfp4 *w[4];
    const block_q8_0 *y[4];
    __m256 even[4];
    __m256 odd[4];
    for (int r = 0; r < 4; ++r) {
        w[r] = (const block_mxfp4 *)(base + (size_t)r * stride);
        y[r] = q8[TESY_FOUR_MODE == SHARED ? 0 : r];
        even[r] = _mm256_setzero_ps();
        odd[r] = _mm256_setzero_ps();
    }
    const int blocks = n / QK_MXFP4;
    int ib = 0;
    for (; ib + 1 < blocks; ib += 2) {
#if TESY_FOUR_MODE == SHARED
        const activation_block common_even = load_activation(y[0] + ib);
        const activation_block common_odd = load_activation(y[0] + ib + 1);
#endif
#pragma GCC unroll 4
        for (int r = 0; r < 4; ++r) {
#if TESY_FOUR_MODE == SHARED
            const activation_block a = common_even, b = common_odd;
#else
            const activation_block a = load_activation(y[r] + ib);
            const activation_block b = load_activation(y[r] + ib + 1);
#endif
            even[r] = accumulate(even[r], w[r] + ib, a);
            odd[r] = accumulate(odd[r], w[r] + ib + 1, b);
        }
    }
    for (int r = 0; r < 4; ++r) {
        float sum = hsum_float_8(_mm256_add_ps(even[r], odd[r]));
        if (ib < blocks) {
            sum = finish_odd(sum, w[r] + ib, y[r] + ib);
        }
        out[r] = sum;
    }
#endif
}
