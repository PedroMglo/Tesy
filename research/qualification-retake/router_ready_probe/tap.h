#pragma once
#include <cstdint>
#include <time.h>
#include "ggml.h"

struct Probe {
    const ggml_tensor *target, *ids, *remap, *compact;
    int mode; // zero=OFF, one=ON, two=WRONG
    int entries=0, forwarded=0, remaps=0, threads=0;
    bool kernel_identity=false, remap_identity=false;
    uint64_t start=0, ready=0, consumer=0;
    int32_t snapshot[4*32]{};
};

inline uint64_t nanos(timespec value) {
    return uint64_t(value.tv_sec)*1000000000ull + uint64_t(value.tv_nsec);
}
inline uint64_t clock_now() {
    timespec value{};
    if (clock_gettime(CLOCK_MONOTONIC, &value) != 0) __builtin_trap();
    return nanos(value);
}
