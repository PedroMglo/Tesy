#include "records.inc"
#include <ggml.h>
#include <ggml-cpu.h>
#include <ggml-alloc.h>
#include <ggml-backend.h>

constexpr unsigned slot_ids[2]{3,14};
constexpr size_t shape_bytes=40*rank_bytes;

struct VkLease {
    VkBuffer b{};
    VkDeviceMemory m{};
    uintptr_t page{};
    size_t size{}, delta{};
    int role=-1, which=-1;
};

void verify_cpu_runtime() {
    std::ifstream maps("/proc/self/maps"); std::string s;
    bool cpu=false,base=false;
    while(std::getline(maps,s)) {
        const auto at=s.find('/');
        if(at==std::string::npos)continue;
        const auto name=s.substr(at);
        if(name.find("libggml-")==std::string::npos || name.find(".so")==std::string::npos)continue;
        if(name==CPU_DSO)cpu=true;
        else if(name==BASE_DSO)base=true;
        else throw std::runtime_error("foreign ggml DSO");
    }
    need(cpu && base,"authenticated GGML CPU/base providers");
}

struct SlotPool {
    const ProjectionDevice &p;
    ggml_backend_t cpu{};
    ggml_context *ctx{};
    ggml_backend_buffer_t owner{};
    ggml_tensor *t[3]{};
    VkLease lease{};
    int selected=-1;
    void *crypto{};
    decltype(&SHA256) sha;
    uintptr_t first{}, end{};
    size_t desc_align=0;

    unsigned char *weight(int r,int k) const {
        return static_cast<unsigned char*>(t[k]->data)+slot_ids[r]*rank_bytes;
    }
    void seal(int r,int k) const {
        unsigned char d[32]{};char hex[65]{};
        need(sha(weight(r,k),rank_bytes,d)!=nullptr,"SHA256 primary");
        for(size_t i=0;i<32;++i) std::snprintf(hex+2*i,3,"%02x",d[i]);
        need(!strcmp(hex,records[r].hashes[k]),"CPU tensor weight role/slot digest");
    }
    explicit SlotPool(const ProjectionDevice &device,const char *path):p(device) {
        verify_cpu_runtime();
        crypto=dlopen("/usr/lib64/libcrypto.so.3",RTLD_NOW|RTLD_LOCAL);need(crypto,"libcrypto");
        void *sym=dlsym(crypto,"SHA256");Dl_info info{};
        need(sym && dladdr(sym,&info) && std::filesystem::canonical(info.dli_fname)==
             std::filesystem::canonical("/usr/lib64/libcrypto.so.3"),"SHA provider");
        sha=reinterpret_cast<decltype(&SHA256)>(sym);
        cpu=ggml_backend_cpu_init();need(cpu,"native CPU backend");
        auto buft=ggml_backend_get_default_buffer_type(cpu);
        need(buft==ggml_backend_cpu_buffer_type() && !strcmp(ggml_backend_buft_name(buft),"CPU"),"default CPU buft");
        ctx=ggml_init({4*ggml_tensor_overhead()+4096,nullptr,true});need(ctx,"GGML metadata");
        for(auto &tensor:t)tensor=ggml_new_tensor_3d(ctx,GGML_TYPE_MXFP4,2880,2880,40);
        owner=ggml_backend_alloc_ctx_tensors_from_buft(ctx,buft);
        need(owner && ggml_backend_buffer_get_type(owner)==buft && ggml_backend_buffer_is_host(owner),"GGML CPU buffers");
        ggml_backend_buffer_set_usage(owner,GGML_BACKEND_BUFFER_USAGE_WEIGHTS);
        first=reinterpret_cast<uintptr_t>(ggml_backend_buffer_get_base(owner));
        end=first+ggml_backend_buffer_get_size(owner);
        need(first && end>first && end-first>=3*shape_bytes && end-first<=3*shape_bytes+4096,"owner range");
        for(int k=0;k<3;k++) {
            auto *tensor=t[k];
            auto a=reinterpret_cast<uintptr_t>(tensor->data);
            need(tensor->buffer==owner && tensor->type==GGML_TYPE_MXFP4 && tensor->ne[0]==2880 &&
                 tensor->ne[1]==2880 && tensor->ne[2]==40 && ggml_is_contiguous(tensor) &&
                 ggml_nbytes(tensor)==shape_bytes && tensor->nb[0]==17 && tensor->nb[1]==1530 &&
                 tensor->nb[2]==rank_bytes && a>=first && a<=end-shape_bytes,"dense GGML tensor");
            if(k)need(a>=reinterpret_cast<uintptr_t>(t[k-1]->data)+shape_bytes,"overlapping GGML tensors");
            std::printf("ggml_tensor\t%d\t%zu\t%zu\t%zu\t%zu\t%zu\n",k,size_t(a-first),shape_bytes,
                size_t(end-first),first%4096,a%4096);
        }
        VkPhysicalDeviceProperties pr{};vkGetPhysicalDeviceProperties(p.gpu,&pr);
        desc_align=pr.limits.minStorageBufferOffsetAlignment;need(desc_align>0,"storage descriptor alignment");
        int file=open(path,O_RDONLY|O_CLOEXEC|O_NOFOLLOW);need(file>=0,"pack");
        std::vector<unsigned char> stage(rank_bytes);
        for(int r=0;r<2;r++)for(int k=0;k<3;k++) {
            pack_identity(file);
            const auto off=records[r].offset+off_t(k*rank_bytes);
            need(pread(file,stage.data(),stage.size(),off)==ssize_t(stage.size()),"read one matrix");
            ggml_backend_tensor_set(t[k],stage.data(),slot_ids[r]*rank_bytes,rank_bytes);
            seal(r,k);
            std::printf("ggml_set\t%d\t%u\t%d\t%zu\t%zu\n",records[r].expert,slot_ids[r],k,size_t(off),rank_bytes);
        }
        pack_identity(file);need(!close(file),"close source");guard();
    }
    void anonymous_vma(uintptr_t a,uintptr_t b) const {
        std::ifstream maps("/proc/self/maps");std::string s;
        while(std::getline(maps,s)) {
            unsigned long lo=0,hi=0,off=0,ino=0;int tail=0;
            unsigned maj=0,min=0;char perm[5]{};
            if(std::sscanf(s.c_str(),"%lx-%lx %4s %lx %x:%x %lu %n",&lo,&hi,perm,&off,&maj,&min,&ino,&tail)!=7)continue;
            if(lo>a || hi<b)continue;
            const auto name=s.substr(tail);
            supported(!strcmp(perm,"rw-p") && !maj && !min && ino==0 &&
                (name.empty() || name=="[heap]" || name.rfind("[anon:",0)==0),"CPU weight VMA is not anonymous rw-p");
            return;
        }
        throw Unsupported("import crosses a VMA");
    }
    void select(int r){need(!lease.b && r>=0 && r<2,"live reader or invalid selection");selected=r;}
    VkDescriptorBufferInfo view(int role) {
        need(selected>=0 && (role==0 || role==2) && !lease.b,"valid role with no previous reader");
        const int r=selected;
        seal(r,role);
        const auto ptr=reinterpret_cast<uintptr_t>(weight(r,role));
        const auto page=ptr & ~(uintptr_t(p.align)-1);
        const auto delta=size_t(ptr-page), requested=delta+rank_bytes;
        supported(page>=first && (delta%desc_align)==0,"storage offset/owner alignment");
        VkExternalMemoryBufferCreateInfo ext{VK_STRUCTURE_TYPE_EXTERNAL_MEMORY_BUFFER_CREATE_INFO};
        ext.handleTypes=host_type;
        VkBufferCreateInfo ci{VK_STRUCTURE_TYPE_BUFFER_CREATE_INFO,&ext};
        ci.size=requested;ci.usage=usage;ci.sharingMode=VK_SHARING_MODE_EXCLUSIVE;
        vk(vkCreateBuffer(p.dev,&ci,nullptr,&lease.b),"GGML subrange");
        VkMemoryRequirements mr{};vkGetBufferMemoryRequirements(p.dev,lease.b,&mr);
        const size_t bytes=rounded(mr.size,p.align);
        supported(bytes>=requested && end-first>=bytes && page<=end-bytes &&
                  (!p.dedicated || bytes==mr.size),"GGML owner span");
        anonymous_vma(page,page+bytes);
        VkMemoryHostPointerPropertiesEXT hp{VK_STRUCTURE_TYPE_MEMORY_HOST_POINTER_PROPERTIES_EXT};
        const auto ret=p.pointers(p.dev,host_type,reinterpret_cast<void*>(page),&hp);
        if(ret==VK_ERROR_INVALID_EXTERNAL_HANDLE)throw Unsupported("CPU subrange pointer rejected");
        vk(ret,"query GGML pointer");
        uint32_t type=0;
        for(;type<p.memory.memoryTypeCount;++type) if((mr.memoryTypeBits&hp.memoryTypeBits&(1u<<type)) &&
               (p.memory.memoryTypes[type].propertyFlags&coherent)==coherent)break;
        supported(type<p.memory.memoryTypeCount,"no coherent GGML memory type");
        std::printf("primary_range\t%d\t%u\t%d\t%zu\t%zu\t%zu\t%zu\t%zu\t%zu\t%u\t%u\t%u\n",
            records[r].expert,slot_ids[r],role,size_t(page-first),delta,requested,size_t(mr.size),bytes,
            desc_align,type,hp.memoryTypeBits,mr.memoryTypeBits);
        VkMemoryDedicatedAllocateInfo di{VK_STRUCTURE_TYPE_MEMORY_DEDICATED_ALLOCATE_INFO};di.buffer=lease.b;
        VkImportMemoryHostPointerInfoEXT hi{VK_STRUCTURE_TYPE_IMPORT_MEMORY_HOST_POINTER_INFO_EXT};hi.handleType=host_type;
        hi.pHostPointer=reinterpret_cast<void*>(page);hi.pNext=p.dedicated ? &di:nullptr;
        VkMemoryAllocateInfo ai{VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO,&hi};
        ai.allocationSize=bytes;ai.memoryTypeIndex=type;
        auto res=vkAllocateMemory(p.dev,&ai,nullptr,&lease.m);
        if(res==VK_ERROR_INVALID_EXTERNAL_HANDLE)throw Unsupported("dense CPU buffer rejected at allocate");
        vk(res,"import dense CPU buffer");vk(vkBindBufferMemory(p.dev,lease.b,lease.m,0),"bind dense CPU buffer");
        lease.page=page;lease.delta=delta;lease.size=bytes;lease.role=role;lease.which=r;
        return {lease.b,delta,rank_bytes};
    }
    void release_after_fence() {
        need(lease.b && lease.m && selected==lease.which,"lease fence");
        auto k=lease.role;auto r=lease.which;
        vkDestroyBuffer(p.dev,lease.b,nullptr);vkFreeMemory(p.dev,lease.m,nullptr);
        lease={};seal(r,k);
        std::printf("released\t%d\t%u\t%d\t0\t11520\n",records[r].expert,slot_ids[r],k);
    }
    void cleanup() {
        need(!lease.b,"outstanding GGML reader");
        for(int r=0;r<2;r++)for(int k=0;k<3;k++)seal(r,k);
        ggml_backend_buffer_free(owner);ggml_free(ctx);ggml_backend_free(cpu);
        verify_cpu_runtime();need(!dlclose(crypto),"release crypto");
    }
};
