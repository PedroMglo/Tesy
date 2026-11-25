// Capture three complete rows via public stock APIs. The controller seals stdin.
#include "arg.h"
#include "common.h"
#include "llama.h"
#include "log.h"

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <iostream>
#include <limits>
#include <memory>
#include <stdexcept>
#include <string>
#include <vector>

static_assert(sizeof(float) == 4 && std::numeric_limits<float>::is_iec559);
static_assert(sizeof(llama_token) == 4);
static constexpr int vocab = 201088;

static void require(bool value, const char * reason) {
    if (!value) {
        throw std::runtime_error(reason);
    }
}

static std::array<llama_token, 18> inputs() {
    std::array<llama_token, 18> ids{};
    const uint16_t one = 1;
    require(*reinterpret_cast<const unsigned char *>(&one) == 1, "little-endian required");
    std::cin.read(reinterpret_cast<char *>(ids.data()), sizeof(ids));
    require(std::cin.gcount() == static_cast<std::streamsize>(sizeof(ids)) && std::cin.peek() == EOF,
            "expected 18 int32 IDs");
    require(std::all_of(ids.begin(), ids.end(), [](llama_token t) { return t >= 0 && t < vocab; }),
            "out-of-vocabulary ID");
    return ids;
}

static void execute(common_params & params, const std::array<llama_token, 18> & ids, FILE * out) {
    auto model = common_init_from_params(params);
    require(model && model->model() && model->context(), "stock initialization failed");
    auto * ctx = model->context();
    require(llama_vocab_n_tokens(llama_model_get_vocab(model->model())) == vocab, "vocabulary");
    require(llama_n_ctx(ctx) == 8192 && llama_n_ubatch(ctx) == 32 && llama_n_batch(ctx) == 256,
            "context geometry");
    require(llama_n_rs_seq(ctx) == 0, "unexpected rollback geometry");
    require(common_context_can_seq_rm(ctx) == COMMON_CONTEXT_SEQ_RM_TYPE_PART, "stock startup probe");
    require(llama_memory_seq_pos_max(llama_get_memory(ctx), 0) == -1, "KV did not clear");
    std::fprintf(stderr, "STOCK_NUMERIC_READY probe=common_context_can_seq_rm\n");
    for (const auto & call : std::array<std::array<int, 2>, 3>{{{0,16},{16,1},{17,1}}}) {
        const int begin = call[0];
        const int count = call[1];
        common_batch batch(ctx);
        for (int i = 0; i < count; ++i) {
            batch.add(ids.at(begin+i), begin+i, 0, i+1 == count);
        }
        require(llama_process(ctx, LLAMA_PROCESS_TYPE_DECODE, batch.get()) == 0, "batch failed");
        const float * row = llama_get_logits_ith(ctx, count-1);
        require(row != nullptr, "missing full row");
        require(std::fwrite(row, sizeof(float), vocab, out) == vocab && std::fflush(out) == 0,
                "could not persist full row");
        require(std::all_of(row, row+vocab, [](float v) { return std::isfinite(v); }), "nonfinite");
        std::fprintf(stderr, "STOCK_NUMERIC_ROW begin=%d count=%d last=%d n=%d\n",
                     begin, count, begin+count-1, vocab);
    }
}

int main(int argc, char ** argv) {
    bool initialized = false;
    try {
        const auto ids = inputs();
        if (argc == 2 && std::strcmp(argv[1], "--check-input") == 0) {
            std::puts("PASS_INPUT_18_INT32");
            return 0;
        }
        require(argc == 3, "usage: stock-numeric MODEL NEW_LOGITS < sealed-18-ids.i32");
        const auto close_file = [](FILE * f) { std::fclose(f); };
        std::unique_ptr<FILE, decltype(close_file)> out(std::fopen(argv[2], "wbx"), close_file);
        require(out != nullptr, "output unavailable or already exists");
        std::vector<std::string> options = {
            "stock-numeric", "-m", argv[1], "-lm", "mmap", "-lzm", "off", "--no-repack",
            "--no-host", "--fit", "off", "-ngl", "99", "-cmoe", "--moe-cache-mib", "2048",
            "--moe-cache-cpu-share", "0", "-c", "8192", "-np", "1", "-b", "256", "-ub", "32",
            "-ctk", "f16", "-ctv", "f16", "--no-warmup", "-lv", "4",
        };
        std::vector<char *> cli;
        for (auto & arg : options) {
            cli.push_back(arg.data());
        }
        cli.push_back(nullptr);
        common_params params;
        common_init();
        require(common_params_parse(static_cast<int>(options.size()), cli.data(), params,
                                    LLAMA_EXAMPLE_SERVER), "stock option parser");
        require(!params.warmup && !params.kv_unified && !params.swa_full &&
                params.moe_cache_size == (2048ULL << 20) && params.moe_cache_cpu_share == 0,
                "unexpected cache/profile");
        llama_backend_init();
        initialized = true;
        llama_numa_init(params.numa);
        execute(params, ids, out.get());
        require(std::fclose(out.release()) == 0, "output close");
        llama_backend_free();
        initialized = false;
        common_log_flush(common_log_main());
        return 0;
    } catch (const std::exception & exc) {
        if (initialized) {
            llama_backend_free();
        }
        std::fprintf(stderr, "STOCK_NUMERIC_FAIL %s\n", exc.what());
        return 1;
    }
}
