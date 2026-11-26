// Single-device, headless Vulkan host import. No shader, weight file or network input.
#include <vulkan/vulkan_core.h>
#include <algorithm>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <stdexcept>
#include <string>
#include <vector>
#include <sys/stat.h>
#include <sys/sysmacros.h>

constexpr size_t payload = 3 * 4406400;
constexpr VkBufferUsageFlags usage = VK_BUFFER_USAGE_STORAGE_BUFFER_BIT |
    VK_BUFFER_USAGE_TRANSFER_SRC_BIT | VK_BUFFER_USAGE_TRANSFER_DST_BIT;
constexpr auto host_type = VK_EXTERNAL_MEMORY_HANDLE_TYPE_HOST_ALLOCATION_BIT_EXT;
constexpr VkMemoryPropertyFlags coherent = VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT | VK_MEMORY_PROPERTY_HOST_COHERENT_BIT;

void need(bool ok, const char *why) { if (!ok) throw std::runtime_error(why); }
struct Unsupported : std::runtime_error { using std::runtime_error::runtime_error; };
void supported(bool ok, const char *why) { if (!ok) throw Unsupported(why); }
void vk(VkResult r, const char *step) {
    if (r != VK_SUCCESS) throw std::runtime_error(std::string(step) + ": " + std::to_string(r));
}
std::string line(std::filesystem::path p) {
    std::ifstream f(p);
    std::string s;
    need(bool(std::getline(f, s)), "read cgroup field");
    return s;
}
void guard() {
    std::string cp = line("/proc/self/cgroup");
    need(cp.rfind("0::/", 0) == 0 && cp.find("/tesy-igpu-rank-") != std::string::npos, "own scope");
    std::filesystem::path d("/sys/fs/cgroup" + cp.substr(3));
    need(line(d/"memory.high") == "134217728" && line(d/"memory.max") == "134217728" &&
         line(d/"memory.swap.max") == "0" && line(d/"memory.swap.current") == "0", "scope caps");
    std::printf("scope_peak_bytes\t%s\n", line(d/"memory.peak").c_str());
}
void providers() {
    std::ifstream f("/proc/self/maps");
    std::string s;
    bool radv=false, loader=false, drm=false;
    while (std::getline(f,s)) {
        const size_t slash = s.find('/');
        if (slash == std::string::npos) continue;
        const auto p = s.substr(slash);
        if (p.find("libvulkan") != std::string::npos && p.find(".so") != std::string::npos) {
            if (p == "/usr/lib64/libvulkan_radeon.so") radv=true;
            else if (p == "/usr/lib64/libvulkan.so.1.4.341") loader=true;
            else throw std::runtime_error("foreign Vulkan provider " + p);
        }
        need(p.find("libnvidia") == std::string::npos && p.find("libcuda.so") == std::string::npos, "foreign NVIDIA provider");
    }
    for (const auto &p : std::filesystem::directory_iterator("/proc/self/fd")) {
        struct stat st{};
        if (stat(p.path().c_str(), &st) || !S_ISCHR(st.st_mode) || major(st.st_rdev)!=226) continue;
        need(minor(st.st_rdev)==128 || minor(st.st_rdev)==1, "foreign DRM FD");
        drm |= minor(st.st_rdev)==128;
    }
    need(radv && loader && drm, "loader, RADV or renderD128 absent");
    std::puts("providers\tRADV+loader+renderD128");
}
size_t rounded(size_t n, size_t a) {
    need(a && (a & (a-1)) == 0 && a <= (1u<<20), "host alignment out of budget");
    return (n+a-1) & ~(a-1);
}
struct Imported { VkBuffer b{}; VkDeviceMemory mem{}; uint32_t *p{}; size_t bytes{}; };
Imported buffer(VkDevice dev, const VkPhysicalDeviceMemoryProperties &mp, size_t align,
                PFN_vkGetMemoryHostPointerPropertiesEXT get, bool dedicated) {
    Imported v;
    VkExternalMemoryBufferCreateInfo ext{VK_STRUCTURE_TYPE_EXTERNAL_MEMORY_BUFFER_CREATE_INFO};
    ext.handleTypes=host_type;
    VkBufferCreateInfo cb{VK_STRUCTURE_TYPE_BUFFER_CREATE_INFO, &ext};
    cb.size=rounded(payload, std::max<size_t>(65536,align)); cb.usage=usage;
    cb.sharingMode=VK_SHARING_MODE_EXCLUSIVE;
    vk(vkCreateBuffer(dev,&cb,nullptr,&v.b),"create buffer");
    VkMemoryRequirements mr{};
    vkGetBufferMemoryRequirements(dev,v.b,&mr);
    v.bytes=rounded(mr.size,align);
    need(v.bytes <= 16u<<20 && (!dedicated || v.bytes==mr.size), "import size budget");
    void *base=nullptr;
    need(!posix_memalign(&base,std::max<size_t>(4096,align),v.bytes),"allocate host");
    v.p=static_cast<uint32_t*>(base);
    std::memset(base,0,v.bytes);
    VkMemoryHostPointerPropertiesEXT hp{VK_STRUCTURE_TYPE_MEMORY_HOST_POINTER_PROPERTIES_EXT};
    vk(get(dev,host_type,base,&hp),"query host pointer");
    const auto eligible=hp.memoryTypeBits & mr.memoryTypeBits;
    uint32_t t=0;
    while(t<mp.memoryTypeCount && (!(eligible & (1u<<t)) ||
        (mp.memoryTypes[t].propertyFlags & coherent)!=coherent)) ++t;
    supported(t<mp.memoryTypeCount,"no compatible coherent host import");
    VkMemoryDedicatedAllocateInfo di{VK_STRUCTURE_TYPE_MEMORY_DEDICATED_ALLOCATE_INFO};
    di.buffer=v.b;
    VkImportMemoryHostPointerInfoEXT ip{VK_STRUCTURE_TYPE_IMPORT_MEMORY_HOST_POINTER_INFO_EXT};
    ip.pNext=dedicated ? &di : nullptr; ip.handleType=host_type; ip.pHostPointer=base;
    VkMemoryAllocateInfo ci{VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO,&ip};
    ci.allocationSize=v.bytes; ci.memoryTypeIndex=t;
    vk(vkAllocateMemory(dev,&ci,nullptr,&v.mem),"import host pages");
    vk(vkBindBufferMemory(dev,v.b,v.mem,0),"bind");
    std::printf("import\t%zu\t%zu\t%u\t%u\t%u\t%u\t%u\n",v.bytes,size_t(mr.alignment),
        hp.memoryTypeBits,mr.memoryTypeBits,t,mp.memoryTypes[t].heapIndex,mp.memoryTypes[t].propertyFlags);
    return v;
}
uint32_t word(size_t i, uint32_t generation) { return uint32_t(i)*2654435761u ^ (0x6a09e667u*generation); }
void run() {
    guard();
    VkApplicationInfo app{VK_STRUCTURE_TYPE_APPLICATION_INFO}; app.apiVersion=VK_API_VERSION_1_2;
    VkInstanceCreateInfo ic{VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO}; ic.pApplicationInfo=&app;
    VkInstance in{}; vk(vkCreateInstance(&ic,nullptr,&in),"instance");
    uint32_t n=0; vk(vkEnumeratePhysicalDevices(in,&n,nullptr),"device count");
    need(n==1,"expected one physical device");
    VkPhysicalDevice gpu{}; vk(vkEnumeratePhysicalDevices(in,&n,&gpu),"device");
    vk(vkEnumerateDeviceExtensionProperties(gpu,nullptr,&n,nullptr),"extension count");
    std::vector<VkExtensionProperties> ex(n);
    vk(vkEnumerateDeviceExtensionProperties(gpu,nullptr,&n,ex.data()),"extensions");
    for (const char *name : {"VK_EXT_external_memory_host","VK_EXT_pci_bus_info"}) {
        supported(std::any_of(ex.begin(),ex.end(),[&](auto &e){ return !strcmp(e.extensionName,name); }),name);
    }
    VkPhysicalDeviceExternalMemoryHostPropertiesEXT hp{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_EXTERNAL_MEMORY_HOST_PROPERTIES_EXT};
    VkPhysicalDevicePCIBusInfoPropertiesEXT pci{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_PCI_BUS_INFO_PROPERTIES_EXT,&hp};
    VkPhysicalDeviceDriverProperties dp{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_DRIVER_PROPERTIES,&pci};
    VkPhysicalDeviceProperties2 pp{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_PROPERTIES_2,&dp};
    vkGetPhysicalDeviceProperties2(gpu,&pp);
    const auto &p=pp.properties;
    std::printf("device\t%s\t%s\t%04x:%02x:%02x.%x\t%u\t%u\t%u\t%zu\n",p.deviceName,dp.driverName,pci.pciDomain,
        pci.pciBus,pci.pciDevice,pci.pciFunction,p.vendorID,p.deviceID,p.deviceType,size_t(hp.minImportedHostPointerAlignment));
    need(p.vendorID==0x1002 && p.deviceID==0x150e && p.deviceType==VK_PHYSICAL_DEVICE_TYPE_INTEGRATED_GPU
        && dp.driverID==VK_DRIVER_ID_MESA_RADV && pci.pciDomain==0 && pci.pciBus==0xc5 && !pci.pciDevice && !pci.pciFunction,"GPU identity");
    VkPhysicalDeviceMemoryProperties mp{}; vkGetPhysicalDeviceMemoryProperties(gpu,&mp);
    for(uint32_t i=0;i<mp.memoryHeapCount;++i) std::printf("heap\t%u\t%llu\t%u\n",i,(unsigned long long)mp.memoryHeaps[i].size,mp.memoryHeaps[i].flags);
    for(uint32_t i=0;i<mp.memoryTypeCount;++i) std::printf("type\t%u\t%u\t%u\n",i,mp.memoryTypes[i].heapIndex,mp.memoryTypes[i].propertyFlags);
    VkPhysicalDeviceExternalBufferInfo eb{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_EXTERNAL_BUFFER_INFO}; eb.handleType=host_type; eb.usage=usage;
    VkExternalBufferProperties bp{VK_STRUCTURE_TYPE_EXTERNAL_BUFFER_PROPERTIES};
    vkGetPhysicalDeviceExternalBufferProperties(gpu,&eb,&bp);
    const auto features=bp.externalMemoryProperties.externalMemoryFeatures;
    std::printf("external_features\t%u\n",features);
    supported(features & VK_EXTERNAL_MEMORY_FEATURE_IMPORTABLE_BIT,"not importable for STORAGE+TRANSFER");
    vkGetPhysicalDeviceQueueFamilyProperties(gpu,&n,nullptr);
    std::vector<VkQueueFamilyProperties> qs(n); vkGetPhysicalDeviceQueueFamilyProperties(gpu,&n,qs.data());
    uint32_t q=0; while(q<n && !(qs[q].queueFlags & VK_QUEUE_COMPUTE_BIT)) ++q;
    supported(q<n, "no compute queue"); std::printf("queue\t%u\t%u\n",q,qs[q].queueFlags);
    float prio=1; VkDeviceQueueCreateInfo qc{VK_STRUCTURE_TYPE_DEVICE_QUEUE_CREATE_INFO};
    qc.queueFamilyIndex=q; qc.queueCount=1; qc.pQueuePriorities=&prio;
    const char *extension="VK_EXT_external_memory_host";
    VkDeviceCreateInfo dc{VK_STRUCTURE_TYPE_DEVICE_CREATE_INFO}; dc.queueCreateInfoCount=1; dc.pQueueCreateInfos=&qc;
    dc.enabledExtensionCount=1;dc.ppEnabledExtensionNames=&extension;
    VkDevice dev{}; vk(vkCreateDevice(gpu,&dc,nullptr,&dev),"create device");
    auto get=reinterpret_cast<PFN_vkGetMemoryHostPointerPropertiesEXT>(vkGetDeviceProcAddr(dev,"vkGetMemoryHostPointerPropertiesEXT"));
    need(get,"missing import entry point");
    providers();
    auto a=buffer(dev,mp,hp.minImportedHostPointerAlignment,get,features & VK_EXTERNAL_MEMORY_FEATURE_DEDICATED_ONLY_BIT);
    auto b=buffer(dev,mp,hp.minImportedHostPointerAlignment,get,features & VK_EXTERNAL_MEMORY_FEATURE_DEDICATED_ONLY_BIT);
    VkQueue queue{}; vkGetDeviceQueue(dev,q,0,&queue);
    VkCommandPoolCreateInfo pc{VK_STRUCTURE_TYPE_COMMAND_POOL_CREATE_INFO};pc.queueFamilyIndex=q;
    VkCommandPool pool{};vk(vkCreateCommandPool(dev,&pc,nullptr,&pool),"pool");
    VkCommandBufferAllocateInfo ac{VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO};ac.commandPool=pool;ac.commandBufferCount=1;
    VkCommandBuffer cb{};vk(vkAllocateCommandBuffers(dev,&ac,&cb),"command buffer");
    VkCommandBufferBeginInfo bi{VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO};vk(vkBeginCommandBuffer(cb,&bi),"begin");
    VkMemoryBarrier barrier{VK_STRUCTURE_TYPE_MEMORY_BARRIER};barrier.srcAccessMask=VK_ACCESS_HOST_WRITE_BIT;
    barrier.dstAccessMask=VK_ACCESS_TRANSFER_READ_BIT|VK_ACCESS_TRANSFER_WRITE_BIT;
    vkCmdPipelineBarrier(cb,VK_PIPELINE_STAGE_HOST_BIT,VK_PIPELINE_STAGE_TRANSFER_BIT,0,1,&barrier,0,nullptr,0,nullptr);
    VkBufferCopy copy{0,0,payload};vkCmdCopyBuffer(cb,a.b,b.b,1,&copy);
    barrier.srcAccessMask=VK_ACCESS_TRANSFER_WRITE_BIT;barrier.dstAccessMask=VK_ACCESS_HOST_READ_BIT;
    vkCmdPipelineBarrier(cb,VK_PIPELINE_STAGE_TRANSFER_BIT,VK_PIPELINE_STAGE_HOST_BIT,0,1,&barrier,0,nullptr,0,nullptr);
    vk(vkEndCommandBuffer(cb),"end");
    VkFenceCreateInfo fc{VK_STRUCTURE_TYPE_FENCE_CREATE_INFO};VkFence fence{};vk(vkCreateFence(dev,&fc,nullptr,&fence),"fence");
    VkSubmitInfo submit{VK_STRUCTURE_TYPE_SUBMIT_INFO};submit.commandBufferCount=1;submit.pCommandBuffers=&cb;
    for(uint32_t g : {1u,2u}) {
        for(size_t i=0;i<payload/4;++i){a.p[i]=word(i,g);b.p[i]=~word(i,g);}
        vk(vkQueueSubmit(queue,1,&submit,fence),"submit");
        vk(vkWaitForFences(dev,1,&fence,VK_TRUE,1000000000),"fence within 1 s");
        size_t same=0,wrong=0;
        for(size_t i=0;i<payload/4;++i) { same+=b.p[i]==word(i,g); wrong+=b.p[i]!=word(i,3-g); }
        std::printf("generation\t%u\t%zu\t%zu\n",g,same,wrong);
        need(same==payload/4 && wrong==payload/4,"direct CPU result");
        vk(vkResetFences(dev,1,&fence),"reset");
    }
    vkDestroyFence(dev,fence,nullptr);vkDestroyCommandPool(dev,pool,nullptr);
    for(auto v : {a,b}){vkDestroyBuffer(dev,v.b,nullptr);vkFreeMemory(dev,v.mem,nullptr);free(v.p);}
    vkDestroyDevice(dev,nullptr);vkDestroyInstance(in,nullptr);guard();
}
int main() {
    setvbuf(stdout,nullptr,_IOLBF,0);
    try {run();std::puts("PASS_HOST_IMPORT_COPY_ONLY");return 0;}
    catch(const Unsupported &e) {std::printf("NOT_ADMITTED\t%s\n",e.what());return 3;}
    catch(const std::exception &e) {std::fprintf(stderr,"FAIL\t%s\n",e.what());return 2;}
}
