// Reproduce the ordered chat choices and usage for a witness, with the C281 server DSO.
// The caller authenticates the zero-tensor GGUF, DSOs, raw request and observed event projection.
#include "gguf.h"
#include "server-task.h"

#include <algorithm>
#include <filesystem>
#include <iostream>
#include <memory>
#include <set>
#include <stdexcept>

namespace {
void gate(bool value, const char *message) {
    if (!value) throw std::runtime_error(message);
}

using Model = std::unique_ptr<llama_model, decltype(&llama_model_free)>;

Model vocabulary(const char *path) {
    gate(std::filesystem::file_size(path) == 12980384, "metadata size");
    std::unique_ptr<gguf_context, decltype(&gguf_free)> header(
        gguf_init_from_file(path, {true, nullptr}), gguf_free);
    gate(header && gguf_get_n_tensors(header.get()) == 0 && gguf_get_n_kv(header.get()) == 36,
         "metadata geometry");
    header.reset();
    auto params = llama_model_default_params();
    ggml_backend_dev_t empty[] = {nullptr};
    params.devices = empty;
    params.n_gpu_layers = 0;
    params.vocab_only = true;
    params.use_extra_bufts = false;
    params.use_mlock = false;
    params.use_mmap = false;
    return Model(llama_model_load_from_file(path, params), llama_model_free);
}

struct Grammar {
    common_chat_parser_params parser;
    std::set<llama_token> preserved;
};

Grammar grammar(const llama_model *model, const llama_vocab *vocab) {
    auto templ = common_chat_templates_init(model, "");
    common_chat_templates_inputs in;
    // gpt-oss builds its PEG from the template, tools, continuation and reasoning settings.
    // A neutral exemplar suffices to obtain the identical assistant prefix and no-tools PEG.
    common_chat_msg user;
    user.role = "user";
    user.content = "x";
    in.messages = {user};
    in.reasoning_format = COMMON_REASONING_FORMAT_DEEPSEEK;
    in.chat_template_kwargs["reasoning_effort"] = "\"medium\"";
    in.now = std::chrono::system_clock::from_time_t(1791158400); // 2026-10-05
    const auto chat = common_chat_templates_apply(templ.get(), in);
    gate(chat.format == COMMON_CHAT_FORMAT_PEG_NATIVE && chat.generation_prompt == "<|start|>assistant"
         && chat.grammar.empty() && !chat.parser.empty() && chat.additional_stops.empty(), "PEG profile");
    Grammar g;
    g.parser = common_chat_parser_params(chat);
    g.parser.parser.load(chat.parser);
    g.parser.reasoning_format = COMMON_REASONING_FORMAT_DEEPSEEK;
    const std::set<std::string> controls = {
        "<|channel|>", "<|constrain|>", "<|message|>", "<|start|>", "<|end|>"
    };
    gate(std::set<std::string>(chat.preserved_tokens.begin(),chat.preserved_tokens.end()) == controls,
         "preserved token names");
    for (const auto &piece : controls) {
        const auto ids = common_tokenize(vocab, piece, false, true);
        gate(ids.size() == 1 && common_token_to_piece(vocab, ids.front(), true) == piece,
             "preserved token geometry");
        g.preserved.insert(ids.front());
    }
    gate(g.preserved.size() == controls.size(), "distinct preserved IDs");
    return g;
}

// Keep the full ordered choices, finish_reason, and usage. Transport framing and
// independently variable metadata (clock, request identifiers and timings) are external.
void append_projection(json &out, const json &chunks) {
    for (const auto &item : chunks) {
        json event = {{"choices", item.at("choices")}};
        if (item.contains("usage")) event["usage"] = item.at("usage");
        out.push_back(event);
    }
}

json chat_delta(const json &delta, const json &finish) {
    return {{"choices", json::array({{{"finish_reason", finish}, {"index", 0}, {"delta", delta}}})}};
}

json expected(const json &input) {
    const auto reasoning = input.at("reasoning_deltas").get<std::vector<std::string>>();
    const auto final = input.at("final_deltas").get<std::vector<std::string>>();
    gate(reasoning.size() == 35 && final.size() == 2, "observed delta geometry");
    json out = json::array();
    out.push_back(chat_delta({{"role", "assistant"}, {"content", nullptr}}, nullptr));
    for (const auto &s : reasoning) out.push_back(chat_delta({{"reasoning_content", s}}, nullptr));
    for (const auto &s : final) out.push_back(chat_delta({{"content", s}}, nullptr));
    out.push_back(chat_delta(json::object(), "stop"));
    out.push_back({{"choices",json::array()}, {"usage",{
        {"completion_tokens",47}, {"prompt_tokens",2197}, {"total_tokens",2244},
        {"prompt_tokens_details",{{"cached_tokens",2044}}}
    }}});
    return out;
}

bool matches(const llama_vocab *v, const Grammar &g, const llama_tokens &ids, const json &expected) {
    task_result_state state(g.parser);
    json out = json::array();
    std::string accumulated;
    size_t sent = 0;
    for (size_t i = 0; i < ids.size(); ++i) {
        // C269 server-context.cpp::process_token, unrestricted stream with zero stop strings.
        accumulated += common_token_to_piece(v, ids[i], g.preserved.count(ids[i]) != 0);
        if (validate_utf8(accumulated) != accumulated.size()) continue;
        server_task_result_cmpl_partial part{};
        part.res_type = TASK_RESPONSE_TYPE_OAI_CHAT;
        part.index = 0;
        part.n_decoded = static_cast<int>(i + 1);
        part.content = accumulated.substr(sent);
        part.tokens = {ids[i]};
        sent = accumulated.size();
        part.update(state);
        append_projection(out, part.to_json());
    }
    server_task_result_cmpl_final final{};
    final.res_type = TASK_RESPONSE_TYPE_OAI_CHAT;
    final.index = 0;
    final.stream = true;
    final.include_usage = true;
    final.stop = STOP_TYPE_EOS;
    final.n_decoded = static_cast<int>(ids.size());
    final.n_prompt_tokens = 2197;
    final.n_prompt_tokens_cache = 2044;
    final.update(state);
    append_projection(out, final.to_json());
    return out == expected;
}
} // namespace

int main(int argc, char **argv) {
    try {
        gate(argc == 2, "usage: witness VOCAB_ONLY_GGUF");
        json input;
        std::cin >> input;
        auto ids = input.at("ids").get<llama_tokens>();
        gate(ids.size() == 47, "candidate length");
        auto model = vocabulary(argv[1]);
        gate(model != nullptr, "vocab-only load");
        const auto *v = llama_model_get_vocab(model.get());
        gate(v && llama_vocab_n_tokens(v) == 201088, "vocabulary cardinality");
        for (size_t i = 0; i < ids.size(); ++i) {
            gate(ids[i]>=0 && ids[i]<201088, "candidate ID range");
            if (llama_vocab_is_eog(v, ids[i]) != (i+1 == ids.size())) {
                std::cout << R"({"status":"REJECT_PROJECTED_STREAM","eog_ids":[]})" << '\n';
                return 0;
            }
        }
        auto g = grammar(model.get(), v);
        const json observation = expected(input);
        llama_tokens compatible;
        int tested = 0;
        for (llama_token t = 0; t < llama_vocab_n_tokens(v); ++t) {
            if (!llama_vocab_is_eog(v,t)) continue;
            tested++;
            ids.back() = t;
            if (matches(v,g,ids,observation)) compatible.push_back(t);
        }
        gate(tested > 0, "empty EOG inventory");
        json result = {{"status", compatible.empty() ? "REJECT_PROJECTED_STREAM" : "PASS_REAL_C269_PEG_WITNESS"},
                       {"eog_ids",compatible},{"eog_tested",tested},{"vocab_size",201088},{"sample_count",47},
                       {"reasoning_deltas",35},{"final_deltas",2},{"chat_events",observation.size()}};
        std::cout << result.dump() << '\n';
        return std::cout ? 0 : 1;
    } catch (const std::exception &) {
        // No private strings, token IDs or candidate contents in diagnostics.
        std::cerr << "C269 witness input, linkage or profile gate failed\n";
        return 1;
    }
}
