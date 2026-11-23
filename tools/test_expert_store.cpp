#define TESY_STORE_TESTING
#include "llama-moe-stream.h"
#include "c291-expert-store.h"
#include <cassert>
#include <functional>
#include <iostream>
#include <thread>
void rejects(const std::function<void()>&f){bool failed=false;try{f();}catch(const std::exception&){failed=true;}assert(failed);}
ssize_t fail_read(int,void*,size_t,off_t){errno=EIO;return -1;}
ssize_t short_read(int,void*,size_t,off_t){return 8;}
int interruptions=0;
ssize_t interrupt_read(int fd,void*data,size_t n,off_t o){if(interruptions++==0){errno=EINTR;return -1;}return pread(fd,data,n,o);}
int main(int argc,char**argv){assert(argc==2);using S=tesy_expert_store;
 assert(tesy_store_completion_valid(false,true,7,7,4,4,LLAMA_MOE_STREAM_SLOT_LOADING,true));
 for(int kind=0;kind<7;kind++)assert(!tesy_store_completion_valid(kind==0,kind!=1,7,kind==2?8:7,4,kind==3?5:4,kind==4?LLAMA_MOE_STREAM_SLOT_RESIDENT:kind==5?LLAMA_MOE_STREAM_SLOT_EMPTY:LLAMA_MOE_STREAM_SLOT_LOADING,kind!=6));
 std::string file=std::string(argv[1])+"/store-synthetic16MiB.bin";std::vector<uint8_t> gold(S::staging_bytes);for(size_t i=0;i<gold.size();i++)gold[i]=i%251;
 int fd=open(file.c_str(),O_CREAT|O_EXCL|O_WRONLY|O_CLOEXEC,0600);assert(fd>=0);assert(write(fd,gold.data(),gold.size())==ssize_t(gold.size()));assert(fsync(fd)==0);close(fd);assert(chmod(file.c_str(),0444)==0);
 S store;store.data.open_file(file.c_str());store.entries[0][0].offset=0;void*memory=nullptr;assert(posix_memalign(&memory,4096,S::staging_bytes)==0);auto*staging=static_cast<uint8_t*>(memory);
 const auto*p=store.read(0,0,staging);assert(memcmp(p,gold.data(),S::weights)==0);
 p=store.read(0,0,staging,interrupt_read);assert(interruptions==2&&memcmp(p,gold.data(),S::weights)==0);
 rejects([&]{store.read(0,0,staging,fail_read);});rejects([&]{store.read(0,0,staging,short_read);});rejects([&]{store.read(36,0,staging);});rejects([&]{store.read(0,128,staging);});
 store.entries[0][0].offset=store.data.file_size();rejects([&]{store.read(0,0,staging);});store.entries[0][0].offset=1;rejects([&]{store.read(0,0,staging);});free(memory);
 // Give real runner time to observe the actual mapped runtime; no benchmark claim.
 std::this_thread::sleep_for(std::chrono::seconds(1));std::cout<<"PASS_STALE_EXPERT_GENERATION_CANCEL_LATE_ERROR_DIRECT_EINTR_SHORT_RANGE_ALIGNMENT_REUSE no model weights\n";
}
