#include "chat.h"
#include "gguf.h"
#include "llama.h"
#include <chrono>
#include <ctime>
#include <fstream>
#include <iostream>
#include <stdexcept>

int main(int argc,char ** argv) {
    try {
        if(argc!=3)throw std::runtime_error("MODEL OUTPUT");
        ggml_context * meta=nullptr;auto * g=gguf_init_from_file(argv[1],{true,&meta});
        if(!g)throw std::runtime_error("metadata");
        auto id=gguf_find_key(g,"tokenizer.chat_template");if(id<0)throw std::runtime_error("template missing");
        std::string text=gguf_get_val_str(g,id);gguf_free(g);ggml_free(meta);
        auto tmpls=common_chat_templates_init(nullptr,text,"","<|return|>");
        common_chat_templates_inputs inputs;
        common_chat_msg user;user.role="user";user.content="Count exactly two letters: AB.";inputs.messages.push_back(user);
        inputs.chat_template_kwargs["reasoning_effort"]=R"("medium")";
        std::tm date{};date.tm_year=126;date.tm_mon=8;date.tm_mday=30;
        inputs.now=std::chrono::system_clock::from_time_t(timegm(&date));
        auto params=common_chat_templates_apply(tmpls.get(),inputs);
        std::ofstream diagnostic(argv[2]);diagnostic<<params.prompt;diagnostic.close();
        if(!diagnostic)throw std::runtime_error("rendered output write failed");
        if(params.prompt.find("2026-09-30")==std::string::npos || params.prompt.find("Reasoning: medium")==std::string::npos ||
           params.prompt.find("<|start|>assistant")==std::string::npos)throw std::runtime_error("date/medium/Harmony gate");
        std::ofstream out(argv[2]);out<<params.prompt;
        std::cout<<"C148_NATIVE_TEMPLATE_DATE_MEDIUM_HARMONY_PASS bytes="<<params.prompt.size()<<std::endl;
    }catch(const std::exception & e){std::cerr<<e.what()<<std::endl;return 1;}
}
