#include <filesystem>
#include <string>
#include <stdexcept>
#include <cstdio>
#include <iostream>
#include "c156_atomic_output.inl"
int main(int argc,char **argv){
 if(argc!=3)return 2;std::string mode=argv[2];const char * path=argv[1];
 if(mode=="collision"){FILE * original=std::fopen(path,"wx");if(!original)return 3;std::fputs("original",original);std::fclose(original);return c156_open_output(path)?4:0;}
 FILE * out=c156_open_output(path);if(!out)return 5;std::fputs("payload",out);
 if(mode=="error")::close(fileno(out));
 const bool accepted=c156_finish_output(out,path,mode!="cancel");
 return accepted==(mode=="ok")?0:6;
}
