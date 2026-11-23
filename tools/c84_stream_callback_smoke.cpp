// Drive the real remap/load/eviction callback on a tiny synthetic expert file.
#include "llama-moe-stream.h"

#include "ggml-backend.h"
#include "ggml.h"

#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <vector>

int main(int argc, char ** argv) {
    if (argc != 3 || setenv("TESY_C84_EXPERT_TRACE_FILE", argv[2], 1) != 0) return 2;
    FILE * file = std::fopen(argv[1], "wx");
    if (file == nullptr) return 3;
    for (int32_t i = 0; i < 128; ++i) {
        const float value = static_cast<float>(i);
        if (std::fwrite(&value, sizeof(value), 1, file) != 1) return 4;
    }
    if (std::fclose(file) != 0) return 5;

    ggml_init_params params = { 64 * 1024, nullptr, false };
    ggml_context * ctx = ggml_init(params);
    if (ctx == nullptr) return 6;
    ggml_tensor * meta = ggml_new_tensor_3d(ctx, GGML_TYPE_F32, 1, 1, 128);
    ggml_tensor * ids = ggml_new_tensor_2d(ctx, GGML_TYPE_I32, 4, 1);
    ggml_tensor * slots = ggml_new_tensor_2d(ctx, GGML_TYPE_I32, 4, 1);
    uint64_t slot_hash = 1469598103934665603ull;
    {
        llama_moe_stream mgr(1, 32, 1, false);
        mgr.create_cache_tensor(0, ggml_backend_cpu_buffer_type(), meta, 0, 0);
        mgr.alloc_bufs(false);
        mgr.open_files({argv[1]});
        auto * layer = mgr.layer(0);
        if (layer == nullptr) return 7;
        for (int group = 0; group < 9; ++group) {
            int32_t * logical = static_cast<int32_t *>(ids->data);
            for (int k = 0; k < 4; ++k) logical[k] = group * 4 + k;
            llama_moe_stream_remap(slots, ids, 0, 1, layer);
            int32_t * physical = static_cast<int32_t *>(slots->data);
            for (int k = 0; k < 4; ++k) {
                const int32_t slot = physical[k];
                if (slot < 0 || slot >= 32 || layer->slot_expert[slot] != logical[k] ||
                    layer->slot_state[slot] != LLAMA_MOE_STREAM_SLOT_RESIDENT) return 8;
                float stored = -1;
                ggml_backend_tensor_get(layer->weights[0].cache, &stored,
                                        static_cast<size_t>(slot) * sizeof(float), sizeof(stored));
                if (stored != static_cast<float>(logical[k])) return 9;
                slot_hash = (slot_hash ^ static_cast<uint64_t>(slot)) * 1099511628211ull;
            }
        }
        int32_t logical[] = {0, 1, 2, 3}; // evicted by the ninth group
        for (int repeat = 0; repeat < 2; ++repeat) {
            std::memcpy(ids->data, logical, sizeof(logical));
            llama_moe_stream_remap(slots, ids, 0, 1, layer);
            int32_t * physical = static_cast<int32_t *>(slots->data);
            for (int k = 0; k < 4; ++k) {
                if (physical[k] < 0 || physical[k] >= 32 ||
                    layer->slot_expert[physical[k]] != logical[k]) return 10;
                slot_hash = (slot_hash ^ static_cast<uint64_t>(physical[k])) * 1099511628211ull;
            }
        }
    }
    ggml_free(ctx);
    std::printf("C84_SYNTHETIC_STREAM_SLOT_HASH=%llu\n",
                static_cast<unsigned long long>(slot_hash));
    return 0;
}
