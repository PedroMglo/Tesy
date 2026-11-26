#pragma once
#include <bit>
#include <cfenv>
#include "parked-arithmetic.inc"

static bool capture_wave = false;
static std::array<std::array<int32_t, 128>, 8> physical_waves;
static std::array<std::array<float, 128>, 8> mask_waves;
static std::array<unsigned, 8> seen_ids{}, seen_masks{};
static std::atomic<bool> invalid_tail{false};

static void capture_ids(ggml_tensor *dst, int ith, int nth, void *user) {
    llama_moe_stream_wave_ids(dst, ith, nth, user);
    if (capture_wave && ith == 0) {
        const auto w = static_cast<llama_moe_stream_wave *>(user)->wave;
        std::memcpy(physical_waves.at(w).data(), dst->data, ggml_nbytes(dst));
        ++seen_ids.at(w);
    }
}

static void capture_mask(ggml_tensor *dst, int ith, int nth, void *user) {
    llama_moe_stream_wave_mask(dst, ith, nth, user);
    if (capture_wave && ith == 0) {
        const auto w = static_cast<llama_moe_stream_wave *>(user)->wave;
        std::memcpy(mask_waves.at(w).data(), dst->data, ggml_nbytes(dst));
        ++seen_masks.at(w);
    }
}

static void parked_wave(ggml_tensor *dst, int ith, int nth, void *) {
    const auto *prev = static_cast<const float *>(dst->src[0]->data);
    const auto *physical = static_cast<const int32_t *>(dst->src[1]->data);
    const auto *mask = static_cast<const float *>(dst->src[2]->data);
    const auto *logical = static_cast<const int32_t *>(dst->src[3]->data);
    const auto *bias = static_cast<const float *>(dst->src[4]->data);
    auto *out = static_cast<float *>(dst->data);
    const int rows = int(dst->ne[1] * dst->ne[2]);
    for (int row = ith; row < rows; row += nth) {
        const int expert = logical[row];
        if (expert < 0 || expert >= 128 || physical[row] != -1 || std::bit_cast<uint32_t>(mask[row]) != 0) {
            invalid_tail = true;
            continue;
        }
        for (int col = 0; col < width; ++col) {
            const int i = row * width + col;
            const float b = bias[expert * width + col];
            if (!std::isfinite(prev[i]) || !std::isfinite(b)) invalid_tail = true;
            out[i] = empty_add(prev[i], b);
        }
    }
}

static ggml_tensor *tail_node(ggml_context *ctx, ggml_tensor *prev, ggml_tensor *physical,
                              ggml_tensor *mask, ggml_tensor *logical, ggml_tensor *bias) {
    ggml_tensor *args[] = {prev, physical, mask, logical, bias};
    for (const auto *a : args) need(ggml_is_contiguous(a), "contiguous CPU tile");
    need(prev->ne[0]==width && prev->ne[1]==4 && prev->ne[2]==nt &&
         ggml_nelements(physical)==4*nt && ggml_nelements(mask)==4*nt, "CPU tail geometry");
    return ggml_custom_4d(ctx, GGML_TYPE_F32, width, 4, nt, 1, args, 5, parked_wave, 8, nullptr);
}

static void save_wave_maps(const fs::path &out, const std::vector<int> &ids, llama_moe_stream_layer *layer) {
    std::ofstream f(out/"wave-maps.bin", std::ios::binary);
    for (int w=0; w<8; ++w) {
        need(seen_ids[w]==1 && seen_masks[w]==1, "one IDs/mask audit per wave");
        for (int row=0; row<4*nt; ++row) {
            const int physical=physical_waves[w][row];
            const uint32_t mask=std::bit_cast<uint32_t>(mask_waves[w][row]);
            if (w==0) need(mask==0x3f800000 && physical==layer->expert_slot.at(ids[row]), "active route/slot");
            else need(!mask && physical==-1, "parked route/mask");
        }
        f.write(reinterpret_cast<const char *>(physical_waves[w].data()), sizeof(physical_waves[w]));
        f.write(reinterpret_cast<const char *>(mask_waves[w].data()), sizeof(mask_waves[w]));
    }
    f.close();
    need(bool(f), "complete wave maps");
}
