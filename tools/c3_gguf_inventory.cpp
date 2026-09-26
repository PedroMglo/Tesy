#include "ggml.h"
#include "gguf.h"

#include <cinttypes>
#include <cstdio>
#include <cstdlib>
#include <limits>
#include <string>

namespace {

void json_string(const char * value) {
    std::fputc('"', stdout);
    const unsigned char * p =
        reinterpret_cast<const unsigned char *>(value ? value : "");
    for (; *p != '\0'; ++p) {
        switch (*p) {
            case '"':
                std::fputs("\\\"", stdout);
                break;
            case '\\':
                std::fputs("\\\\", stdout);
                break;
            case '\b':
                std::fputs("\\b", stdout);
                break;
            case '\f':
                std::fputs("\\f", stdout);
                break;
            case '\n':
                std::fputs("\\n", stdout);
                break;
            case '\r':
                std::fputs("\\r", stdout);
                break;
            case '\t':
                std::fputs("\\t", stdout);
                break;
            default:
                if (*p < 0x20) {
                    std::fprintf(stdout, "\\u%04x", static_cast<unsigned>(*p));
                } else {
                    std::fputc(*p, stdout);
                }
        }
    }
    std::fputc('"', stdout);
}

[[noreturn]] void usage(const char * argv0, int code) {
    std::fprintf(
        code == 0 ? stdout : stderr,
        "usage: %s MODEL.gguf\n"
        "Emit GGUF tensor metadata as Tesy JSONL without allocating tensor data.\n",
        argv0);
    std::exit(code);
}

}  // namespace

int main(int argc, char ** argv) {
    if (argc == 2 && (std::string(argv[1]) == "-h" || std::string(argv[1]) == "--help")) {
        usage(argv[0], 0);
    }
    if (argc != 2) {
        usage(argv[0], 2);
    }

    ggml_context * meta = nullptr;
    const gguf_init_params params = {
        /*.no_alloc =*/ true,
        /*.ctx      =*/ &meta,
    };
    gguf_context * gguf = gguf_init_from_file(argv[1], params);
    if (gguf == nullptr || meta == nullptr) {
        std::fprintf(stderr, "failed to read GGUF metadata: %s\n", argv[1]);
        if (meta != nullptr) {
            ggml_free(meta);
        }
        if (gguf != nullptr) {
            gguf_free(gguf);
        }
        return 2;
    }

    const int64_t tensor_count = gguf_get_n_tensors(gguf);
    if (tensor_count <= 0) {
        std::fprintf(stderr, "GGUF contains no tensors\n");
        ggml_free(meta);
        gguf_free(gguf);
        return 2;
    }

    const size_t data_offset = gguf_get_data_offset(gguf);
    std::printf(
        "{\"schema\":\"tesy.gguf_native_inventory_header.v1\","
        "\"gguf_version\":%u,\"alignment\":%zu,\"data_offset\":%zu,"
        "\"tensor_count\":%" PRId64 "}\n",
        gguf_get_version(gguf),
        gguf_get_alignment(gguf),
        data_offset,
        tensor_count);

    for (int64_t id = 0; id < tensor_count; ++id) {
        const char * name = gguf_get_tensor_name(gguf, id);
        if (name == nullptr || name[0] == '\0') {
            std::fprintf(stderr, "tensor %" PRId64 " has no name\n", id);
            ggml_free(meta);
            gguf_free(gguf);
            return 2;
        }

        ggml_tensor * tensor = ggml_get_tensor(meta, name);
        if (tensor == nullptr) {
            std::fprintf(stderr, "metadata tensor missing from ggml context: %s\n", name);
            ggml_free(meta);
            gguf_free(gguf);
            return 2;
        }

        const int n_dims = ggml_n_dims(tensor);
        if (n_dims <= 0 || n_dims > GGML_MAX_DIMS) {
            std::fprintf(stderr, "invalid tensor dimensions for %s: %d\n", name, n_dims);
            ggml_free(meta);
            gguf_free(gguf);
            return 2;
        }

        const size_t n_bytes = gguf_get_tensor_size(gguf, id);
        const size_t relative_offset = gguf_get_tensor_offset(gguf, id);
        if (relative_offset > std::numeric_limits<size_t>::max() - data_offset) {
            std::fprintf(stderr, "tensor offset overflow for %s\n", name);
            ggml_free(meta);
            gguf_free(gguf);
            return 2;
        }
        const size_t absolute_offset = data_offset + relative_offset;
        const ggml_type type = gguf_get_tensor_type(gguf, id);

        std::fputs(
            "{\"schema\":\"tesy.gguf_native_tensor.v1\",\"id\":",
            stdout);
        std::fprintf(stdout, "%" PRId64 ",\"name\":", id);
        json_string(name);
        std::fputs(",\"shape\":[", stdout);
        for (int dim = 0; dim < n_dims; ++dim) {
            if (dim != 0) {
                std::fputc(',', stdout);
            }
            std::fprintf(stdout, "%" PRId64, tensor->ne[dim]);
        }
        std::fputs("],\"tensor_type\":", stdout);
        json_string(ggml_type_name(type));
        std::fprintf(
            stdout,
            ",\"n_bytes\":%zu,\"relative_data_offset\":%zu,"
            "\"data_offset\":%zu}\n",
            n_bytes,
            relative_offset,
            absolute_offset);
    }

    ggml_free(meta);
    gguf_free(gguf);
    return 0;
}
