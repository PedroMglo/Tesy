// Model-free check for the exact routed-ID diagnostic used before wave planning.
#include "llama-moe-stream-id-check.h"
#include <array>
#include <cstdio>

int main() {
    constexpr uint32_t experts=128;
    std::array<int32_t, 8> ids={1, 3, 127, 0, 40, 42, 5, 2};
    if (llama_moe_first_invalid_id(ids.data(),ids.size(),experts).index!=-1) return 1;
    ids[4]=-1;
    const auto negative=llama_moe_first_invalid_id(ids.data(),ids.size(),experts);
    if (negative.index!=4 || negative.value!=-1) return 2;
    ids[1]=128;
    const auto range=llama_moe_first_invalid_id(ids.data(),ids.size(),experts);
    if (range.index!=1 || range.value!=128) return 3;
    if (llama_moe_first_invalid_id(ids.data(),0,experts).index!=-1) return 4;
    std::puts("C66_WAVE_ID_DIAGNOSTIC_MODEL_FREE_PASS");
}
