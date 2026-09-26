#include "ggml-backend.h"
#include "ggml.h"
#include "gguf.h"
#include "llama.h"

#include <algorithm>
#include <array>
#include <cerrno>
#include <cstdint>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <limits>
#include <set>
#include <stdexcept>
#include <string>
#include <vector>

#include <fcntl.h>
#include <unistd.h>

namespace {

constexpr int expert_count = 128;
constexpr int slot_count = 32;
constexpr int top_k = 4;

struct canonical_slice {
    size_t offset = 0;
    size_t per_expert = 0;
};

struct slot_state {
    std::vector<int32_t> logical;
    std::vector<int32_t> physical;
    std::array<ggml_tensor *, 3> weights{};
    std::array<ggml_tensor *, 3> biases{};
    bool wave = false;
    size_t wave_index = 0;
};

struct capture_state {
    std::filesystem::path root;
    std::string phase;
    bool enabled = false;
    bool all_layers = false;
    size_t bytes = 0;
    size_t count = 0;
    std::string index = "phase\tlayer\tname\ttype\tne\tnb\tbytes\tfile\n";
    std::set<std::string> seen_stages;
    int model_fd = -1;
    std::array<std::array<canonical_slice, 6>, 36> canonical{};
    std::array<slot_state, 36> slots{};
    std::string checked = "phase\tlayer\twave\tlogical\tslot\ttensor\tbytes\tstatus\n";
    size_t checked_slices = 0;
    size_t checked_bytes = 0;
    std::vector<std::string> phases;
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

std::vector<int32_t> ids_from(const ggml_tensor * tensor) {
    check(tensor && tensor->type == GGML_TYPE_I32 && tensor->ne[0] == top_k &&
          tensor->ne[1] >= 1 && tensor->ne[1] <= 32, "invalid routed ID shape");
    std::vector<uint8_t> raw(ggml_nbytes(tensor));
    ggml_backend_tensor_get(tensor, raw.data(), 0, raw.size());
    std::vector<int32_t> out(static_cast<size_t>(top_k*tensor->ne[1]));
    for (int t = 0; t < tensor->ne[1]; ++t) for (int k = 0; k < top_k; ++k) {
        const size_t offset = static_cast<size_t>(t)*tensor->nb[1] + k*tensor->nb[0];
        check(offset + sizeof(int32_t) <= raw.size(), "ID stride out of bounds");
        std::memcpy(&out[static_cast<size_t>(t*top_k+k)], raw.data()+offset, sizeof(int32_t));
    }
    return out;
}

std::vector<float> mask_from(const ggml_tensor * tensor) {
    check(tensor && tensor->type == GGML_TYPE_F32 && tensor->ne[0] == 1 &&
          tensor->ne[1] == top_k && tensor->ne[2] >= 1 && tensor->ne[2] <= 32,
          "invalid wave mask shape");
    std::vector<uint8_t> raw(ggml_nbytes(tensor));
    ggml_backend_tensor_get(tensor, raw.data(), 0, raw.size());
    std::vector<float> out(static_cast<size_t>(top_k*tensor->ne[2]));
    for (int t = 0; t < tensor->ne[2]; ++t) for (int k = 0; k < top_k; ++k) {
        const size_t offset = static_cast<size_t>(t)*tensor->nb[2] + k*tensor->nb[1];
        check(offset + sizeof(float) <= raw.size(), "mask stride out of bounds");
        std::memcpy(&out[static_cast<size_t>(t*top_k+k)], raw.data()+offset, sizeof(float));
        check(out[static_cast<size_t>(t*top_k+k)] == 0.0f ||
              out[static_cast<size_t>(t*top_k+k)] == 1.0f, "invalid wave mask value");
    }
    return out;
}

void pread_exact(int fd, void * data, size_t size, size_t offset) {
    auto * p = static_cast<uint8_t *>(data);
    size_t done = 0;
    while (done < size) {
        const ssize_t n = pread(fd, p+done, size-done, offset+done);
        check(n > 0, "short/error read of canonical GGUF expert slice");
        done += static_cast<size_t>(n);
    }
}

void verify_slots(capture_state & state, int layer, const std::vector<float> & mask) {
    auto & slot = state.slots[static_cast<size_t>(layer)];
    check(!slot.logical.empty() && slot.logical.size() == slot.physical.size() &&
          slot.logical.size() == mask.size(), "route/slot/mask cardinality mismatch");
    for (int kind = 0; kind < 3; ++kind)
        check(slot.weights[kind] && slot.biases[kind], "expert tensor pointer missing");
    std::set<std::array<int32_t, 3>> seen;
    for (size_t i = 0; i < mask.size(); ++i) {
        if (mask[i] == 0.0f) continue;
        const int32_t logical = slot.logical[i], physical = slot.physical[i];
        check(logical >= 0 && logical < expert_count &&
              physical >= 0 && physical < slot_count, "expert/slot ID out of range");
        for (int kind = 0; kind < 3; ++kind) {
            if (!seen.insert({kind,logical,physical}).second) continue;
            for (int bias = 0; bias < 2; ++bias) {
                const int spec_index = kind + (bias ? 3 : 0);
                const canonical_slice & source = state.canonical[static_cast<size_t>(layer)][spec_index];
                ggml_tensor * tensor = bias ? slot.biases[kind] : slot.weights[kind];
                const size_t tensor_index = bias ? static_cast<size_t>(logical) :
                                                  static_cast<size_t>(physical);
                check(source.per_expert > 0 &&
                      ggml_nbytes(tensor) >= (tensor_index+1)*source.per_expert,
                      "consumer tensor slice outside tensor");
                std::vector<uint8_t> observed(source.per_expert);
                std::vector<uint8_t> expected(source.per_expert);
                ggml_backend_tensor_get(tensor,observed.data(),
                                        tensor_index*source.per_expert,source.per_expert);
                pread_exact(state.model_fd,expected.data(),expected.size(),
                            source.offset + static_cast<size_t>(logical)*source.per_expert);
                check(observed == expected, "consumer expert bytes differ from canonical GGUF");
                state.checked += state.phase + "\t" + std::to_string(layer) + "\t" +
                                 std::to_string(slot.wave_index) + "\t" +
                                 std::to_string(logical) + "\t" + std::to_string(physical) +
                                 "\t" + std::to_string(spec_index) + "\t" +
                                 std::to_string(source.per_expert) + "\tEQUAL\n";
                ++state.checked_slices;
                state.checked_bytes += source.per_expert;
            }
        }
    }
    slot.weights = {};
    slot.biases = {};
    ++slot.wave_index;
}

void prepare_canonical(capture_state & state, const char * model) {
    ggml_context * meta = nullptr;
    gguf_init_params params{true, &meta};
    gguf_context * gguf = gguf_init_from_file(model, params);
    check(gguf && meta, "cannot parse canonical GGUF metadata");
    constexpr std::array<const char *, 6> suffix{
        "ffn_gate_exps.weight", "ffn_up_exps.weight", "ffn_down_exps.weight",
        "ffn_gate_exps.bias", "ffn_up_exps.bias", "ffn_down_exps.bias"};
    for (int layer = 0; layer < 36; ++layer) {
        for (int kind = 0; kind < 6; ++kind) {
            const std::string name = "blk." + std::to_string(layer) + "." + suffix[kind];
            const int64_t id = gguf_find_tensor(gguf,name.c_str());
            check(id >= 0, "canonical expert tensor missing");
            const size_t size = gguf_get_tensor_size(gguf,id);
            const size_t per = size/expert_count;
            check(size == per*expert_count &&
                  per == (kind < 3 ? 4406400u : 11520u) &&
                  gguf_get_tensor_type(gguf,id) == (kind < 3 ? GGML_TYPE_MXFP4 : GGML_TYPE_F32),
                  "canonical expert tensor layout mismatch");
            state.canonical[static_cast<size_t>(layer)][kind] = {
                gguf_get_data_offset(gguf) + gguf_get_tensor_offset(gguf,id),per};
        }
    }
    ggml_free(meta);
    gguf_free(gguf);
    state.model_fd = open(model,O_RDONLY|O_CLOEXEC);
    check(state.model_fd >= 0, "cannot open canonical GGUF");
}

bool capture(ggml_tensor * tensor, bool ask, void * user_data) {
    auto & state = *static_cast<capture_state *>(user_data);
    if (!state.enabled) return false;
    const std::string name = tensor->name;
    const auto dash = name.rfind('-');
    if (dash == std::string::npos) return false;
    const std::string stage = name.substr(0, dash);
    const std::string layer = name.substr(dash + 1);
    if (layer.empty() || !std::all_of(layer.begin(),layer.end(),[](char c) { return c >= '0' && c <= '9'; })) return false;
    const int layer_id = std::stoi(layer);
    if (layer_id < 0 || layer_id >= 36 || (!state.all_layers && layer_id != 0 && layer_id != 35)) return false;
    if (ask && stage.rfind("ffn_moe_", 0) == 0) state.seen_stages.insert(stage);
    constexpr std::array<const char *, 16> wanted{
        "attn_post_norm", "ffn_moe_logits", "ffn_moe_logits_biased",
        "ffn_moe_probs", "ffn_moe_topk", "ffn_moe_weights",
        "ffn_moe_weights_softmax", "ffn_moe_topk_stream",
        "ffn_moe_wave_ids", "ffn_moe_wave_mask",
        "ffn_moe_up_biased", "ffn_moe_gate_biased",
        "ffn_moe_down_biased", "ffn_moe_weighted", "ffn_moe_out",
        "ffn_moe_argsort"};
    bool matched = false;
    for (const char * item : wanted) matched |= stage == item;
    if (!matched) return false;
    const bool byte_check = !state.all_layers ||
        ((layer_id == 0 || layer_id == 35) &&
         (state.phase == "prefill0" || state.phase == "decode0"));
    const bool save = !state.all_layers ||
        stage == "attn_post_norm" || stage == "ffn_moe_logits" ||
        stage == "ffn_moe_logits_biased" || stage == "ffn_moe_probs" ||
        stage == "ffn_moe_topk" || stage == "ffn_moe_weights_softmax" ||
        stage == "ffn_moe_topk_stream" || stage == "ffn_moe_wave_ids" ||
        stage == "ffn_moe_wave_mask" || stage == "ffn_moe_out";
    if (!save && !(byte_check &&
        (stage == "ffn_moe_gate_biased" || stage == "ffn_moe_up_biased" ||
         stage == "ffn_moe_down_biased"))) return false;
    if (ask) return true;
    if (save) {
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
    }
    if (!byte_check) return true;
    auto & slot = state.slots[static_cast<size_t>(layer_id)];
    if (stage == "ffn_moe_topk") {
        slot = {};
        slot.logical = ids_from(tensor);
    } else if (stage == "ffn_moe_topk_stream" || stage == "ffn_moe_wave_ids") {
        slot.physical = ids_from(tensor);
        slot.wave = stage == "ffn_moe_wave_ids";
    } else if (stage == "ffn_moe_gate_biased" ||
               stage == "ffn_moe_up_biased" || stage == "ffn_moe_down_biased") {
        const int kind = stage == "ffn_moe_gate_biased" ? 0 :
                         stage == "ffn_moe_up_biased" ? 1 : 2;
        check(tensor->op == GGML_OP_ADD_ID && tensor->src[0] &&
              tensor->src[0]->op == GGML_OP_MUL_MAT_ID && tensor->src[1] &&
              tensor->src[2], "biased expert graph structure changed");
        auto * matmul = tensor->src[0];
        check(ids_from(tensor->src[2]) == slot.logical &&
              ids_from(matmul->src[2]) == slot.physical,
              "logical/physical ID namespace mismatch at consumer");
        slot.weights[kind] = matmul->src[0];
        slot.biases[kind] = tensor->src[1];
        if (kind == 2 && !slot.wave) {
            verify_slots(state,layer_id,std::vector<float>(slot.logical.size(),1.0f));
        }
    } else if (stage == "ffn_moe_wave_mask") {
        check(slot.wave, "wave mask without wave IDs");
        verify_slots(state,layer_id,mask_from(tensor));
    }
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
    if (argc != 5 && argc != 6) {
        std::cerr << "usage: c3_boundary_capture MODEL.gguf IDS.tsv CASE OUTPUT_DIR [--all-layers]\n";
        return 2;
    }
    try {
        const auto prompt = ids_for(argv[2], argv[3], false);
        const auto continuation = ids_for(argv[2], argv[3], true);
        const bool all_layers = argc == 6 && std::strcmp(argv[5],"--all-layers") == 0;
        check(argc == 5 || all_layers, "unknown capture mode");
        check(prompt.size() >= 32 && prompt.size() + continuation.size() <= 4096 &&
              (!all_layers || (prompt.size() >= 160 && continuation.size() >= 32)),
              "token count outside frozen context/batch");
        capture_state state;
        state.root = argv[4];
        state.all_layers = all_layers;
        check(std::filesystem::create_directory(state.root), "output root already exists");
        prepare_canonical(state,argv[1]);
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
        const int vocab = llama_vocab_n_tokens(llama_model_get_vocab(model));
        check(vocab == 201088, "target vocabulary changed");
        const int final_prompt_start = ((static_cast<int>(prompt.size()) - 1)/32)*32;
        for (int off = 0; off < static_cast<int>(prompt.size()); off += 32) {
            state.enabled = off == 0 || (all_layers && (off == 128 || off == final_prompt_start));
            state.phase = off == 0 ? "prefill0" : off == 128 ? "prefill128" : "prefill_final";
            decode(ctx,prompt,off,off,std::min(32,static_cast<int>(prompt.size())-off));
            if (state.enabled) {
                const float * logits = llama_get_logits(ctx);
                check(logits != nullptr, "prefill logits unavailable");
                write_new(state.root / (state.phase + ".logits.f32"),logits,
                          static_cast<size_t>(vocab)*sizeof(float));
                state.phases.push_back(state.phase);
                std::cout << "captured=" << state.phase << " tensors=" << state.count << "\n" << std::flush;
            }
            state.enabled = false;
        }
        const int decode_count = all_layers ? 32 : 1;
        for (int i = 0; i < decode_count; ++i) {
            state.enabled = i == 0 || (all_layers && (i == 1 || i == 7 || i == 31));
            state.phase = "decode" + std::to_string(i);
            std::vector<llama_token> token{continuation[static_cast<size_t>(i)]};
            decode(ctx, token, 0, static_cast<int>(prompt.size()) + i, 1);
            if (state.enabled) {
                const float * logits = llama_get_logits(ctx);
                check(logits != nullptr, "decode logits unavailable");
                write_new(state.root / (state.phase + ".logits.f32"),logits,
                          static_cast<size_t>(vocab)*sizeof(float));
                state.phases.push_back(state.phase);
                std::cout << "captured=" << state.phase << " tensors=" << state.count << "\n" << std::flush;
            }
            state.enabled = false;
        }
        write_new(state.root / "index.tsv", state.index.data(), state.index.size());
        write_new(state.root / "byte_checks.tsv", state.checked.data(), state.checked.size());
        std::string phases;
        for (const auto & phase : state.phases) phases += phase + "\n";
        write_new(state.root / "phases.txt",phases.data(),phases.size());
        std::string stages;
        for (const auto & name : state.seen_stages) stages += name + "\n";
        write_new(state.root / "stages.txt", stages.data(), stages.size());
        std::cout << "capture_tensors=" << state.count << " bytes=" << state.bytes
                  << " checked_slices=" << state.checked_slices
                  << " checked_bytes=" << state.checked_bytes
                  << " prompt_ids=" << prompt.size() << " continuation_ids="
                  << continuation.size() << "\n";
        llama_free(ctx);
        llama_model_free(model);
        llama_backend_free();
        close(state.model_fd);
        return 0;
    } catch (const std::exception & exc) {
        std::cerr << "C3_CAPTURE_FAIL: " << exc.what() << "\n";
        return 1;
    }
}
