// Replay the C281 public speculative interface. Only the verification loop reads future target IDs.
#include "arg.h"
#include "common.h"
#include "ngram-map.h"
#include "speculative.h"
#include <nlohmann/json.hpp>
#include <algorithm>
#include <iostream>
#include <stdexcept>

using json = nlohmann::json;

static void require(bool ok, const char *why) {
    if (!ok) throw std::runtime_error(why);
}

static json replay(const json &input, common_params &params) {
    const auto prompt = input.at("prompt").get<llama_tokens>();
    const auto target = input.at("target").get<llama_tokens>();
    const int cap = input.at("cap");
    require(cap > 0 && !target.empty() && int(target.size()) <= cap && !prompt.empty(), "workload");
    common_speculative_ptr engine(common_speculative_init(params.speculative, 1));
    require(engine.get() != nullptr && !common_speculative_need_embd(engine.get()), "ngram engine");
    common_speculative_begin(engine.get(), 0, prompt);
    llama_tokens past = prompt;
    llama_token last = target.front();
    size_t confirmed = 1;
    json rows = json::array();
    while (confirmed < target.size()) {
        const int room = std::min(8192 - int(past.size()) - 2, cap - int(confirmed) - 1);
        llama_tokens draft;
        if (room > 0) {
            auto &slot = common_speculative_get_draft_params(engine.get(), 0);
            slot = {true, room, llama_pos(past.size()), last, &past, &draft};
            common_speculative_draft(engine.get());
            const auto & config = params.speculative.ngram_simple;
            auto direct = common_ngram_simple_draft({uint16_t(config.size_n), uint16_t(config.size_m)}, past, last);
            if (int(direct.size()) > room) direct.resize(room);
            require(draft == direct, "server and helper propose different IDs");
        }
        const size_t begin = confirmed;
        size_t accepted = 0;
        while (confirmed < target.size() && accepted < draft.size() && draft[accepted] == target[confirmed]) {
            ++accepted;
            ++confirmed;
        }
        const bool no_bonus = confirmed == target.size();
        if (!no_bonus) ++confirmed;
        require(confirmed > begin && confirmed <= target.size(), "verification progress");
        if (!draft.empty()) common_speculative_accept(engine.get(), 0, uint16_t(accepted));
        past.push_back(last);
        past.insert(past.end(), target.begin() + begin, target.begin() + confirmed - 1);
        last = target[confirmed - 1];
        require(past.size() == prompt.size() + confirmed - 1 &&
                std::equal(target.begin(), target.begin()+confirmed-1, past.begin()+prompt.size()),
                "logical committed history");
        rows.push_back({{"at",begin},{"proposal",draft},{"accepted",accepted},
                        {"emitted",confirmed-begin},{"unobserved_bonus",no_bonus},{"room",room}});
    }
    return rows;
}

int main(int argc, char **argv) try {
    common_params params;
    require(common_speculative_n_max(&params.speculative) == 0, "plain server reserve");
    require(common_params_parse(argc, argv, params, LLAMA_EXAMPLE_SERVER), "server CLI parse");
    // The CLI appends the explicit method to the default NONE entry; NONE registers no engine.
    std::cerr << "PLAN_CONFIG " << common_speculative_type_name_str(params.speculative.types)
              << " max=" << common_speculative_n_max(&params.speculative) << '\n';
    const std::vector<common_speculative_type> parsed{COMMON_SPECULATIVE_TYPE_NONE,
                                                     COMMON_SPECULATIVE_TYPE_NGRAM_SIMPLE};
    require(params.speculative.types == parsed &&
            (params.speculative.ngram_simple.size_n == 2 || params.speculative.ngram_simple.size_n == 3) &&
            params.speculative.ngram_simple.size_m == 2 &&
            params.speculative.ngram_simple.min_hits == 1 && common_speculative_n_max(&params.speculative) == 2,
            "public ngram settings");
    const json inputs = json::parse(std::cin);
    json results;
    for (const auto &case_data : inputs.items()) results[case_data.key()] = replay(case_data.value(), params);
    std::cout << results.dump() << '\n';
    return 0;
} catch (const std::exception &e) {
    std::cerr << "PLAN_FAIL " << e.what() << '\n';
    return 1;
}
