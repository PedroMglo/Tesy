// Check actual loader tensor bindings without constructing a context or reading a weight.
#include "ggml-backend.h"
#include "llama.h"
#include "../../cpu_numeric/vma/inspect.hpp"
#include <iostream>

int main(int argc, char **argv) {
    if (argc != 3) return 2;
    try {
        std::string mode = argv[1];
        if (mode != "NORMAL" && mode != "DRY") return 2;
        struct stat file{};
        if (stat(argv[2], &file) || file.st_size != 3390592) return 3;
        llama_backend_init();
        auto p = llama_model_default_params();
        p.n_gpu_layers = 0;
        p.ncmoe = 999;
        p.split_mode = LLAMA_SPLIT_MODE_LAYER;
        p.fit = p.use_mlock = p.use_thp = p.repack_tensors = false;
        p.merge_qkv = p.merge_up_gate_exps = p.check_tensors = p.validate_quants = false;
        p.use_mmap = p.defer_experts = true;
        p.dry_run = mode == "DRY";
        auto *model = llama_model_load_from_file(argv[2], p);
        if (!model || llama_n_layer(model) != 2 || llama_model_n_embd(model) != 256) return 4;
        auto maps = ik_vma::Inspect::capture(argv[2], file);
        for (int i = 0; i < 2; ++i) {
            for (const char *role : {"gate", "up", "down"}) {
                auto name = "blk." + std::to_string(i) + ".ffn_" + role + "_exps.weight";
                const auto *t = llama_get_model_tensor(model, name.c_str());
                if (!t || t->type != GGML_TYPE_MXFP4 || t->ne[0] != 256 || t->ne[1] != 256 ||
                    t->ne[2] != 8 || t->ne[3] != 1) return 5;
                const bool host = t->buffer && ggml_backend_buffer_is_host(t->buffer);
                const bool weight = t->buffer && ggml_backend_buffer_get_usage(t->buffer) ==
                                                   GGML_BACKEND_BUFFER_USAGE_WEIGHTS;
                int64_t offset = -1;
                if (host && t->data) {
                    auto addr = reinterpret_cast<uintptr_t>(t->data);
                    auto &v = ik_vma::cover(maps.maps, addr);
                    if (v.path == maps.key.path && v.offset <= v.begin)
                        offset = maps.offset(name, v.begin - v.offset, file.st_size,
                                             addr, ggml_nbytes(t));
                }
                std::cout << "VIEW " << name << ' ' << bool(t->data) << ' ' << bool(t->buffer)
                          << ' ' << host << ' ' << weight << ' ' << offset << '\n';
            }
        }
        llama_free_model(model);
        llama_backend_free();
    } catch (const std::exception &e) {
        std::cerr << e.what() << '\n';
        return 6;
    }
    return 0;
}
