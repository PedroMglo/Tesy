#include "llama.h"
#include <filesystem>
#include <fstream>
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <vector>
static std::string read(const std::filesystem::path & p){std::ifstream f(p);if(!f)throw std::runtime_error("text missing");return {std::istreambuf_iterator<char>(f),{}};}
static std::vector<llama_token> tokens(const llama_vocab * v,const std::string & text,bool special) {
    std::vector<llama_token> a(text.size()+1024);int n=llama_tokenize(v,text.data(),text.size(),a.data(),a.size(),special,true);
    if(n<=0)throw std::runtime_error("tokenize");a.resize(n);return a;
}
static void save(const std::filesystem::path & p,const std::vector<llama_token> & a){std::ofstream o(p);for(size_t i=0;i<a.size();++i)o<<(i?",":"")<<a[i];o<<'\n';o.close();if(!o)throw std::runtime_error("IDs write");}
int main(int argc,char ** argv) {
    try {
        if(argc!=5)throw std::runtime_error("MODEL text|render INPUT OUTPUT");
        llama_backend_init();auto mp=llama_model_default_params();mp.vocab_only=true;mp.use_mmap=false;
        auto * m=llama_model_load_from_file(argv[1],mp);if(!m)throw std::runtime_error("vocab only");auto * v=llama_model_get_vocab(m);
        std::string mode=argv[2];std::filesystem::path input=argv[3],output=argv[4];
        if(mode=="text")save(output,tokens(v,read(input),false));
        else if(mode=="render") {
            std::string system=read(input/"system.txt"),user=read(input/"user.txt"),history=read(input/"history.txt"),next=read(input/"next.txt");
            std::vector<llama_token> ids;std::string rendered;
            for(int attempt=0;attempt<2200;++attempt) {
                const llama_chat_message messages[]={{"system",system.c_str()},{"user",user.c_str()},{"assistant",history.c_str()},{"user",next.c_str()}};
                std::vector<char> out(system.size()+user.size()+history.size()+next.size()+4096);
                int n=llama_chat_apply_template(llama_model_chat_template(m,nullptr),messages,4,true,out.data(),out.size());
                if(n<=0||size_t(n)>=out.size())throw std::runtime_error("native Harmony render");
                rendered.assign(out.data(),n);ids=tokens(v,rendered,true);
                if(ids.size()==2197)break;
                if(ids.size()>2197)throw std::runtime_error("padding crossed exact context count");user+=" note";
            }
            if(ids.size()!=2197||rendered.find("Reasoning: medium")==std::string::npos||rendered.find("2026-09-30")==std::string::npos)throw std::runtime_error("context/date/medium gate");
            save(output,ids);std::ofstream out(output.string()+".rendered.txt");out<<rendered;out.close();if(!out)throw std::runtime_error("render write");
        } else throw std::runtime_error("mode");
        llama_model_free(m);llama_backend_free();return 0;
    }catch(const std::exception & e){std::cerr<<e.what()<<'\n';return 1;}
}
