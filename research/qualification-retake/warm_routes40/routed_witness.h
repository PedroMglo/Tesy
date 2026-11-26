// Common, non-operational C294 client witness for target positions and ordered IDs.
#pragma once

#include "ggml-backend.h"

#include <array>
#include <charconv>
#include <cstdint>
#include <stdexcept>
#include <string>
#include <string_view>
#include <vector>

class routed_witness {
public:
    std::vector<uint8_t> bytes{'W', 'R', 'T', '1'};

    static void need(bool ok, const char *reason) {
        if (!ok) {
            throw std::runtime_error(reason);
        }
    }

    void begin_call(int first, int size) {
        need(!in_call && !finished && first == total && size > 0 && size <= 256, "witness call");
        in_call = true;
        start = first;
        length = size;
        used = 0;
        byte('C');
        word(first);
        word(size);
    }

    void end_call() {
        need(in_call && used == length, "incomplete witness call");
        close_graph();
        in_call = false;
        total += length;
        byte('D');
    }

    void finish() {
        need(!in_call && total > 0 && !finished, "incomplete witness");
        finished = true;
        byte('F');
    }

    bool observe(ggml_tensor *tensor, bool ask) {
        try {
            return visit(tensor, ask);
        } catch (const std::exception &error) {
            throw std::runtime_error(std::string(error.what()) + " [node=" + ggml_get_name(tensor) +
                                     ", op=" + ggml_op_name(tensor->op) +
                                     ", rows=" + std::to_string(tensor->ne[1]) + "]");
        }
    }

private:
    int start = 0, length = 0, used = 0, total = 0, width = 0, next_layer = 0;
    bool in_call = false, output_seen = false, empty_seen = false, finished = false;

    static int route_layer(std::string_view name) {
        constexpr std::string_view prefix = "ffn_moe_topk-";
        if (name.size() <= prefix.size() || name.substr(0, prefix.size()) != prefix) {
            return -1;
        }
        name.remove_prefix(prefix.size());
        int layer = -1;
        const char *end = name.data() + name.size();
        auto parsed = std::from_chars(name.data(), end, layer);
        // ggml_cont, reshape and other derived tensors append their own suffix.
        // They provide neither extra routed layers nor alternative logical labels.
        if (parsed.ptr != end) {
            return -1;
        }
        need(parsed.ec == std::errc() && layer >= 0 && layer < 36 &&
             !(name.size() > 1 && name[0] == '0'), "invalid canonical topk layer");
        return layer;
    }

    // GGML asks for each scheduled node. Only a true answer yields delivery
    // after synchronization. Never read tensor data in the query callback.
    bool visit(ggml_tensor *tensor, bool ask) {
        const std::string_view name(ggml_get_name(tensor));
        const int layer = route_layer(name);
        const bool position = name == "Qcur-0" && tensor->op == GGML_OP_ROPE;
        const bool selector = name == "ffn_inp-35" && tensor->ne[1] > 0;
        if (!position && !selector && layer < 0) {
            return false;
        }
        if (layer == 35 && tensor->ne[1] == 0) {
            need(ask && in_call && width > 0 && used < length && next_layer == 35 &&
                 !empty_seen && tensor->ne[0] == 4 && tensor->type == GGML_TYPE_I32,
                 "unexpected empty final router");
            empty_seen = true;
            return false;
        }
        if (ask) {
            return true;
        }
        need(in_call, "node outside supplied call");
        if (position) {
            positions(tensor);
        } else if (selector) {
            selection(tensor);
        } else {
            route(layer, tensor);
        }
        return true;
    }

    void byte(int value) {
        need(bytes.size() < 1024 * 1024 && value >= 0 && value < 256, "witness overflow");
        bytes.push_back(static_cast<uint8_t>(value));
    }

    void word(int value) {
        need(value >= 0 && value < 65536, "witness word");
        byte(value & 255);
        byte(value >> 8);
    }

    void close_graph() {
        if (!width) {
            return;
        }
        const bool final = used == length;
        need(next_layer == (final ? 36 : 35) && output_seen == final,
             "missing routed layer or final selector");
        width = 0;
        next_layer = 0;
        output_seen = false;
        empty_seen = false;
        byte('E');
    }

    void positions(ggml_tensor *query) {
        close_graph();
        auto *input = query->src[1];
        need(query->op == GGML_OP_ROPE && input && input->type == GGML_TYPE_I32 &&
             input->ne[0] > 0 && input->ne[0] <= 32 && input->ne[1] == 1 &&
             input->ne[2] == 1 && input->ne[3] == 1 && input->nb[0] == sizeof(int32_t) &&
             query->ne[2] == input->ne[0], "unexpected RoPE position view");
        width = static_cast<int>(input->ne[0]);
        need(used + width <= length, "unexpected extra ubatch");
        std::array<int32_t, 32> actual{};
        ggml_backend_tensor_get(input, actual.data(), 0, width * sizeof(int32_t));
        byte('U');
        byte(width);
        for (int i = 0; i < width; ++i) {
            need(actual[i] == start + used + i && actual[i] < 8192, "wrong graph position");
            word(actual[i]);
        }
        used += width;
    }

    void selection(ggml_tensor *tensor) {
        // Both residual operands use GET_ROWS and the target's output index.
        need(width > 0 && used == length && next_layer == 35 && !output_seen &&
             tensor->op == GGML_OP_ADD && tensor->ne[1] == 1, "unexpected final FFN selector");
        for (int side = 0; side < 2; ++side) {
            auto *rows = tensor->src[side];
            need(rows && rows->op == GGML_OP_GET_ROWS && rows->src[1], "missing final get_rows");
            auto *index = rows->src[1];
            need(index->type == GGML_TYPE_I32 && ggml_nelements(index) == 1,
                 "last-output index shape");
            int32_t selected = -1;
            ggml_backend_tensor_get(index, &selected, 0, sizeof(selected));
            need(selected == width - 1, "wrong final physical row");
        }
        output_seen = true;
        byte('O');
        byte(width - 1);
    }

    void route(int layer, ggml_tensor *tensor) {
        need(width > 0 && layer == next_layer && (layer != 35 || output_seen), "routed layer order");
        const int rows = layer == 35 ? 1 : width;
        const size_t stride = tensor->nb[1];
        need(tensor->type == GGML_TYPE_I32 && tensor->ne[0] == 4 && tensor->ne[1] == rows &&
             tensor->ne[2] == 1 && tensor->ne[3] == 1 && tensor->nb[0] == 4 &&
             stride >= 16 && stride <= 512 && stride % 4 == 0, "unexpected logical router view");
        const size_t span = (rows - 1) * stride + 16;
        std::array<int32_t, 32 * 128> raw{};
        need(span <= ggml_nbytes(tensor), "strided payload length");
        ggml_backend_tensor_get(tensor, raw.data(), 0, span);
        byte('R');
        byte(layer);
        byte(rows);
        word(static_cast<int>(stride));
        for (int i = 0; i < rows; ++i) {
            std::array<bool, 128> seen{};
            for (int rank = 0; rank < 4; ++rank) {
                const int id = raw[i * (stride / 4) + rank];
                need(id >= 0 && id < 128 && !seen[id], "invalid top-4 IDs");
                seen[id] = true;
                byte(id);
            }
        }
        ++next_layer;
    }
};
