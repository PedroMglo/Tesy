#include "llama.h"
#include <fstream>
#include <iostream>
#include <iterator>
#include <vector>
int main(int argc,char**argv){
 if(argc!=3)return 2;llama_backend_init();auto p=llama_model_default_params();p.vocab_only=true;p.use_mmap=false;p.use_mlock=false;p.n_gpu_layers=0;
 auto*m=llama_model_load_from_file(argv[1],p);if(!m)return 3;
 std::ifstream f(argv[2]);std::string s((std::istreambuf_iterator<char>(f)),std::istreambuf_iterator<char>());
 auto*v=llama_model_get_vocab(m);std::vector<llama_token> ids(s.size()+32);int n=llama_tokenize(v,s.data(),s.size(),ids.data(),ids.size(),false,true);
 if(n<=0||n>128)return 4;std::cout<<"{\"mode\":\"vocab_only_no_weights\",\"official_expected_JSON_tokens\":"<<n<<",\"ids\":[";
 for(int i=0;i<n;++i)std::cout<<(i?",":"")<<ids[i];std::cout<<"]}\n";llama_model_free(m);llama_backend_free();return 0;
}
