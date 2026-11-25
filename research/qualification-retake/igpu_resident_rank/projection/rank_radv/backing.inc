#include <sys/mman.h>
#include <sys/syscall.h>
#include <linux/memfd.h>
#include <sstream>

constexpr size_t window_bytes=13221888;
constexpr size_t rank_bytes=4406400;
constexpr size_t pool_bytes=40*window_bytes;
constexpr uint32_t phys_slot=3;

struct Record {
    int expert, generation;
    off_t offset;
    const char *hashes[3];
};
static const Record records[2]{
    {28,6,371245056,{
      "3a76d368a4c215dafd9d39e740d1db137709d8bac6df70084c918656ec31cc50",
      "1845b508d3d93903a31617482aacb3fba47717ec7ff6139cccc865a578858e22",
      "9565a93dae40cd4d78532aab7c3aef0e80647183d05beac08b022a042e24b746"}},
    {24,7,318210048,{
      "160b94a05575d9783e7ba505815e70b2358958f88c82b1ef51e3cb4a856f18bf",
      "0412125e9c3eb2d7675a3def6826ff53f7257c4156a7516bc678ab5392fada45",
      "455efe08522ceff734b0d74a24cde57f9d907cafe980ce32bc1b8e77da155a24"}}
};

void pack_identity(int fd) {
    struct stat s{};
    need(!fstat(fd,&s) && s.st_dev==56 && s.st_ino==40137035 && s.st_size==61096329216LL &&
        s.st_mtim.tv_sec==1795615219 && s.st_mtim.tv_nsec==800191666 &&
        s.st_ctim.tv_sec==1795615266 && s.st_ctim.tv_nsec==599091242,"pack FD seal");
}

void identify_vma(const void *ptr, const struct stat &st, bool writable) {
    std::ifstream maps("/proc/self/maps");
    std::string line;
    while (std::getline(maps,line)) {
        unsigned long begin=0,end=0,off=1,ino=0;
        unsigned maj=0,min=0; char perms[5]{};
        if (std::sscanf(line.c_str(),"%lx-%lx %4s %lx %x:%x %lu",&begin,&end,perms,&off,&maj,&min,&ino)!=7) continue;
        if (begin!=reinterpret_cast<uintptr_t>(ptr)) continue;
        need(end-begin==window_bytes && off==0 && ino==st.st_ino && makedev(maj,min)==st.st_dev &&
             !strcmp(perms,writable ? "rw-s":"r--s"),"bad physical slot/host-import alias");
        return;
    }
    throw std::runtime_error("missing window mapping");
}

struct SlotPool {
    const ProjectionDevice &p;
    int pack;
    unsigned char *base;
    const Record *record=nullptr;
    int fd=-1, previous_fd=-1;
    unsigned char *alias=nullptr;
    VkBuffer gpu_buffer{};
    VkDeviceMemory gpu_memory{};
    bool held=false;
    struct stat st{};
    void *crypto;
    decltype(&SHA256) sha;
    size_t descriptor_alignment=0;

    explicit SlotPool(const ProjectionDevice &device,const char *path):p(device) {
        pack=open(path,O_RDONLY|O_NOFOLLOW|O_CLOEXEC);need(pack>=0,"pack");pack_identity(pack);
        base=static_cast<unsigned char*>(mmap(nullptr,pool_bytes,PROT_NONE,
            MAP_PRIVATE|MAP_ANONYMOUS|MAP_NORESERVE,-1,0));
        need(base!=MAP_FAILED,"reserve virtual 40-window pool");
        crypto=dlopen("/usr/lib64/libcrypto.so.3",RTLD_NOW|RTLD_LOCAL);need(crypto,"libcrypto");
        void *address=dlsym(crypto,"SHA256");Dl_info info{};
        need(address && dladdr(address,&info) && std::filesystem::canonical(info.dli_fname)==
             std::filesystem::canonical("/usr/lib64/libcrypto.so.3"),"SHA provider");
        sha=reinterpret_cast<decltype(&SHA256)>(address);
        VkPhysicalDeviceProperties pr{};vkGetPhysicalDeviceProperties(p.gpu,&pr);
        descriptor_alignment=pr.limits.minStorageBufferOffsetAlignment;
        supported(descriptor_alignment>0 && (2*rank_bytes)%descriptor_alignment==0,"up descriptor alignment");
    }
    unsigned char *cpu() const {return base+phys_slot*window_bytes;}
    void integrity() {
        identify_vma(cpu(),st,false);identify_vma(alias,st,true);
        for(int role=0;role<3;++role) {
            unsigned char hash[32]{};
            need(sha(cpu()+role*rank_bytes,rank_bytes,hash)!=nullptr,"weight digest");
            char hex[65]{};for(size_t i=0;i<32;++i) std::snprintf(hex+2*i,3,"%02x",hash[i]);
            need(!strcmp(hex,record->hashes[role]),"slot/role content");
        }
    }
    static void require_unsupported(const char *what,size_t wanted,size_t maximum) {
        std::printf("unsupported_size\t%s\t%zu\t%zu\n",what,wanted,maximum);
        throw Unsupported(what);
    }
    void import() {
        VkExternalMemoryBufferCreateInfo ext{VK_STRUCTURE_TYPE_EXTERNAL_MEMORY_BUFFER_CREATE_INFO};
        ext.handleTypes=host_type;
        VkBufferCreateInfo ci{VK_STRUCTURE_TYPE_BUFFER_CREATE_INFO,&ext};
        ci.size=window_bytes;ci.usage=usage;ci.sharingMode=VK_SHARING_MODE_EXCLUSIVE;
        vk(vkCreateBuffer(p.dev,&ci,nullptr,&gpu_buffer),"file-backed storage buffer");
        VkMemoryRequirements mr{};vkGetBufferMemoryRequirements(p.dev,gpu_buffer,&mr);
        if(mr.size > window_bytes) require_unsupported("allocation exceeds C291 backing",mr.size,window_bytes);
        supported(window_bytes%p.align==0 && uintptr_t(alias)%p.align==0,"file mapping pointer alignment");
        VkMemoryHostPointerPropertiesEXT hp{VK_STRUCTURE_TYPE_MEMORY_HOST_POINTER_PROPERTIES_EXT};
        const auto allowed=p.pointers(p.dev,host_type,alias,&hp);
        if(allowed==VK_ERROR_INVALID_EXTERNAL_HANDLE) throw Unsupported("driver rejected file-backed host pointer");
        vk(allowed,"file pointer");
        uint32_t type=0;
        for(;type<p.memory.memoryTypeCount;++type) {
            if((mr.memoryTypeBits&hp.memoryTypeBits&(1u<<type)) &&
               (p.memory.memoryTypes[type].propertyFlags&coherent)==coherent)break;
        }
        supported(type<p.memory.memoryTypeCount,"no compatible coherent file memory type");
        VkMemoryDedicatedAllocateInfo di{VK_STRUCTURE_TYPE_MEMORY_DEDICATED_ALLOCATE_INFO};di.buffer=gpu_buffer;
        VkImportMemoryHostPointerInfoEXT hi{VK_STRUCTURE_TYPE_IMPORT_MEMORY_HOST_POINTER_INFO_EXT};
        hi.handleType=host_type;hi.pHostPointer=alias;hi.pNext=p.dedicated ? &di:nullptr;
        supported(!p.dedicated || mr.size==window_bytes,"dedicated allocation mismatch");
        VkMemoryAllocateInfo ai{VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO,&hi};
        ai.allocationSize=window_bytes;ai.memoryTypeIndex=type;
        const auto r=vkAllocateMemory(p.dev,&ai,nullptr,&gpu_memory);
        if(r==VK_ERROR_INVALID_EXTERNAL_HANDLE)throw Unsupported("RADV cannot import the C291 memfd VMA");
        vk(r,"file-backed import");vk(vkBindBufferMemory(p.dev,gpu_buffer,gpu_memory,0),"bind C291 backing");
        std::printf("window_import\t%d\t%lu\t%zu\t%zu\t%zu\t%zu\t%u\t%u\t%u\t%u\n",
            record->generation,(unsigned long)st.st_ino,window_bytes,size_t(mr.size),size_t(mr.alignment),
            descriptor_alignment,type,hp.memoryTypeBits,mr.memoryTypeBits,p.memory.memoryTypes[type].propertyFlags);
    }
    bool publish(const Record &next) {
        if(held)return false;
        if(record) {
            integrity();
            vkDestroyBuffer(p.dev,gpu_buffer,nullptr);vkFreeMemory(p.dev,gpu_memory,nullptr);
            need(!munmap(alias,window_bytes),"unmap retired import");
            previous_fd=fd; // Keep old inode live across replacement and distinct from the new one.
        }
        record=&next;
        fd=int(syscall(SYS_memfd_create,"tesy-rank-window",MFD_CLOEXEC));
        need(fd>=0 && ftruncate(fd,window_bytes)==0 && !fstat(fd,&st),"allocate one backing");
        alias=static_cast<unsigned char*>(mmap(nullptr,window_bytes,PROT_READ|PROT_WRITE,MAP_SHARED,fd,0));
        need(alias!=MAP_FAILED,"host import alias");
        pack_identity(pack);
        need(pread(pack,alias,window_bytes,record->offset)==ssize_t(window_bytes),"load into backing");
        pack_identity(pack);
        need(mmap(cpu(),window_bytes,PROT_READ,MAP_SHARED|MAP_FIXED,fd,0)==cpu(),"publish CPU slot");
        integrity();import();
        std::printf("publish\t%u\t%d\t%d\t%lu\t%zu\t%zu\t%zu\n",phys_slot,next.expert,next.generation,
                    (unsigned long)st.st_ino,window_bytes,size_t(next.offset),size_t(cpu()-base));
        return true;
    }
    bool acquire(unsigned slot,int gen) {
        if (held || slot!=phys_slot || !record || gen!=record->generation)return false;
        held=true;
        std::printf("acquire\t%u\t%d\t%lu\n",slot,gen,(unsigned long)st.st_ino);
        return true;
    }
    VkDescriptorBufferInfo view(int role) {
        need(held && (role==0 || role==2),"live role lease");
        return {gpu_buffer,role*rank_bytes,rank_bytes};
    }
    void release() {
        need(held,"release");held=false;
        std::printf("release_after_fence\t%d\t%lu\n",record->generation,(unsigned long)st.st_ino);
    }
    void cleanup() {
        need(!held && previous_fd>=0,"readers drained");integrity();pack_identity(pack);
        vkDestroyBuffer(p.dev,gpu_buffer,nullptr);vkFreeMemory(p.dev,gpu_memory,nullptr);
        need(!munmap(alias,window_bytes) && !munmap(base,pool_bytes),"release mappings");
        need(!close(fd) && !close(previous_fd) && !close(pack) && !dlclose(crypto),"close authorities");
    }
};
