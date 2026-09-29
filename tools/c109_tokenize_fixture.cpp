#include "llama.h"

#include <algorithm>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

static std::string read(const std::string & path) {
    std::ifstream in(path);
    if (!in) throw std::runtime_error("missing fixture text");
    return {std::istreambuf_iterator<char>(in), std::istreambuf_iterator<char>()};
}

static std::vector<llama_token> tokenize(const llama_vocab * vocab,
                                          const std::string & value, bool add_special) {
    std::vector<llama_token> out(std::max<size_t>(256, value.size()*2));
    int n = llama_tokenize(vocab, value.data(), value.size(), out.data(), out.size(),
                           add_special, true);
    if (n < 0) {
        out.resize(static_cast<size_t>(-n));
        n = llama_tokenize(vocab, value.data(), value.size(), out.data(), out.size(),
                           add_special, true);
    }
    if (n <= 0 || static_cast<size_t>(n) > out.size()) throw std::runtime_error("tokenize failed");
    out.resize(static_cast<size_t>(n));
    return out;
}

int main(int argc, char ** argv) {
    if (argc != 4) return 2;
    try {
        const std::string root = argv[2];
        const std::string output = argv[3];
        llama_backend_init();
        auto params = llama_model_default_params();
        params.vocab_only = true;
        params.use_mmap = false;
        llama_model * model = llama_model_load_from_file(argv[1], params);
        if (!model) throw std::runtime_error("vocab-only model load failed");
        const char * tmpl = llama_model_chat_template(model, nullptr);
        if (!tmpl) throw std::runtime_error("embedded chat template missing");
        const std::string system = read(root + "/system.txt");
        const std::string user = read(root + "/user.txt");
        const std::string answer = read(root + "/answer.txt");
        const llama_chat_message messages[] = {{"system", system.c_str()}, {"user", user.c_str()}};
        std::vector<char> rendered(system.size() + user.size() + 4096);
        int n = llama_chat_apply_template(tmpl, messages, 2, true,
                                          rendered.data(), rendered.size());
        if (n <= 0) throw std::runtime_error("embedded chat template failed");
        if (static_cast<size_t>(n) >= rendered.size()) {
            rendered.resize(static_cast<size_t>(n)+1);
            n = llama_chat_apply_template(tmpl, messages, 2, true,
                                           rendered.data(), rendered.size());
            if (n <= 0 || static_cast<size_t>(n) >= rendered.size())
                throw std::runtime_error("chat template retry failed");
        }
        const std::string prompt(rendered.data(), static_cast<size_t>(n));
        const llama_vocab * vocab = llama_model_get_vocab(model);
        const auto prompt_ids = tokenize(vocab, prompt, true);
        const auto full_ids = tokenize(vocab, prompt + answer, true);
        if (full_ids.size() < prompt_ids.size()+192 ||
            !std::equal(prompt_ids.begin(), prompt_ids.end(), full_ids.begin()))
            throw std::runtime_error("prompt/answer token boundary is not prefix stable");
        std::ofstream out(output, std::ios::out | std::ios::trunc);
        if (!out) throw std::runtime_error("ID output unavailable");
        out << "prompt\t";
        for (size_t i=0; i<prompt_ids.size(); ++i) out << (i ? "," : "") << prompt_ids[i];
        out << "\ncontinuation192\t";
        for (size_t i=0; i<192; ++i) out << (i ? "," : "") << full_ids[prompt_ids.size()+i];
        out << '\n';
        out.close();
        if (!out) throw std::runtime_error("ID output write failed");
        std::cout << "prompt_tokens=" << prompt_ids.size() << " continuation_tokens=192"
                  << " answer_available_tokens=" << full_ids.size()-prompt_ids.size() << '\n';
        llama_model_free(model);
        llama_backend_free();
    } catch (const std::exception & e) {
        std::cerr << "C109 tokenizer: " << e.what() << '\n';
        return 1;
    }
    return 0;
}
