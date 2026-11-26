#include "ggml.h"
#include "ggml-alloc.h"
#include "ggml-backend.h"
#include "ggml-cuda.h"
#include "../client/hooks.hpp"
#include <cuda_runtime_api.h>
#include <nlohmann/json.hpp>
#include <algorithm>
#include <array>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <dlfcn.h>
#include <fcntl.h>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <poll.h>
#include <sstream>
#include <stdexcept>
#include <string>
#include <sys/mman.h>
#include <sys/resource.h>
#include <sys/stat.h>
#include <sys/sysmacros.h>
#include <time.h>
#include <unistd.h>
#include <vector>

using json = nlohmann::json;
namespace fs = std::filesystem;
using byte = uint8_t;
using triple = std::array<size_t,3>;
constexpr size_t slab = 4406400, page = 4096, sample = 64;
constexpr triple probes = {0, slab/2, slab-sample};
static void need(bool v, const char *reason) { if (!v) throw std::runtime_error(reason); }
static size_t round_page(size_t n) { return (n+page-1)/page*page; }
static byte marker(size_t role, size_t i) {
    return byte(17+role*43+37*(i%4096)+11*(i/4096)+17*(i/251));
}
static int64_t ns(clockid_t clock) {
    timespec t{};
    need(clock_gettime(clock,&t)==0, "clock_gettime");
    return int64_t(t.tv_sec)*1000000000LL+t.tv_nsec;
}
static void handoff(char marker) {
    const char *tx = getenv("TESY_TEST_TX"), *rx = getenv("TESY_TEST_RX");
    need(tx && rx, "supervisor required");
    int w=std::stoi(tx), r=std::stoi(rx);
    need(w>2 && r>2 && w!=r && write(w,&marker,1)==1, "notify supervisor");
    pollfd wait{r,POLLIN,0};
    char ack=0;
    need(poll(&wait,1,5000)==1 && (wait.revents&POLLIN) && read(r,&ack,1)==1 && ack==marker,
         "supervisor handoff");
}

struct Sources {
    int ro=-1;
    size_t span=0;
    triple starts{}, residues{};
    byte *file=nullptr, *anon=nullptr;
    explicit Sources(triple offsets) {
        need(sysconf(_SC_PAGESIZE)==long(page), "4K pages required");
        for (unsigned k=0; k<3; ++k) {
            residues[k]=offsets[k]%page;
            starts[k]=span+residues[k];
            span=round_page(starts[k]+slab);
        }
        const int fd=memfd_create("tesy-ik-hot-slabs",MFD_CLOEXEC|MFD_ALLOW_SEALING);
        need(fd>=0 && ftruncate(fd,span)==0, "fresh shmem file");
        auto dst=static_cast<byte*>(mmap(nullptr,span,PROT_WRITE|PROT_READ,MAP_SHARED,fd,0));
        need(dst!=MAP_FAILED, "file setup mapping");
        for(unsigned k=0;k<3;++k)
            for(size_t i=0;i<slab;++i) dst[starts[k]+i]=marker(k,i);
        need(munmap(dst,span)==0, "drop writable file mapping");
        constexpr int seals=F_SEAL_SEAL|F_SEAL_WRITE|F_SEAL_GROW|F_SEAL_SHRINK;
        need(fcntl(fd,F_ADD_SEALS,seals)==0, "seal file");
        ro=open(("/proc/self/fd/"+std::to_string(fd)).c_str(),O_RDONLY|O_CLOEXEC);
        struct stat a{},b{};
        need(ro>=0 && fstat(ro,&a)==0 && fstat(fd,&b)==0 && a.st_dev==b.st_dev &&
             a.st_ino==b.st_ino && size_t(a.st_size)==span && fcntl(ro,F_GET_SEALS)==seals &&
             (fcntl(ro,F_GETFL)&O_ACCMODE)==O_RDONLY && close(fd)==0,"read-only descriptor");
        file=static_cast<byte*>(mmap(nullptr,span,PROT_READ,MAP_PRIVATE,ro,0));
        anon=static_cast<byte*>(mmap(nullptr,span,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS,-1,0));
        need(file!=MAP_FAILED && anon!=MAP_FAILED, "source mappings");
        std::memcpy(anon,file,span);
        need(mprotect(anon,span,PROT_READ)==0,"read-only anonymous control");
        check_vma(file,true,a);
        check_vma(anon,false,a);
    }
    void check_vma(const byte *base,bool from_file,const struct stat &id) const {
        std::ifstream maps("/proc/self/maps");
        std::string row;
        while(std::getline(maps,row)) {
            unsigned long lo,hi,off,inode;
            unsigned major_id,minor_id;
            char perms[5]{};
            if(std::sscanf(row.c_str(),"%lx-%lx %4s %lx %x:%x %lu",
                           &lo,&hi,perms,&off,&major_id,&minor_id,&inode)!=7) continue;
            if(lo>uintptr_t(base) || hi<uintptr_t(base)+span) continue;
            need(std::string(perms)=="r--p", "source VMA permissions");
            if(from_file) need(inode==id.st_ino && major_id==major(id.st_dev) &&
                               minor_id==minor(id.st_dev) && off+uintptr_t(base)-lo==0,
                               "shmem VMA identity");
            else need(inode==0 && major_id==0 && minor_id==0, "anonymous source identity");
            return;
        }
        need(false,"source VMA coverage");
    }
    triple resident(byte* base) const {
        triple result{};
        for(unsigned k=0;k<3;++k) {
            size_t first=starts[k]-residues[k], bytes=round_page(residues[k]+slab);
            std::vector<unsigned char> flags(bytes/page);
            need(mincore(base+first,bytes,flags.data())==0,"mincore");
            result[k]=std::count_if(flags.begin(),flags.end(),[](auto s){return (s&1)!=0;});
            need(result[k]==flags.size(),"nonresident source page");
        }
        return result;
    }
    ~Sources() {
        if(file && file!=MAP_FAILED) munmap(file,span);
        if(anon && anon!=MAP_FAILED) munmap(anon,span);
        if(ro>=0) close(ro);
    }
};

namespace observe {
int phase=1;
thread_local unsigned long owner=0;
static bool recording=false;
static int count=0;
struct Expected { const void *src; void *dst; };
static std::array<Expected,3> expected;
int64_t file_offset(const void*, size_t) { return -1; }
void transfer(const char* api, void *dst, const void* src, size_t bytes, int kind, int rc) {
    if(!recording) return;
    if(count>=3 || std::strcmp(api,"async") || kind!=cudaMemcpyHostToDevice || rc!=cudaSuccess ||
       bytes!=slab || src!=expected[count].src || dst!=expected[count].dst) std::abort();
    ++count;
}
}

struct Device {
    ggml_backend_t backend=nullptr;
    ggml_context *ctx=nullptr;
    ggml_backend_buffer_t buffer=nullptr;
    std::array<ggml_tensor*,3> tensor{};
    Device() {
        backend=ggml_backend_cuda_init(0,nullptr,nullptr);
        ctx=ggml_init({1024*1024,nullptr,true});
        need(backend && ctx,"CUDA0 context");
        for(auto &t:tensor) t=ggml_new_tensor_3d(ctx,GGML_TYPE_MXFP4,2880,2880,3);
        buffer=ggml_backend_alloc_ctx_tensors(ctx,backend);
        need(buffer && std::string(ggml_backend_buffer_name(buffer))=="CUDA0","CUDA0 buffer");
        ggml_backend_buffer_set_usage(buffer,GGML_BACKEND_BUFFER_USAGE_WEIGHTS);
        for(auto *t:tensor) need(t && t->buffer==buffer && t->type==GGML_TYPE_MXFP4 &&
                                 ggml_is_contiguous(t) && t->nb[2]==slab &&
                                 ggml_nbytes(t)==3*slab,"MXFP4 destination");
    }
    ~Device() { ggml_backend_buffer_free(buffer); ggml_free(ctx); ggml_backend_free(backend); }
};

static void unregistered(const byte *p) {
    static auto attrs=reinterpret_cast<decltype(&cudaPointerGetAttributes)>(
        dlsym(RTLD_DEFAULT,"cudaPointerGetAttributes"));
    cudaPointerAttributes value{};
    need(attrs && attrs(&value,p)==cudaSuccess && value.type==cudaMemoryTypeUnregistered,
         "CUDA source registration or attributes");
}

static json one(Device &dev, Sources &mem, bool from_file, bool qualify) {
    auto *base=from_file ? mem.file : mem.anon;
    auto before=mem.resident(base);
    for(unsigned k=0;k<3;++k) {
        const auto pos=mem.starts[k];
        unregistered(base+pos);
        unregistered(base+pos+slab-1);
        observe::expected[k]={base+pos,static_cast<byte*>(dev.tensor[k]->data)+slab};
        for(auto at:probes) {
            std::array<byte,sample> poison;
            for(size_t i=0;i<sample;++i) poison[i]=marker(k,at+i)^0xff;
            ggml_backend_tensor_set(dev.tensor[k],poison.data(),slab+at,sample);
        }
    }
    ggml_backend_synchronize(dev.backend);
    rusage usage0{},usage1{};
    need(getrusage(RUSAGE_SELF,&usage0)==0,"begin usage");
    auto process0=ns(CLOCK_PROCESS_CPUTIME_ID), thread0=ns(CLOCK_THREAD_CPUTIME_ID);
    observe::count=0;
    observe::recording=true;
    auto wall0=ns(CLOCK_MONOTONIC);
    for(unsigned k=0;k<3;++k)
        ggml_backend_tensor_set_async(dev.backend,dev.tensor[k],base+mem.starts[k],slab,slab);
    auto submitted=ns(CLOCK_MONOTONIC);
    ggml_backend_synchronize(dev.backend);
    auto end=ns(CLOCK_MONOTONIC);
    observe::recording=false;
    auto thread1=ns(CLOCK_THREAD_CPUTIME_ID), process1=ns(CLOCK_PROCESS_CPUTIME_ID);
    need(getrusage(RUSAGE_SELF,&usage1)==0 && observe::count==3,"copy count or usage");
    auto after=mem.resident(base);
    for(unsigned k=0;k<3;++k) {
        auto check=[&](size_t pos, size_t n) {
            std::vector<byte> recovered(n);
            ggml_backend_tensor_get(dev.tensor[k],recovered.data(),slab+pos,n);
            for(size_t i=0;i<n;++i) need(recovered[i]==marker(k,pos+i), "roundtrip mismatch");
        };
        if(qualify) check(0,slab);
        else for(auto pos:probes) check(pos,sample);
    }
    need(usage1.ru_majflt==usage0.ru_majflt && usage1.ru_inblock==usage0.ru_inblock,
         "major fault or block read in hot interval");
    return {{"mode",from_file?"FILE":"ANON"},{"exact",qualify},{"pages_before",before},
            {"pages_after",after},{"copies",observe::count},{"payload_B",3*slab},
            {"poison_B",9*sample},{"roundtrip_B",qualify?3*slab:9*sample},
            {"submit_ns",submitted-wall0},{"drain_ns",end-submitted},{"wall_ns",end-wall0},
            {"thread_ns",thread1-thread0},{"process_ns",process1-process0},
            {"minor_faults",usage1.ru_minflt-usage0.ru_minflt},
            {"major_faults",usage1.ru_majflt-usage0.ru_majflt},
            {"input_blocks",usage1.ru_inblock-usage0.ru_inblock}};
}

int main(int argc,char**argv) try {
    need(argc==4,"expected FILE_FIRST|ANON_FIRST geometry.json new-dir");
    const std::string order=argv[1];
    need(order=="FILE_FIRST"||order=="ANON_FIRST","order");
    const fs::path out=argv[3];
    need(fs::create_directory(out),"exclusive native output");
    json meta=json::parse(std::ifstream(argv[2]));
    auto offsets=meta.at("layer0_original_offsets_gate_up_down").get<triple>();
    need(offsets==triple{1838905376,2405874208,1273411616},"C283 L0 offsets");
    Sources mem(offsets);
    const bool first=order=="FILE_FIRST";
    auto rows=json::array();
    handoff('E');
    {
        Device dev;
        handoff('A');
        rows.push_back(one(dev,mem,first,true));
        rows.push_back(one(dev,mem,!first,true));
        for(int i=0;i<5;++i) {
            bool direction=(i%2==0) ? first : !first;
            rows.push_back(one(dev,mem,direction,false));
            rows.push_back(one(dev,mem,!direction,false));
        }
        std::ifstream kernel("/proc/self/maps");
        std::ofstream maps(out/"maps");
        maps<<kernel.rdbuf(); maps.close();
        need(bool(maps),"save final maps");
        handoff('F');
    }
    json result={{"status","PASS_HOT_TRANSFER_PROCESS"},{"order",order},{"offsets",offsets},
                 {"residues",mem.residues},{"span_B",mem.span},{"rows",rows}};
    std::ofstream raw(out/"samples.json"); raw<<result.dump(2)<<"\n";raw.close();
    need(bool(raw),"save samples");
    return 0;
} catch(const std::exception &e) {
    std::cerr<<e.what()<<'\n';
    return 1;
}
