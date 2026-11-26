// C291 constructor gate. Only tensor metadata is allocated.
#include "llama-moe-stream.h"
#include "c291-expert-store.h"

#include <dlfcn.h>
#include <filesystem>
#include <iostream>

#ifdef TESY_STORE_TESTING
#error The original production constructor is required
#endif

using json = nlohmann::json;
using check = tesy_expert_store;
static int read_calls;

extern "C" ssize_t __wrap_pread(int, void *, size_t, off_t) {
    ++read_calls;
    errno = EIO;
    return -1;
}

static json fd_identity(int fd) {
    struct stat s{};
    check::require(fstat(fd, &s) == 0, "pack FD fstat");
    auto ns = [](timespec t) { return uint64_t(t.tv_sec) * 1000000000 + t.tv_nsec; };
    return {{"dev", s.st_dev}, {"inode", s.st_ino}, {"size_bytes", s.st_size},
            {"mtime_ns", ns(s.st_mtim)}, {"ctime_ns", ns(s.st_ctim)}};
}

static json verify(const char *manifest, const char *model, const char *pack, const char *bases) {
    constexpr size_t slab = 4406400;
    constexpr size_t stride = 13258752;
    const std::array<std::string, 3> roles = {"gate", "down", "up"};
    std::ifstream f(bases);
    check::require(f.is_open(), "missing independently inventoried bases");
    ggml_init_params init{4 * 1024 * 1024, nullptr, true};
    std::unique_ptr<ggml_context, decltype(&ggml_free)> ctx(ggml_init(init), ggml_free);
    check::require(ctx != nullptr && ggml_get_no_alloc(ctx.get()), "metadata-only context");

    std::vector<std::unique_ptr<llama_moe_stream_layer>> layers;
    for (unsigned l = 0; l < 36; ++l) {
        auto sl = std::make_unique<llama_moe_stream_layer>();
        sl->il = l;
        sl->n_slots = 40;
        sl->n_expert = 128;
        for (unsigned r = 0; r < roles.size(); ++r) {
            unsigned layer, role;
            size_t offset, bytes;
            check::require(bool(f >> layer >> role >> offset >> bytes) &&
                           layer == l && role == r && bytes == slab, "inventory geometry");
            auto *w = ggml_new_tensor_3d(ctx.get(), GGML_TYPE_MXFP4, 2880, 2880, 40);
            check::require(w && !w->data && !w->buffer && w->nb[2] == slab, "tensor allocated/stride");
            const auto name = "blk." + std::to_string(l) + ".ffn_" + roles[r] + "_exps.weight.stream_cache";
            ggml_set_name(w, name.c_str());
            sl->weights.push_back({w, 0, offset, bytes});
        }
        layers.push_back(std::move(sl));
    }
    f >> std::ws;
    check::require(f.eof(), "trailing tensor base");
    int fd;
    json out;
    {
        tesy_expert_store store(manifest, model, layers);
        fd = store.data.descriptor();
        int flags = fcntl(fd, F_GETFL);
        check::require(flags >= 0 && (flags & O_DIRECT) && (flags & O_ACCMODE) == O_RDONLY, "live pack FD flags");
        check::require(fd_identity(fd) == store.pack_identity &&
                       store.pack_identity == check::identity(pack) &&
                       store.original_identity == check::identity(model), "live FD identity");
        size_t count = 0;
        for (const auto &layer : store.entries) {
            for (const auto &record : layer) {
                check::require(record.offset == count * stride &&
                               record.relative == std::array<size_t, 3>{0, slab, 2 * slab}, "constructor record");
                ++count;
            }
        }
        out = {{"pack_stat", store.pack_identity}, {"model_stat", store.original_identity},
               {"pack_bytes", store.data.file_size()}, {"mem_align", store.data.memory_alignment()},
               {"offset_align", store.data.offset_alignment()}, {"pack_fd_direct", true},
               {"layers", layers.size()}, {"tensor_headers", 3 * layers.size()}, {"records", count}};
    }
    check::require(fcntl(fd, F_GETFD) < 0 && errno == EBADF, "FD not closed after destructor");
    layers[35]->weights[2].offs += 1;
    bool rejected = false;
    try {
        tesy_expert_store altered(manifest, model, layers);
    } catch (const std::runtime_error &e) {
        rejected = std::string(e.what()) == "store component/native tensor mapping changed";
    }
    check::require(rejected && read_calls == 0, "negative offset or unexpected pread");
    Dl_info lib{};
    check::require(dladdr(reinterpret_cast<void *>(ggml_get_name), &lib) && lib.dli_fname, "ggml provider");
    out["ggml_provider"] = std::filesystem::canonical(lib.dli_fname).string();
    out["pread_calls"] = read_calls;
    out["last_layer_offset_rejected"] = true;
    out["status"] = "PASS_C291_NATIVE_CONSTRUCTOR";
    return out;
}

int main(int argc, char **argv) {
    try {
        check::require(argc == 5, "expected manifest model pack bases");
        std::cout << verify(argv[1], argv[2], argv[3], argv[4]).dump() << "\n";
        return 0;
    } catch (const std::exception &ex) {
        std::cerr << ex.what() << "\n";
        return 1;
    }
}
