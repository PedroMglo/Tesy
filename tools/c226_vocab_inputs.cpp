// Official C75 common chat renderer and tokenizer, vocab_only; no weights/forward.
#include "chat.h"
#include "llama.h"
#include "nlohmann/json.hpp"
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <vector>
using json=nlohmann::ordered_json;
int main(int argc,char**argv){
 try{
  if(argc!=4)throw std::runtime_error("MODEL TASKS OUTPUT");
  std::ifstream f(argv[2]);json tasks;f>>tasks;if(!f)throw std::runtime_error("tasks read");
  llama_backend_init();auto mp=llama_model_default_params();mp.vocab_only=true;mp.use_mmap=false;mp.use_mlock=false;mp.n_gpu_layers=0;
  auto*m=llama_model_load_from_file(argv[1],mp);if(!m)throw std::runtime_error("vocab load");
  auto tmpls=common_chat_templates_init(m, "", "", "");json out=json::object();
  for(const auto &task:tasks){common_chat_templates_inputs in;
   in.messages=common_chat_msgs_parse_oaicompat(task["messages"]);
   in.chat_template_kwargs["reasoning_effort"]=R"("medium")";
   in.chat_template_kwargs["tesy_template_date"]=R"("2026-09-30")";
   auto rendered=common_chat_templates_apply(tmpls.get(),in);
   std::vector<llama_token> ids(rendered.prompt.size()+4096);
   auto*v=llama_model_get_vocab(m);int n=llama_tokenize(v,rendered.prompt.data(),rendered.prompt.size(),ids.data(),ids.size(),false,true);
   if(n<=0||size_t(n)>ids.size())throw std::runtime_error("official tokenize");ids.resize(n);
   out[task["id"].get<std::string>()]={{"ids",ids},{"rendered_prompt",rendered.prompt},{"mode","vocab_only_no_weights_no_forward"}};
  }
  std::ofstream target(argv[3],std::ios::out|std::ios::trunc);target<<out.dump(2)<<"\n";target.close();if(!target)throw std::runtime_error("output write");
  llama_model_free(m);llama_backend_free();return 0;
 }catch(const std::exception&e){std::cerr<<e.what()<<"\n";return 1;}
}
