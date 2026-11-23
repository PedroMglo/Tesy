// Native pinned renderer/tokenizer only: metadata and vocabulary, never weights.
#include "chat.h"
#include "llama.h"
#include "json.hpp"
#include <chrono>
#include <ctime>
#include <fstream>
#include <iostream>
#include <vector>
int main(int argc,char**argv) {
 try {
  if(argc!=3)throw std::runtime_error("MODEL USER_TEXT");
  std::ifstream in(argv[2]);if(!in)throw std::runtime_error("user text missing");std::string user{std::istreambuf_iterator<char>(in),{}};
  llama_backend_init();auto mp=llama_model_default_params();mp.vocab_only=true;mp.use_extra_bufts=false;mp.load_mode=LLAMA_LOAD_MODE_NONE;
  auto*m=llama_model_load_from_file(argv[1],mp);if(!m)throw std::runtime_error("vocab metadata");
  auto tmpls=common_chat_templates_init(m,"","","<|return|>");common_chat_templates_inputs ci;common_chat_msg msg;msg.role="user";msg.content=user;ci.messages.push_back(msg);ci.chat_template_kwargs["reasoning_effort"]=R"("medium")";
  std::tm date{};date.tm_year=126;date.tm_mon=8;date.tm_mday=30;ci.now=std::chrono::system_clock::from_time_t(timegm(&date));auto out=common_chat_templates_apply(tmpls.get(),ci);
  if(out.prompt.find("2026-09-30")==std::string::npos||out.prompt.find("Reasoning: medium")==std::string::npos)throw std::runtime_error("date/medium");
  std::vector<llama_token> ids(out.prompt.size()+1024);int n=llama_tokenize(llama_model_get_vocab(m),out.prompt.data(),out.prompt.size(),ids.data(),ids.size(),false,true);if(n<=0)throw std::runtime_error("tokens");ids.resize(n);
  std::cout<<nlohmann::json({{"schema","native-chat-fixture-v1"},{"prompt",out.prompt},{"ids",ids},{"medium",true},{"date","2026-09-30"},{"weights_loaded",false}}).dump()<<'\n';llama_model_free(m);llama_backend_free();return 0;
 }catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}
}
