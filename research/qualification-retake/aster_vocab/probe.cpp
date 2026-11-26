// Decode official GGUF metadata with the production libraries. Never accepts the full model.
#include "gguf.h"
#include "llama.h"

#include <cstdint>
#include <cstring>
#include <filesystem>
#include <iostream>
#include <iterator>
#include <stdexcept>
#include <string>
#include <vector>

constexpr size_t header_end = 13022240;

static void check(bool condition) {
    if (!condition) throw std::runtime_error("metadata/tokenization gate");
}

static void emit(const void *data, size_t size) {
    check(size <= 64 * 1024);
    uint32_t count = size;
    std::cout.write(reinterpret_cast<const char *>(&count), sizeof(count));
    std::cout.write(static_cast<const char *>(data), size);
}

int main(int argc, char **argv) {
    try {
        check(argc >= 3);
        std::string action(argv[1]);
        if (action == "--copy-kv" && argc == 4) {
            check(std::filesystem::file_size(argv[2]) == header_end);
            auto *source = gguf_init_from_file(argv[2], {true, nullptr});
            check(source && gguf_get_n_tensors(source) == 687 && gguf_get_data_offset(source) == header_end);
            auto *dest = gguf_init_empty();
            gguf_set_kv(dest, source);
            check(gguf_get_n_kv(dest) == gguf_get_n_kv(source) && gguf_get_n_tensors(dest) == 0);
            std::cout << gguf_get_n_kv(dest) << '\n';
            check(gguf_write_to_file(dest, argv[3], true));
            gguf_free(dest);
            gguf_free(source);
        } else if (action == "--tokenize" && argc == 3) {
            check(std::filesystem::file_size(argv[2]) <= header_end);
            auto *header = gguf_init_from_file(argv[2], {true, nullptr});
            check(header && gguf_get_n_tensors(header) == 0);
            gguf_free(header);
            auto params = llama_model_default_params();
            ggml_backend_dev_t empty[] = {nullptr};
            params.devices = empty;
            params.vocab_only = true;
            params.n_gpu_layers = 0;
            params.use_extra_bufts = false;
#ifdef REFERENCE_C269
            params.use_mmap = false;
            params.use_mlock = false;
#else
            params.load_mode = LLAMA_LOAD_MODE_NONE;
#endif
            auto *model = llama_model_load_from_file(argv[2], params);
            check(model);
            auto *v = llama_model_get_vocab(model);
            check(v && llama_vocab_n_tokens(v) == 201088);
            auto tmpl = llama_model_chat_template(model, nullptr);
            check(tmpl);
            emit(tmpl, std::strlen(tmpl));
            while (std::cin.peek() != std::char_traits<char>::eof()) {
                uint32_t n;
                check(static_cast<bool>(std::cin.read(reinterpret_cast<char *>(&n), sizeof(n))));
                check(n > 0 && n <= 32 * 1024);
                std::string text(n, '\0');
                check(static_cast<bool>(std::cin.read(text.data(), text.size())));
                std::vector<llama_token> tokens(n + 64);
                auto count = llama_tokenize(v, text.data(), n, tokens.data(), tokens.size(), false, true);
                check(count > 0 && static_cast<size_t>(count) <= tokens.size());
                emit(tokens.data(), count * sizeof(llama_token));
            }
            llama_model_free(model);
        } else {
            throw std::runtime_error("unknown mode");
        }
        return std::cout ? 0 : 1;
    } catch (const std::exception &) {
        std::cerr << "probe gate failed\n";
        return 1;
    }
}
