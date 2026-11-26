// Model-free driver for the C269 proposer and verifier. The two row callbacks
// replace model-dependent sampling only in this executable.
#include "ngram-map.h"
#include "sampling.h"

#include <nlohmann/json.hpp>
#include <algorithm>
#include <dlfcn.h>
#include <filesystem>
#include <iostream>
#include <numeric>
#include <stdexcept>

using json = nlohmann::json;
namespace fs = std::filesystem;

static void require(bool valid, const char *reason) {
    if (!valid) throw std::runtime_error(reason);
}

struct WindowEnd {};

struct TargetRows {
    const llama_tokens &target;
    size_t start;  // Index of the next confirmed output after the prompt anchor.
    size_t stop;   // Exclusive; the verifier cannot sample outside this window.
    size_t width;
    size_t reads = 0;
    size_t unavailable = 0;
    llama_tokens accepted;
};

static TargetRows *active = nullptr;

llama_token common_sampler_sample(common_sampler *sampler, llama_context *ctx,
                                  int idx, bool grammar_first) {
    require(active && !sampler && !ctx && !grammar_first, "row callback contract");
    auto &t = *active;
    require(idx >= 0 && static_cast<size_t>(idx) == t.reads && t.reads < t.width &&
            t.reads == t.accepted.size() && !t.unavailable, "unexpected verifier index");
    if (t.start + t.reads == t.stop) {
        ++t.unavailable;
        throw WindowEnd{};
    }
    return t.target.at(t.start + t.reads++);
}

void common_sampler_accept(common_sampler *sampler, llama_token token, bool generated) {
    require(active && !sampler && generated, "accept callback contract");
    auto &t = *active;
    require(t.reads == t.accepted.size() + 1 &&
            t.target.at(t.start + t.reads - 1) == token, "unexpected accepted row");
    t.accepted.push_back(token);
}

template<typename Function>
static fs::path provider(Function fn) {
    Dl_info info{};
    require(dladdr(reinterpret_cast<const void *>(fn), &info) && info.dli_fname,
            "cannot identify symbol provider");
    return fs::canonical(info.dli_fname);
}

static llama_tokens ids(const json &value) {
    require(value.is_array() && !value.empty() && value.size() <= 8192, "invalid ID vector");
    llama_tokens result;
    for (const auto &entry : value) {
        require(entry.is_number_integer() && entry >= 0 && entry < 201088, "invalid target ID");
        result.push_back(entry.get<llama_token>());
    }
    return result;
}

static json run(const json &input) {
    using Verify = llama_tokens (*)(common_sampler *, llama_context *, const std::vector<int> &,
                                    const llama_tokens &, bool);
    auto verify = static_cast<Verify>(common_sampler_sample_and_accept_n);
    const auto lookup_dso = provider(common_ngram_simple_draft);
    const auto verify_dso = provider(verify);
    const auto executable = fs::canonical("/proc/self/exe");
    require(lookup_dso == verify_dso && lookup_dso != executable &&
            provider(common_sampler_sample) == executable &&
            provider(common_sampler_accept) == executable, "wrong symbol providers");

    const auto prompt = ids(input.at("prompt"));
    const auto target = ids(input.at("target"));
    const auto &limit = input.at("end");
    require(limit.is_number_integer() && limit > 0 && limit < target.size(), "invalid window");
    const size_t end = limit.get<size_t>();
    llama_tokens past = prompt;
    llama_token sampled = target.front();
    json events = json::array();
    size_t pos = 0, ordinary = 0, proposed = 0, matched = 0, drafted = 0;
    size_t full = 0, rejected = 0, other = 0, discarded = 0, interrupted = 0;

    while (pos < end) {
        // Neither the target suffix nor the window boundary is given to the proposer.
        const auto draft = common_ngram_simple_draft({2, 2}, past, sampled);
        require(draft.empty() || draft.size() == 2, "unexpected draft size");
        std::vector<int> indexes(draft.size() + 1);
        std::iota(indexes.begin(), indexes.end(), 0);
        TargetRows rows{target, 1 + pos, 1 + end, indexes.size(), 0, 0, {}};
        active = &rows;
        try {
            if (draft.empty()) {
                const auto id = common_sampler_sample(nullptr, nullptr, 0, false);
                common_sampler_accept(nullptr, id, true);
            } else {
                const auto result = verify(nullptr, nullptr, indexes, draft, false);
                require(result == rows.accepted, "verifier return differs from accept callbacks");
            }
        } catch (const WindowEnd &) {
            require(rows.unavailable == 1 && rows.start + rows.reads == rows.stop,
                    "unexpected window interruption");
        }
        active = nullptr;
        const auto &outputs = rows.accepted;
        require(!outputs.empty() && rows.reads == outputs.size() &&
                outputs.size() <= indexes.size(), "incorrect verifier output cardinality");
        size_t accepted = 0;
        while (accepted < draft.size() && accepted < outputs.size() &&
               draft[accepted] == outputs[accepted]) ++accepted;
        const bool mismatch = accepted < draft.size() && accepted < outputs.size();
        require(rows.unavailable ? accepted == outputs.size() :
                outputs.size() == accepted + 1, "invalid verifier stop");

        // Model the server's logical prefix. A copy of a rejected or unobserved
        // draft must not survive into the next n-gram lookup. No KV pages exist here.
        past.push_back(sampled);
        const size_t keep = past.size();
        past.insert(past.end(), draft.begin(), draft.end());
        past.resize(keep);
        past.insert(past.end(), outputs.begin(), outputs.end() - 1);
        sampled = outputs.back();
        const size_t next = pos + outputs.size();
        require(past.size() == prompt.size() + next &&
                std::equal(prompt.begin(), prompt.end(), past.begin()) &&
                std::equal(target.begin(), target.begin() + next, past.begin() + prompt.size()) &&
                sampled == target[next], "logical history differs from target prefix");
        const size_t tail = draft.size() - accepted;
        events.push_back({{"position", pos}, {"proposed", draft.size()}, {"accepted_draft", accepted},
                          {"emitted", outputs.size()}, {"discarded_draft", tail}, {"ar", draft.empty()},
                          {"verifier_rows", draft.empty() ? 0 : rows.reads}, {"beyond_window_rows", 0},
                          {"unavailable_row_attempts", rows.unavailable}, {"mismatch", mismatch},
                          {"boundary_interrupted", rows.unavailable != 0},
                          {"unobserved_draft", rows.unavailable ? tail : 0}});
        ordinary += draft.empty();
        proposed += !draft.empty();
        drafted += draft.size();
        matched += accepted;
        full += !draft.empty() && accepted == draft.size();
        rejected += mismatch;
        other += outputs.size() - accepted;
        discarded += tail;
        interrupted += rows.unavailable;
        pos = next;
    }
    require(pos == end && matched + other == end && drafted == matched + discarded &&
            ordinary + proposed == events.size(), "window conservation");
    json summary = {{"outputs", end}, {"calls", events.size()}, {"ordinary", ordinary},
                    {"proposals", proposed}, {"drafted_ids", drafted}, {"accepted_ids", matched},
                    {"full_proposals", full}, {"rejections", rejected},
                    {"ordinary_corrective_or_bonus", other}, {"fewer_calls", end - events.size()}};
    return {{"status", "PASS_C269_B3_NATIVE_CONTROL"}, {"window", end}, {"history_equal", true},
            {"events", events}, {"summary", summary}, {"logical_rollback_rows", discarded},
            {"stop_placeholders", 0}, {"boundary_interruptions", interrupted},
            {"callbacks_in_executable", true}, {"lookup_provider", lookup_dso.string()},
            {"verify_provider", verify_dso.string()}};
}

int main(int argc, char **) {
    try {
        require(argc == 1, "expected JSON on stdin");
        const auto result = run(json::parse(std::cin));
        std::cout << result.dump() << '\n';
        return std::cout ? 0 : 1;
    } catch (...) {
        // Neither parser errors nor token values may reach the public report.
        std::cerr << "B3 native fixture failed input, provenance or execution checks\n";
        return 1;
    }
}
