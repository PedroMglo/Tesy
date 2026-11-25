// Observe the real CPU loader and call libc/kernel for each intercepted operation.
#include "llama.h"
#include "ggml-moe-prefetch.h"
#include <sys/mman.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <sys/sysmacros.h>
#include <sys/resource.h>
#include <unistd.h>
#include <dirent.h>
#include <dlfcn.h>
#include <cstdio>
#include <cstring>
#include <cmath>
#include <cstdlib>
#include <fstream>
#include <string>

static struct stat file_id;
static bool loading;
static uintptr_t base;
static size_t length;
static bool tracked(void *addr, size_t size) {
    uintptr_t p = reinterpret_cast<uintptr_t>(addr);
    return loading && base && p >= base && p-base < length && size <= length-(p-base);
}
extern "C" void *mmap(void *p,size_t n,int prot,int flags,int fd,off_t offset) noexcept {
    auto result = reinterpret_cast<void *>(syscall(SYS_mmap,p,n,prot,flags,fd,offset));
    struct stat s;
    if (loading && result != MAP_FAILED && fd >= 0 && fstat(fd,&s)==0 &&
        s.st_dev==file_id.st_dev && s.st_ino==file_id.st_ino) {
        base=reinterpret_cast<uintptr_t>(result);
        length=n;
        std::printf("MAP %ld %zu %d %d\n",long(offset),n,prot,flags);
    }
    return result;
}
extern "C" int madvise(void *p,size_t n,int advice) noexcept {
    int rc = int(syscall(SYS_madvise,p,n,advice));
    if (tracked(p,n)) std::printf("MAD %zu %zu %d %d\n",uintptr_t(p)-base,n,advice,rc);
    return rc;
}
extern "C" int posix_madvise(void *p,size_t n,int advice) noexcept {
    using Fn=int(*)(void *,size_t,int);
    static auto real=reinterpret_cast<Fn>(dlsym(RTLD_NEXT,"posix_madvise"));
    if (!real) std::abort();
    int rc=real(p,n,advice);
    if (tracked(p,n)) std::printf("POSIX %zu %zu %d %d\n",uintptr_t(p)-base,n,advice,rc);
    return rc;
}
static int tasks() {
    DIR *d=opendir("/proc/self/task");
    if (!d) std::abort();
    int n=0;
    while (auto *e=readdir(d)) if (e->d_name[0]>='0' && e->d_name[0]<='9') ++n;
    closedir(d); return n;
}
static void inspect(llama_model *model,const std::string &name) {
    auto *t=llama_get_model_tensor(model,name.c_str());
    if (!t || !t->data || !t->buffer) std::abort();
    auto start=uintptr_t(t->data), stop=start+ggml_nbytes(t), cursor=start;
    unsigned long file_offset=0;
    std::ifstream maps("/proc/self/maps");
    std::string ln;
    while (std::getline(maps,ln) && cursor<stop) {
        unsigned long a,b,off,ino; unsigned maj,min; char perm[5]={};
        if (std::sscanf(ln.c_str(),"%lx-%lx %4s %lx %x:%x %lu",&a,&b,perm,&off,&maj,&min,&ino)!=7 ||
            !(a<=cursor && cursor<b)) continue;
        if (ino!=file_id.st_ino || makedev(maj,min)!=file_id.st_dev || perm[0]!='r' || perm[1]!='-') {
            std::fprintf(stderr,"non-file or writable view %s\n",name.c_str()); std::exit(34);
        }
        if (cursor==start) file_offset=off+start-a;
        if (off+cursor-a!=file_offset+cursor-start) std::abort();
        cursor=std::min(uintptr_t(b),stop);
    }
    if (cursor != stop) std::abort();
    std::printf("VIEW %s %lu %zu %d\n",name.c_str(),file_offset,ggml_nbytes(t),int(t->type));
}
int main(int argc,char **argv) {
    setvbuf(stdout,nullptr,_IOLBF,0);
    if (argc!=4 || stat(argv[1],&file_id)) return 2;
    const std::string mode=argv[2];
    if (mode!="OFF" && mode!="DEFER" && mode!="DEFER_PREFETCH") return 3;
    llama_backend_init();
    auto mp=llama_model_default_params();
    mp.n_gpu_layers=0; mp.use_mmap=true; mp.use_mlock=false;
    mp.dry_run=false; mp.repack_tensors=false; mp.merge_qkv=false; mp.merge_up_gate_exps=false;
    mp.check_tensors=false; mp.validate_quants=false; mp.use_thp=false;
    mp.defer_experts=mode!="OFF";
    loading=true;
    auto *m=llama_model_load_from_file(argv[1],mp);
    loading=false;
    if (!m || llama_n_vocab(m)!=32) return 4;
    for (int l=0;l<2;++l) for (auto role:{"gate","up","down"}) for(auto kind:{"weight","bias"})
        inspect(m,"blk."+std::to_string(l)+".ffn_"+role+"_exps."+kind);
    auto cp=llama_context_default_params();
    cp.n_ctx=64; cp.n_batch=8; cp.n_ubatch=8; cp.n_threads=1; cp.n_threads_batch=1;
    cp.offload_kqv=false; cp.prefetch_experts=mode=="DEFER_PREFETCH"; cp.prefetch_experts_threads=4;
    int before=tasks();
    auto *ctx=llama_init_from_model(m,cp);
    if (!ctx) return 5;
    std::printf("POOL %d %d %d\n",before,tasks(),int(ggml_moe_prefetch_enabled()));
    llama_token token=7;
    if (llama_decode(ctx,llama_batch_get_one(&token,1,0,0))) return 6;
    auto *logits=llama_get_logits_ith(ctx,-1);
    if (!logits) return 7;
    for (int i=0;i<32;++i) if (!std::isfinite(logits[i])) return 8;
    std::ofstream out(argv[3],std::ios::binary); out.write(reinterpret_cast<char *>(logits),128);
    out.close(); if (!out) return 9;
    llama_free(ctx); llama_free_model(m); llama_backend_free();
    struct rusage r{}; if (getrusage(RUSAGE_SELF,&r)) return 10;
    std::printf("RSS %ld\n",r.ru_maxrss);
    return 0;
}
