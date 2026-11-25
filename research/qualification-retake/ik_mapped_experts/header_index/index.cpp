// Probe only the stock loader's metadata constructor and deferred-file index.
#include "llama-model-loader.h"
#include "nlohmann/json.hpp"

#include <iostream>
#include <string>

using json = nlohmann::json;

static void require(bool condition, const char *message) {
    if (!condition) throw std::runtime_error(message);
}

static uint32_t u32(const gguf_context *ctx, const char *key) {
    const int index = gguf_find_key(ctx, key);
    require(index >= 0 && gguf_get_kv_type(ctx, index) == GGUF_TYPE_UINT32, "missing geometry");
    return gguf_get_val_u32(ctx, index);
}

static json inspect(const std::string &file, bool defer) {
    llama_model_loader loader(file, 0, true, false, false, false, false, false, defer,
                              nullptr, nullptr);
    require(loader.get_arch() == LLM_ARCH_OPENAI_MOE && loader.get_arch_name() == "gpt-oss",
            "architecture");
    llama_hparams hp{};
    hp.n_layer = u32(loader.meta, "gpt-oss.block_count");
    hp.n_expert = u32(loader.meta, "gpt-oss.expert_count");
    hp.n_expert_used = u32(loader.meta, "gpt-oss.expert_used_count");
    require(hp.n_layer == 36 && hp.n_expert == 128 && hp.n_expert_used == 4, "routing geometry");
    require(loader.use_mmap && loader.mappings.empty() && loader.files.size() == 1,
            "unexpected mapping, conversion or shard");
    loader.build_expert_tensor_index(hp);
    const auto &idx = loader.expert_tensor_index;
    require(idx.file_ranges.size() == 1 && !idx.empty(), "missing expert index");
    json ranges = json::array(), tensors = json::array();
    for (const auto &range : idx.file_ranges.front()) {
        ranges.push_back({range.first, range.last});
    }
    for (const auto &w : loader.weights) {
        require(w.idx == 0 && w.tensor->data == nullptr && !w.mxfp4_repack &&
                w.expert_scale.empty() && w.nvfp4_scale.empty() && w.f8_scale.empty(),
                "materialized data or transformed tensor descriptor");
        std::vector<int64_t> shape(w.tensor->ne, w.tensor->ne + ggml_n_dims(w.tensor));
        tensors.push_back({{"name", w.tensor->name}, {"offset", w.offs}, {"shape", shape},
                           {"type", int(w.tensor->type)}, {"bytes", ggml_nbytes(w.tensor)}});
    }
    return {{"status", "INDEXED"}, {"defer", loader.should_defer_expert_mmaps()},
            {"dense_bytes", idx.dense_bytes}, {"deferred_bytes", idx.deferred_bytes},
            {"total_bytes", loader.n_bytes}, {"ranges", ranges}, {"tensors", tensors}};
}

int main(int argc, char **argv) {
    if (argc != 3) return 2;
    const std::string mode = argv[2];
    if (mode != "off" && mode != "on" && mode != "short") return 2;
    try {
        const auto result = inspect(argv[1], mode != "off");
        if (mode == "short") throw std::runtime_error("short file was accepted");
        std::cout << result.dump() << '\n';
    } catch (const std::exception &e) {
        if (mode == "short" && std::string(e.what()).find("not within the file bounds") !=
                std::string::npos) {
            std::cout << "{\"status\":\"REJECTED_SHORT_TENSOR_RANGE\"}\n";
            return 0;
        }
        std::cerr << e.what() << '\n';
        return 1;
    }
}
