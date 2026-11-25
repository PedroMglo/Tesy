// Isolated model-free probe of the two production common_chat implementations.
#include "chat.h"

#include <array>
#include <cstdint>
#include <fstream>
#include <iostream>
#include <iterator>
#include <stdexcept>
#include <string>

static std::string read_field() {
    std::array<unsigned char,4> b{};
    if (!std::cin.read(reinterpret_cast<char *>(b.data()), b.size())) throw std::runtime_error("length");
    const uint32_t n = b[0] | (uint32_t(b[1])<<8) | (uint32_t(b[2])<<16) | (uint32_t(b[3])<<24);
    if (n > 256*1024) throw std::runtime_error("oversized field");
    std::string s(n,'\0');
    if (!std::cin.read(s.data(),n)) throw std::runtime_error("field");
    return s;
}

int main(int argc, char **argv) {
    try {
        if (argc != 3) throw std::runtime_error("template and date required");
        std::ifstream f(argv[1]);
        if (!f) throw std::runtime_error("missing Jinja source");
        std::string tmpl{std::istreambuf_iterator<char>(f),std::istreambuf_iterator<char>()};
        auto templates=common_chat_templates_init(nullptr,tmpl);
        common_chat_templates_inputs inputs;
        inputs.add_generation_prompt = true;
        inputs.use_jinja = true;
        inputs.chat_template_kwargs["reasoning_effort"] = "\"medium\"";
        inputs.chat_template_kwargs["tesy_template_date"] = "\"" + std::string(argv[2]) + "\"";
        while (std::cin.peek() != std::char_traits<char>::eof()) {
            common_chat_msg m;
            m.role=read_field(); m.content=read_field();
            if (m.role != "user" && m.role != "assistant") throw std::runtime_error("unexpected role");
            inputs.messages.push_back(std::move(m));
        }
        if (inputs.messages.empty()) throw std::runtime_error("no messages");
        const auto result=common_chat_templates_apply(templates.get(),inputs);
#if defined(REFERENCE_C269)
        std::cout << result.prompt;
#else
        std::cout << result.prompt.str();
#endif
        return std::cout ? 0 : 1;
    } catch (const std::exception &) {
        std::cerr << "render failed\n";
        return 1;
    }
}
