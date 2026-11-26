// Private input on stdin. Only counts, first differing indices and gates leave this process.
#include "chat.h"
#include "llama.h"
#include "nlohmann/json.hpp"

#include <algorithm>
#include <fstream>
#include <iostream>
#include <memory>
#include <set>

struct Gate : std::runtime_error { using std::runtime_error::runtime_error; };

static void require(bool ok, const char *why) {
    if (!ok) throw Gate(why);
}

template<class A, class B> static long difference(const A &a, const B &b) {
    const size_t n = std::min(a.size(), b.size());
    size_t i = 0;
    while (i < n && a[i] == b[i]) ++i;
    return i == n && a.size() == b.size() ? -1 : static_cast<long>(i);
}

static bool valid_utf8(const std::string &s) {
    try { (void)json(s).dump(); return true; }
    catch (const json::type_error &) { return false; }
}

static bool terminal(const llama_vocab *v, const std::vector<llama_token> &ids) {
    if (ids.empty()) return false;
    for (size_t i = 0; i < ids.size(); ++i)
        if (ids[i] < 0 || ids[i] >= llama_vocab_n_tokens(v) ||
            llama_vocab_is_eog(v, ids[i]) != (i + 1 == ids.size())) return false;
    return true;
}

static json check_turn(const llama_model *m, const common_chat_templates *t, const json &row) {
    const auto *v = llama_model_get_vocab(m);
    common_chat_templates_inputs in;
    in.use_jinja = true;
    in.reasoning_format = COMMON_REASONING_FORMAT_DEEPSEEK;
    in.messages = common_chat_msgs_parse_oaicompat(row.at("messages"));
    in.chat_template_kwargs["reasoning_effort"] = "\"medium\"";
    in.chat_template_kwargs["tesy_template_date"] = "\"2026-10-05\"";
    const auto chat = common_chat_templates_apply(t, in);
    require(chat.format == COMMON_CHAT_FORMAT_PEG_NATIVE && chat.generation_prompt == "<|start|>assistant" &&
            chat.grammar.empty() && chat.additional_stops.empty() && !chat.parser.empty(), "PEG contract");
    const std::set<std::string> markers{"<|start|>", "<|channel|>", "<|constrain|>", "<|message|>", "<|end|>"};
    require(std::set<std::string>(chat.preserved_tokens.begin(), chat.preserved_tokens.end()) == markers, "markers");
    std::set<llama_token> preserved;
    for (const auto &s : markers) {
        const auto id = common_tokenize(v, s, false, true);
        require(id.size() == 1 && llama_token_to_piece(m, id[0], true) == s, "marker encoding");
        preserved.insert(id[0]);
    }
    const auto expected = row.at("official_ids").get<std::vector<llama_token>>();
    const auto prompt = row.at("rendered_prompt").get<std::string>();
    const auto tokens = common_tokenize(v, chat.prompt, false, true);
    const auto direct = common_tokenize(v, prompt, false, true);
    in.chat_template_kwargs["tesy_template_date"] = "\"2026-10-06\"";
    const auto other = common_chat_templates_apply(t, in).prompt;
    std::string shifted = chat.prompt;
    const std::string day = "Current date: 2026-10-05";
    const auto pos = shifted.find(day);
    bool date_control = pos != std::string::npos;
    if (date_control) {
        shifted.replace(pos, day.size(), "Current date: 2026-10-06");
        date_control = other == shifted && common_tokenize(v, other, false, true) != tokens;
    }

    common_chat_parser_params params(chat);
    params.reasoning_format = in.reasoning_format;
    params.parse_tool_calls = false;
    params.parser.load(chat.parser);
    const auto sampled = row.at("sampled").get<std::vector<llama_token>>();
    require(terminal(v, sampled) && sampled.size() > 1, "terminal EOG");
    auto mutant = sampled;
    std::swap(mutant.front(), mutant.back());
    require(!terminal(v, mutant), "early EOG control");
    common_chat_msg previous;
    json deltas = json::array();
    std::string text;
    size_t withheld = 0;
    auto parse = [&](bool partial) {
        const auto next = common_chat_parse(text, partial, params);
        require(next.tool_calls.empty(), "unexpected tool call");
        if (next.empty()) return;
        for (const auto &diff : common_chat_msg_diff::compute_diffs(previous, next)) {
            require(diff.tool_call_index == std::string::npos, "unexpected tool delta");
            json projected = json::object();
            if (!diff.reasoning_content_delta.empty()) projected["reasoning_content"] = diff.reasoning_content_delta;
            if (!diff.content_delta.empty()) projected["content"] = diff.content_delta;
            if (!projected.empty()) deltas.push_back(projected);
        }
        previous = next;
    };
    for (const auto id : sampled) {
        if (!llama_vocab_is_eog(v, id)) text += llama_token_to_piece(m, id, preserved.count(id));
        if (valid_utf8(text)) parse(true);
        else ++withheld;
    }
    require(valid_utf8(text), "terminal UTF-8");
    parse(false);
    return {{"prompt_bytes",chat.prompt.size()},{"prompt_tokens",tokens.size()},{"sampled",sampled.size()},
            {"render_difference",difference(chat.prompt,prompt)},{"ids_difference",difference(tokens,expected)},
            {"direct_ids_difference",difference(direct,expected)},{"date_control",date_control},{"early_eog_rejected",true},
            {"channel_updates",deltas.size()},{"delta_difference",difference(deltas,row.at("deltas"))},
            {"reasoning_equal",!previous.reasoning_content.empty() && previous.reasoning_content==row.at("message").at("reasoning_content")},
            {"final_equal",!previous.content.empty() && previous.content==row.at("message").at("content")},
            {"incomplete_utf8_steps",withheld}};
}

int main(int argc, char **argv) {
    const char *stage = "arguments";
    try {
        require(argc == 3, "arguments");
        require(std::ifstream(argv[1], std::ios::binary | std::ios::ate).tellg() == 12980384, "vocab size");
        std::ifstream source(argv[2], std::ios::binary);
        const std::string bound{std::istreambuf_iterator<char>(source), {}};
        stage = "vocabulary";
        llama_backend_init();
        auto p = llama_model_default_params();
        p.vocab_only = true;
        p.n_gpu_layers = 0;
        p.use_mmap = false;
        using Model = std::unique_ptr<llama_model, decltype(&llama_free_model)>;
        Model model(llama_model_load_from_file(argv[1], p), llama_free_model);
        require(model && llama_vocab_n_tokens(llama_model_get_vocab(model.get())) == 201088, "BPE inventory");
        stage = "template";
        const char *embedded = llama_model_chat_template(model.get(), nullptr);
        require(embedded && !bound.empty(), "embedded template");
        std::string orig(embedded);
        const std::string expr = "strftime_now(\"%Y-%m-%d\")";
        auto start = orig.find(expr);
        require(start != std::string::npos && orig.find(expr,start+1) == std::string::npos, "date expression");
        orig.replace(start, expr.size(), "tesy_template_date");
        require(orig == bound, "dated template");
        const auto templates = common_chat_templates_init(model.get(), bound);
        json request;
        std::cin >> request;
        require(request.size() == 2, "turns");
        json result = json::array();
        for (size_t i = 0; i < request.size(); ++i) {
            stage = i == 0 ? "T1" : "T2";
            result.push_back(check_turn(model.get(), templates.get(), request[i]));
        }
        std::cout << result.dump() << '\n';
        return std::cout ? 0 : 1;
    } catch (const Gate &g) {
        std::cerr << "private replay failed at " << stage << '\n' << "fixed gate: " << g.what() << '\n';
        return 1;
    } catch (...) {
        std::cerr << "private replay failed at " << stage << '\n';
        return 1;
    }
}
