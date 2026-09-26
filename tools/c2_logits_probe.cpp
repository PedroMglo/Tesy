// C2 fixed-token teacher forcing using llama.cpp's own tokenizer, graph, KV and router.
// No Transformer arithmetic or routing is implemented here.
#include "llama.h"

#include <algorithm>
#include <cerrno>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <fcntl.h>
#include <fstream>
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <string>
#include <unistd.h>
#include <vector>

struct Case {
    std::string name;
    std::vector<llama_token> prompt;
    std::vector<llama_token> continuation;
};

static void write_all(int fd, const void * ptr, size_t size) {
    const auto * bytes = static_cast<const char *>(ptr);
    while (size) {
        const auto n = ::write(fd, bytes, size);
        if (n <= 0) throw std::runtime_error(std::string("write failed: ") + std::strerror(errno));
        bytes += n;
        size -= static_cast<size_t>(n);
    }
}

static int new_file(const std::string & name) {
    const int fd = ::open(name.c_str(), O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC, 0600);
    if (fd < 0) throw std::runtime_error("output exists or cannot be opened: " + name);
    return fd;
}

static std::vector<std::string> fields(const std::string & line) {
    std::vector<std::string> out;
    std::stringstream stream(line);
    std::string field;
    while (std::getline(stream, field, '\t')) out.push_back(field);
    return out;
}

static std::vector<llama_token> tokenize(const llama_vocab * vocab, const std::string & text, bool special) {
    int size = std::max<int>(256, text.size() * 2);
    std::vector<llama_token> ids(size);
    int n = llama_tokenize(vocab, text.c_str(), text.size(), ids.data(), ids.size(), special, true);
    if (n < 0) {
        ids.resize(-n);
        n = llama_tokenize(vocab, text.c_str(), text.size(), ids.data(), ids.size(), special, true);
    }
    if (n <= 0 || n > static_cast<int>(ids.size())) throw std::runtime_error("tokenization failed");
    ids.resize(n);
    return ids;
}

static std::string csv(const std::vector<llama_token> & tokens) {
    std::ostringstream out;
    for (size_t i = 0; i < tokens.size(); ++i) {
        if (i) out << ',';
        out << tokens[i];
    }
    return out.str();
}

static std::vector<llama_token> parse_csv(const std::string & text) {
    std::vector<llama_token> out;
    std::stringstream stream(text);
    std::string item;
    while (std::getline(stream, item, ',')) {
        if (item.empty()) throw std::runtime_error("empty token ID");
        size_t used = 0;
        const long n = std::stol(item, &used);
        if (used != item.size() || n < 0 || n > INT32_MAX) throw std::runtime_error("bad token ID");
        out.push_back(static_cast<llama_token>(n));
    }
    if (out.empty()) throw std::runtime_error("missing tokens");
    return out;
}

static std::vector<Case> read_ids(const std::string & path) {
    std::ifstream input(path);
    if (!input) throw std::runtime_error("cannot read token ID file");
    std::vector<Case> cases;
    std::string line;
    while (std::getline(input, line)) {
        auto parts = fields(line);
        if (parts.size() != 3 || parts[0].empty()) throw std::runtime_error("bad ID row");
        for (const auto & c : cases) if (c.name == parts[0]) throw std::runtime_error("duplicate case");
        cases.push_back({parts[0], parse_csv(parts[1]), parse_csv(parts[2])});
    }
    if (cases.empty()) throw std::runtime_error("no cases");
    return cases;
}

static void capture(llama_context * ctx, int vocab, int fd, std::string & index,
                    const std::string & name, const std::string & phase, int position, size_t & rows) {
    float * logits = llama_get_logits_ith(ctx, -1);
    if (!logits) throw std::runtime_error("missing logits");
    for (int i = 0; i < vocab; ++i) if (!std::isfinite(logits[i])) throw std::runtime_error("nonfinite logits");
    write_all(fd, logits, static_cast<size_t>(vocab) * sizeof(float));
    index += name + '\t' + phase + '\t' + std::to_string(position) + '\t' + std::to_string(rows) + '\n';
    ++rows;
}

static void decode(llama_context * ctx, const std::vector<llama_token> & ids, int offset, int count) {
    llama_batch batch = llama_batch_init(count, 0, 1);
    for (int i = 0; i < count; ++i) {
        batch.token[i] = ids[offset+i];
        batch.pos[i] = offset+i;
        batch.n_seq_id[i] = 1;
        batch.seq_id[i][0] = 0;
        batch.logits[i] = i == count-1;
    }
    batch.n_tokens = count;
    const int rc = llama_decode(ctx, batch);
    llama_batch_free(batch);
    if (rc != 0) throw std::runtime_error("llama_decode failed: " + std::to_string(rc));
}

int main(int argc, char ** argv) {
    try {
        const uint32_t endian_test = 1;
        if (*reinterpret_cast<const uint8_t *>(&endian_test) != 1 || sizeof(float) != 4)
            throw std::runtime_error("requires little-endian float32 host");
        if (argc == 5 && std::string(argv[1]) == "tokenize") {
            llama_backend_init();
            auto mp = llama_model_default_params();
            mp.vocab_only = true;
            llama_model * model = llama_model_load_from_file(argv[2], mp);
            if (!model) throw std::runtime_error("vocabulary-only model load failed");
            const llama_vocab * vocab = llama_model_get_vocab(model);
            std::ifstream input(argv[3]);
            if (!input) throw std::runtime_error("cannot open prompt TSV");
            std::string output, line;
            while (std::getline(input, line)) {
                auto parts = fields(line);
                if (parts.size() != 3) throw std::runtime_error("prompt TSV needs 3 columns");
                auto prompt = tokenize(vocab, parts[1], true);
                auto continuation = tokenize(vocab, parts[2], false);
                output += parts[0] + '\t' + csv(prompt) + '\t' + csv(continuation) + '\n';
                std::cout << parts[0] << " prompt=" << prompt.size() << " continuation=" << continuation.size() << '\n';
            }
            const int fd = new_file(argv[4]);
            write_all(fd, output.data(), output.size());
            ::close(fd);
            llama_model_free(model);
            llama_backend_free();
            return 0;
        }
        if (argc != 10 || std::string(argv[1]) != "run") {
            std::cerr << "usage: c2_logits_probe tokenize MODEL PROMPTS.tsv IDS.tsv\n"
                      << "   or: c2_logits_probe run MODEL plain|stream N_GPU IDS.tsv OUTPUT_PREFIX SLOTS UBATCH CASE|all\n";
            return 2;
        }
        const bool streaming = std::string(argv[3]) == "stream";
        if (!streaming && std::string(argv[3]) != "plain") throw std::runtime_error("mode must be plain/stream");
        const int gpu = std::stoi(argv[4]), slots = std::stoi(argv[7]), ubatch = std::stoi(argv[8]);
        if (gpu < 0 || gpu > 36 || slots < 12 || slots > 128 || ubatch < 1 || ubatch > 256)
            throw std::runtime_error("invalid placement/cache/batch");
        auto cases = read_ids(argv[5]);
        const std::string selected = argv[9];
        if (selected != "all") {
            cases.erase(std::remove_if(cases.begin(), cases.end(), [&](const Case & c){return c.name != selected;}), cases.end());
            if (cases.size() != 1) throw std::runtime_error("unknown case selection");
        }
        const std::string prefix = argv[6];
        const int fd = new_file(prefix + ".f32");
        llama_backend_init();
        auto mp = llama_model_default_params();
        mp.n_gpu_layers = gpu;
        mp.use_mmap = !streaming;
        mp.use_direct_io = streaming;
        mp.use_extra_bufts = false;
        mp.moe_stream = streaming;
        mp.moe_stream_slots = slots;
        mp.moe_stream_io_threads = 4;
        mp.moe_stream_direct = streaming;
        llama_model * model = llama_model_load_from_file(argv[2], mp);
        if (!model) throw std::runtime_error("model load failed");
        auto cp = llama_context_default_params();
        cp.n_ctx = 4096; cp.n_batch = 256; cp.n_ubatch = ubatch; cp.n_seq_max = 1;
        cp.n_threads = 8; cp.n_threads_batch = 8; cp.op_offload = false;
        llama_context * ctx = llama_init_from_model(model, cp);
        if (!ctx) throw std::runtime_error("context init failed");
        const int vocab = llama_vocab_n_tokens(llama_model_get_vocab(model));
        std::string index = "case\tphase\tposition\trow\n";
        size_t rows = 0;
        for (const auto & c : cases) {
            llama_memory_clear(llama_get_memory(ctx), true);
            const int n_prompt = c.prompt.size();
            const int n_cont = c.continuation.size();
            if (n_prompt + n_cont > 4096) throw std::runtime_error("context overflow");
            for (int off = 0; off < n_prompt; off += ubatch) {
                const int count = std::min(ubatch, n_prompt-off);
                decode(ctx, c.prompt, off, count);
                capture(ctx, vocab, fd, index, c.name, "prompt", off+count-1, rows);
            }
            for (int i = 0; i < n_cont; ++i) {
                // Explicit absolute positions keep the same prefix/KV semantics on both paths.
                std::vector<llama_token> one{c.continuation[i]};
                llama_batch batch = llama_batch_init(1, 0, 1);
                batch.token[0] = one[0]; batch.pos[0] = n_prompt+i;
                batch.n_seq_id[0] = 1; batch.seq_id[0][0] = 0; batch.logits[0] = 1;
                batch.n_tokens = 1;
                const int rc = llama_decode(ctx, batch);
                llama_batch_free(batch);
                if (rc != 0) throw std::runtime_error("incremental decode failed: " + std::to_string(rc));
                capture(ctx, vocab, fd, index, c.name, "continuation", n_prompt+i, rows);
            }
            std::cout << c.name << " prompt=" << n_prompt << " continuation=" << n_cont
                      << " complete_rows=" << rows << std::endl;
        }
        ::close(fd);
        const int index_fd = new_file(prefix + ".rows.tsv");
        write_all(index_fd, index.data(), index.size());
        ::close(index_fd);
        std::cout << "vocab=" << vocab << " rows=" << rows << " float32_endian=little" << std::endl;
        if (streaming) llama_moe_stream_print_stats(model);
        llama_free(ctx);
        llama_model_free(model);
        llama_backend_free();
        return 0;
    } catch (const std::exception & exc) {
        std::cerr << "C2_PROBE_ERROR: " << exc.what() << '\n';
        return 1;
    }
}
