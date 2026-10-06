#define main service_program_main
#include "expert_service_layout.cpp"
#undef main
#include <cassert>
#include <functional>
void rejects(const std::function<void()> &f){bool bad=false;try{f();}catch(const std::exception&){bad=true;}assert(bad);}
ssize_t short_reader(int,void*,size_t,off_t){return 1;}
ssize_t error_reader(int,void*,size_t,off_t){errno=EINVAL;return -1;}
int interruptions=0;
ssize_t interrupted_reader(int fd,void*p,size_t n,off_t off){if(interruptions++==0){errno=EINTR;return -1;}return pread(fd,p,n,off);}
int main(int argc,char**argv){assert(argc==2);std::string path=std::string(argv[1])+"/transport-synthetic.bin";
 std::vector<uint8_t> expected(32768);for(size_t i=0;i<expected.size();i++)expected[i]=i%251;
 int fd=open(path.c_str(),O_CREAT|O_EXCL|O_WRONLY|O_CLOEXEC,0600);assert(fd>=0);assert(write(fd,expected.data(),expected.size())==ssize_t(expected.size()));assert(fsync(fd)==0);close(fd);
 tesy_witness::direct_reader r;r.open_file(path.c_str());assert(fcntl(r.descriptor(),F_GETFL)&O_DIRECT);aligned_scratch s(r.memory_alignment());uint64_t calls=0,bytes=0;
 for(auto off:{uint64_t(0),uint64_t(1),uint64_t(4095),uint64_t(16384)}){auto*p=transport(r,s,off,4096,calls,bytes);assert(std::memcmp(p,expected.data()+off,4096)==0);}
 auto*p=transport(r,s,7,512,calls,bytes,interrupted_reader);assert(interruptions==2&&std::memcmp(p,expected.data()+7,512)==0);
 rejects([&]{transport(r,s,0,4096,calls,bytes,short_reader);});rejects([&]{transport(r,s,0,4096,calls,bytes,error_reader);});rejects([&]{transport(r,s,32767,2,calls,bytes);});rejects([&]{transport(r,s,UINT64_MAX,2,calls,bytes);});rejects([&]{transport(r,s,0,0,calls,bytes);});
 std::this_thread::sleep_for(std::chrono::seconds(1)); // Observe actual library mappings in bounded runner; no timing claim.
 std::cout<<"PASS direct fd/alignment, logical offsets, reusable bounded buffer, EINTR, short read, no fallback, EOF and overflow; synthetic32KiB, no weights\n";
}
