#include "ggml-backend.h"
#include "ggml.h"
#include "llama.h"

#include <algorithm>
#include <array>
#include <cerrno>
#include <cstdint>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

#include <fcntl.h>
#include <unistd.h>

namespace {

struct capture_state {
    std::filesystem::path root;
    std::string phase;
    bool enabled = false;
    size_t bytes = 0;
    size_t count = 0;
    std::string index = "phase\tlayer\tname\ttype\tne\tnb\tbytes\tfile\n";
};

void check(bool ok, const std::string & message) {
    if (!ok) throw std::runtime_error(message);
}

void write_new(const std::filesystem::path & path, const void * data, size_t size) {
    int fd = open(path.c_str(), O_WRONLY | O_CREAT | O_EXCL, 0600);
    check(fd >= 0, "cannot create " + path.string() + ": " + std::strerror(errno));
    const auto * p = static_cast<const uint8_t *>(data);
    while (size > 0) {
        const ssize_t n = write(fd, p, size);
        if (n <= 0) { close(fd); throw std::runtime_error("short write: " + path.string()); }
        p += n;
        size -= static_cast<size_t>(n);
    }
    check(close(fd) == 0, "close failed: " + path.string());
}

std::string dims(const size_t * values) {
    std::string out;
    for (int i = 0; i < GGML_MAX_DIMS; ++i) {
        if (i) out += ',';
        out += std::to_string(values[i]);
    }
    return out;
}

std::string shape(const ggml_tensor * t) {
    std::string out;
    for (int i = 0; i < GGML_MAX_DIMS; ++i) {
        if (i) out += ',';
        out += std::to_string(t->ne[i]);
    }
    return out;
}

bool capture(ggml_tensor * tensor, bool ask, void * user_data) {
    auto & state = *static_cast<capture_state *>(user_data);
    if (!state.enabled) return false;
    const std::string name = tensor->name;
    const auto dash = name.rfind('-');
    if (dash == std::string::npos) return false;
    const std::string stage = name.substr(0, dash);
    const std::string layer = name.substr(dash + 1);
    if (layer != "0" && layer != "35") return false;
    constexpr std::array<const char *, 9> wanted{
        "attn_post_norm", "ffn_moe_logits_biased", "ffn_moe_topk",
        "ffn_moe_weights_softmax", "ffn_moe_topk_stream",
        "ffn_moe_up_biased", "ffn_moe_gate_biased",
        "ffn_moe_down_biased", "ffn_moe_out"};
    bool matched = false;
    for (const char * item : wanted) matched |= stage == item;
    if (!matched) return false;
    if (ask) return true;
    const size_t size = ggml_nbytes(tensor);
    check(size > 0 && size <= 64u*1024u*1024u, "capture tensor size outside bound");
    check(state.bytes + size <= 256u*1024u*1024u, "capture volume bound exceeded");
    std::vector<uint8_t> data(size);
    ggml_backend_tensor_get(tensor, data.data(), 0, size);
    const std::string file = state.phase + "_" + layer + "_" + stage + "_" +
                             std::to_string(state.count++) + ".bin";
    write_new(state.root / file, data.data(), data.size());
    state.bytes += size;
    state.index += state.phase + "\t" + layer + "\t" + stage + "\t" +
                   ggml_type_name(tensor->type) + "\t" + shape(tensor) + "\t" +
                   dims(tensor->nb) + "\t" + std::to_string(size) + "\t" + file + "\n";
    return true;
}

std::vector<llama_token> ids_for(const std::string & file, const std::string & selected,
                                 bool continuation) {
    std::ifstream in(file);
    check(bool(in), "cannot open token IDs");
    std::string line;
    while (std::getline(in, line)) {
        const size_t first = line.find('\t');
        const size_t second = first == std::string::npos ? first : line.find('\t', first + 1);
        if (first == std::string::npos || second == std::string::npos ||
            line.substr(0, first) != selected) continue;
        const std::string text = continuation ? line.substr(second + 1) :
                                                line.substr(first + 1, second - first - 1);
        std::vector<llama_token> ids;
        size_t pos = 0;
        while (pos < text.size()) {
            size_t end = text.find(',', pos);
            const std::string item = text.substr(pos, end == std::string::npos ? end : end - pos);
            check(!item.empty(), "empty token ID");
            ids.push_back(static_cast<llama_token>(std::stol(item)));
            if (end == std::string::npos) break;
            pos = end + 1;
        }
        check(!ids.empty(), "empty token sequence");
        return ids;
    }
    throw std::runtime_error("case missing from token IDs: " + selected);
}

void decode(llama_context * ctx, const std::vector<llama_token> & ids,
            int id_offset, int position_offset, int count) {
    llama_batch batch = llama_batch_init(count, 0, 1);
    for (int i = 0; i < count; ++i) {
        batch.token[i] = ids[static_cast<size_t>(id_offset + i)];
        batch.pos[i] = position_offset + i;
        batch.n_seq_id[i] = 1;
        batch.seq_id[i][0] = 0;
        batch.logits[i] = i == count - 1;
    }
    batch.n_tokens = count;
    const int rc = llama_decode(ctx, batch);
    llama_batch_free(batch);
    check(rc == 0, "llama_decode failed");
}

} // namespace

int main(int argc, char ** argv) {
    if (argc != 5) {
        std::cerr << "usage: c3_boundary_capture MODEL.gguf IDS.tsv CASE OUTPUT_DIR\n";
        return 2;
    }
    try {
        const auto prompt = ids_for(argv[2], argv[3], false);
        const auto continuation = ids_for(argv[2], argv[3], true);
        check(prompt.size() >= 32 && prompt.size() + continuation.size() <= 4096,
              "token count outside frozen context/batch");
        capture_state state;
        state.root = argv[4];
        check(std::filesystem::create_directory(state.root), "output root already exists");
        llama_backend_init();
        auto mp = llama_model_default_params();
        mp.n_gpu_layers = 8;
        mp.use_mmap = false;
        mp.use_direct_io = true;
        mp.use_extra_bufts = false;
        mp.moe_stream = true;
        mp.moe_stream_slots = 32;
        mp.moe_stream_io_threads = 4;
        mp.moe_stream_direct = true;
        llama_model * model = llama_model_load_from_file(argv[1], mp);
        check(model != nullptr, "model load failed");
        auto cp = llama_context_default_params();
        cp.n_ctx = 4096;
        cp.n_batch = 256;
        cp.n_ubatch = 32;
        cp.n_seq_max = 1;
        cp.n_threads = 8;
        cp.n_threads_batch = 8;
        cp.op_offload = false;
        cp.cb_eval = capture;
        cp.cb_eval_user_data = &state;
        llama_context * ctx = llama_init_from_model(model, cp);
        check(ctx != nullptr, "context init failed");
        state.phase = "prefill0";
        state.enabled = true;
        decode(ctx, prompt, 0, 0, 32);
        state.enabled = false;
        for (int off = 32; off < static_cast<int>(prompt.size()); off += 32) {
            decode(ctx, prompt, off, off, std::min(32, static_cast<int>(prompt.size()) - off));
        }
        state.phase = "decode0";
        state.enabled = true;
        std::vector<llama_token> token{continuation[0]};
        decode(ctx, token, 0, static_cast<int>(prompt.size()), 1);
        state.enabled = false;
        write_new(state.root / "index.tsv", state.index.data(), state.index.size());
        std::cout << "capture_tensors=" << state.count << " bytes=" << state.bytes
                  << " prompt_ids=" << prompt.size() << " continuation_ids="
                  << continuation.size() << "\n";
        llama_free(ctx);
        llama_model_free(model);
        llama_backend_free();
        return 0;
    } catch (const std::exception & exc) {
        std::cerr << "C3_CAPTURE_FAIL: " << exc.what() << "\n";
        return 1;
    }
}
