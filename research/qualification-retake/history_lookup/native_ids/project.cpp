// Reuse the same C269 vocab-only and PEG setup as the independently frozen inversion.
// This program consumes private data on stdin and emits only to its parent's private pipe.
#define main historical_witness_main
#include "../natural47/witness.cpp"
#undef main

static std::string hex_piece(const std::string &piece) {
    static constexpr char digits[] = "0123456789abcdef";
    std::string hex;
    for (unsigned char byte : piece) {
        hex.push_back(digits[byte >> 4]);
        hex.push_back(digits[byte & 15]);
    }
    return hex;
}

static json project(const llama_vocab *vocab, const Grammar &g, const json &turn) {
    auto ids = turn.at("ids").get<llama_tokens>();
    gate(ids.size() == 78 || ids.size() == 47, "turn size");
    gate(turn.at("preserved").get<std::set<llama_token>>() == g.preserved, "preserved controls");
    auto prompt = turn.at("prompt").get<int>();
    auto cache = turn.at("cache").get<int>();
    task_result_state state(g.parser);
    json frames = json::array(), pieces = json::array();
    std::string text;
    size_t sent = 0;
    for (size_t i = 0; i != ids.size(); ++i) {
        auto id = ids[i];
        gate(id >= 0 && id < llama_vocab_n_tokens(vocab), "ID range");
        gate(llama_vocab_is_eog(vocab, id) == (i + 1 == ids.size()), "EOG order");
        auto piece = common_token_to_piece(vocab, id, g.preserved.count(id) != 0);
        pieces.push_back(hex_piece(piece));
        text += piece;
        if (validate_utf8(text) != text.size()) continue;
        server_task_result_cmpl_partial part{};
        part.res_type = TASK_RESPONSE_TYPE_OAI_CHAT;
        part.index = 0;
        part.n_decoded = static_cast<int>(i + 1);
        part.tokens = {id};
        part.content = text.substr(sent);
        sent = text.size();
        part.update(state);
        append_projection(frames, part.to_json());
    }
    server_task_result_cmpl_final final{};
    final.res_type = TASK_RESPONSE_TYPE_OAI_CHAT;
    final.index = 0;
    final.stream = true;
    final.include_usage = true;
    final.stop = STOP_TYPE_EOS;
    final.n_decoded = static_cast<int>(ids.size());
    final.n_prompt_tokens = prompt;
    final.n_prompt_tokens_cache = cache;
    final.update(state);
    append_projection(frames, final.to_json());
    gate(frames == turn.at("frames"), "chat projection");
    return {{"eog_only_at_end", true}, {"pieces_hex", pieces}, {"frames", frames.size()}};
}

int main(int argc, char **argv) {
    try {
        gate(argc == 2, "vocab only");
        auto model = vocabulary(argv[1]);
        gate(model != nullptr, "vocab load");
        const auto *v = llama_model_get_vocab(model.get());
        gate(v && llama_vocab_n_tokens(v) == 201088, "vocab size");
        auto g = grammar(model.get(), v);
        json turns;
        std::cin >> turns;
        gate(turns.is_array() && turns.size() == 2, "turn count");
        json output = json::array();
        for (const auto &turn : turns) output.push_back(project(v, g, turn));
        std::cout << output.dump() << '\n';
        return std::cout ? 0 : 1;
    } catch (...) {
        std::cerr << "C269 vocabulary, EOG or chat projection failed\n";
        return 1;
    }
}
