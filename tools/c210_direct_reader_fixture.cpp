#include "c210_direct_reader.h"
#include <vector>
#include <iostream>
static int injected=0;
ssize_t intr(int f,void*p,size_t n,off_t o){if(!injected++){errno=EINTR;return -1;}return pread(f,p,n,o);}
ssize_t short_read(int,void*,size_t,off_t){return 1;}
ssize_t error_read(int,void*,size_t,off_t){errno=EINVAL;return -1;}
int main(int argc,char**argv){
 if(argc!=2)return 2;
 std::vector<unsigned char> expected(20000);for(size_t i=0;i<expected.size();++i)expected[i]=i%251;
 int fd=open(argv[1],O_WRONLY|O_CREAT|O_EXCL,0600);if(fd<0)return 3;
 if(write(fd,expected.data(),expected.size())!=static_cast<ssize_t>(expected.size()))return 4;
 close(fd);
 try{
  tesy_witness::direct_reader r;r.open_file(argv[1]);int negative=0;
  for(auto pair:std::vector<std::pair<size_t,size_t>>{{0,4096},{3,4406},{19980,20},{1024,8192}}){
   std::vector<unsigned char> out(pair.second);r.read(out.data(),out.size(),pair.first);
   if(memcmp(out.data(),expected.data()+pair.first,out.size()))return 5;
  }
  std::vector<unsigned char> out(4000);r.read(out.data(),out.size(),7,intr);if(memcmp(out.data(),expected.data()+7,out.size()))return 6;
  for(auto fn:{short_read,error_read})try{r.read(out.data(),out.size(),7,fn);return 7;}catch(const std::runtime_error&){++negative;}
  for(auto off:{uint64_t(20000),std::numeric_limits<uint64_t>::max()})try{r.read(out.data(),1,off);return 8;}catch(const std::runtime_error&){++negative;}
  try{r.read(out.data(),0,0);return 9;}catch(const std::runtime_error&){++negative;}
  out[0]^=1;if(!memcmp(out.data(),expected.data()+7,out.size()))return 10;
  std::cout<<"{\"PASS\":true,\"O_DIRECT\":true,\"mem_align\":"<<r.memory_alignment()<<",\"offset_align\":"<<r.offset_alignment()<<",\"negative_controls\":"<<negative<<"}\n";
 }catch(const std::exception&e){std::cerr<<e.what()<<"\n";return 11;}return 0;
}
