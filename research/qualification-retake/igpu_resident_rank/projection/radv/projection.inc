#include <openssl/sha.h>
#include <fcntl.h>
#include <unistd.h>
#include <dlfcn.h>

constexpr uint32_t matrix_bytes = 4406400;
constexpr uint32_t slot_count = 4;
constexpr uint32_t line_bytes = 2880 * 4;

struct ProjectionDevice {
    VkPhysicalDevice gpu;
    VkDevice dev;
    VkQueue queue;
    uint32_t family;
    VkPhysicalDeviceMemoryProperties memory;
    size_t align;
    PFN_vkGetMemoryHostPointerPropertiesEXT pointers;
    bool dedicated;
    uint32_t subgroup;
};

void load_weight(const char *path, unsigned char *dest) {
    Dl_info provider{};
    need(dladdr(reinterpret_cast<void*>(SHA256),&provider) &&
        std::filesystem::canonical(provider.dli_fname) == std::filesystem::canonical("/usr/lib64/libcrypto.so.3"),
        "SHA256 provider");
    int fd=open(path,O_RDONLY|O_NOFOLLOW|O_CLOEXEC);
    need(fd>=0,"open existing pack");
    auto stat_ok=[&]() {
        struct stat s{};
        need(!fstat(fd,&s) && s.st_dev==56 && s.st_ino==40137035 && s.st_size==61096329216LL &&
            s.st_mtim.tv_sec==1795615219 && s.st_mtim.tv_nsec==800191666 &&
            s.st_ctim.tv_sec==1795615266 && s.st_ctim.tv_nsec==599091242, "pack FD seal");
    };
    stat_ok();
    need(pread(fd,dest,matrix_bytes,371245056) == matrix_bytes,"pack gate extent");
    unsigned char hash[32];need(SHA256(dest,matrix_bytes,hash) != nullptr,"weight SHA256");
    char hex[65]{};
    for(size_t i=0;i<32;++i) std::snprintf(hex+2*i,3,"%02x",hash[i]);
    need(!strcmp(hex,"3a76d368a4c215dafd9d39e740d1db137709d8bac6df70084c918656ec31cc50"),"gate SHA");
    stat_ok();need(!close(fd),"pack close");
    std::printf("weight\t%s\t%u\t%u\t%u\n",hex,matrix_bytes,3*matrix_bytes,371245056);
}

void project(const ProjectionDevice &p, const Imported &rhs, char **args) {
    auto getbuf=[&](size_t n){return buffer(p.dev,p.memory,p.align,p.pointers,p.dedicated,n);};
    auto weight=getbuf(matrix_bytes*slot_count), ids=getbuf(16), dst=getbuf(line_bytes);
    load_weight(args[5],reinterpret_cast<unsigned char*>(weight.p)+3*matrix_bytes);
    auto spv=words(args[6],20,1<<20);
    VkShaderModuleCreateInfo mi{VK_STRUCTURE_TYPE_SHADER_MODULE_CREATE_INFO};
    mi.codeSize=spv.size()*4;mi.pCode=spv.data();
    VkShaderModule mod{};vk(vkCreateShaderModule(p.dev,&mi,nullptr,&mod),"MMVQ module");
    VkDescriptorSetLayoutBinding bindings[6]{};
    for(uint32_t i=0;i<6;++i) bindings[i]={i,VK_DESCRIPTOR_TYPE_STORAGE_BUFFER,1,VK_SHADER_STAGE_COMPUTE_BIT,nullptr};
    VkDescriptorSetLayoutCreateInfo li{VK_STRUCTURE_TYPE_DESCRIPTOR_SET_LAYOUT_CREATE_INFO};
    li.bindingCount=6;li.pBindings=bindings;
    VkDescriptorSetLayout layout{};vk(vkCreateDescriptorSetLayout(p.dev,&li,nullptr,&layout),"MMVQ binding layout");
    VkPushConstantRange range{VK_SHADER_STAGE_COMPUTE_BIT,0,48};
    VkPipelineLayoutCreateInfo pi{VK_STRUCTURE_TYPE_PIPELINE_LAYOUT_CREATE_INFO};
    pi.setLayoutCount=1;pi.pSetLayouts=&layout;pi.pushConstantRangeCount=1;pi.pPushConstantRanges=&range;
    VkPipelineLayout pl{};vk(vkCreatePipelineLayout(p.dev,&pi,nullptr,&pl),"MMVQ pipeline layout");
    const uint32_t spec_data[2]{p.subgroup,2};
    const VkSpecializationMapEntry entries[2]{{0,0,4},{1,4,4}};
    VkSpecializationInfo spec{2,entries,8,spec_data};
    VkPipelineShaderStageRequiredSubgroupSizeCreateInfoEXT rsg{VK_STRUCTURE_TYPE_PIPELINE_SHADER_STAGE_REQUIRED_SUBGROUP_SIZE_CREATE_INFO_EXT};
    rsg.requiredSubgroupSize=p.subgroup;
    VkComputePipelineCreateInfo ci{VK_STRUCTURE_TYPE_COMPUTE_PIPELINE_CREATE_INFO};
    ci.stage.sType=VK_STRUCTURE_TYPE_PIPELINE_SHADER_STAGE_CREATE_INFO;ci.stage.pNext=&rsg;
    ci.stage.flags=VK_PIPELINE_SHADER_STAGE_CREATE_REQUIRE_FULL_SUBGROUPS_BIT_EXT;
    ci.stage.stage=VK_SHADER_STAGE_COMPUTE_BIT;ci.stage.module=mod;ci.stage.pName="main";
    ci.stage.pSpecializationInfo=&spec;ci.layout=pl;
    VkPipeline pipeline{};vk(vkCreateComputePipelines(p.dev,VK_NULL_HANDLE,1,&ci,nullptr,&pipeline),"MMVQ pipeline");
    VkDescriptorPoolSize ps{VK_DESCRIPTOR_TYPE_STORAGE_BUFFER,6};
    VkDescriptorPoolCreateInfo dpci{VK_STRUCTURE_TYPE_DESCRIPTOR_POOL_CREATE_INFO};
    dpci.poolSizeCount=1;dpci.pPoolSizes=&ps;dpci.maxSets=1;
    VkDescriptorPool pool{};vk(vkCreateDescriptorPool(p.dev,&dpci,nullptr,&pool),"MMVQ descriptors");
    VkDescriptorSetAllocateInfo ai{VK_STRUCTURE_TYPE_DESCRIPTOR_SET_ALLOCATE_INFO};
    ai.descriptorPool=pool;ai.descriptorSetCount=1;ai.pSetLayouts=&layout;
    VkDescriptorSet ds{};vk(vkAllocateDescriptorSets(p.dev,&ai,&ds),"MMVQ descriptor set");
    VkDescriptorBufferInfo bufs[6]{{weight.b,0,matrix_bytes*slot_count},{rhs.b,0,3312},
        {dst.b,0,line_bytes},{dst.b,0,line_bytes},{dst.b,0,line_bytes},{ids.b,0,16}};
    VkWriteDescriptorSet writes[6]{};
    for(uint32_t i=0;i<6;++i) {
        writes[i].sType=VK_STRUCTURE_TYPE_WRITE_DESCRIPTOR_SET;writes[i].dstSet=ds;writes[i].dstBinding=i;
        writes[i].descriptorCount=1;writes[i].descriptorType=VK_DESCRIPTOR_TYPE_STORAGE_BUFFER;writes[i].pBufferInfo=&bufs[i];
    }
    vkUpdateDescriptorSets(p.dev,6,writes,0,nullptr);
    VkCommandPoolCreateInfo pc{VK_STRUCTURE_TYPE_COMMAND_POOL_CREATE_INFO};pc.queueFamilyIndex=p.family;
    VkCommandPool cp{};vk(vkCreateCommandPool(p.dev,&pc,nullptr,&cp),"MMVQ command pool");
    VkCommandBufferAllocateInfo ac{VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO};
    ac.commandPool=cp;ac.commandBufferCount=1;ac.level=VK_COMMAND_BUFFER_LEVEL_PRIMARY;
    VkCommandBuffer cmd{};vk(vkAllocateCommandBuffers(p.dev,&ac,&cmd),"MMVQ command buffer");
    VkCommandBufferBeginInfo begin{VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO};
    vk(vkBeginCommandBuffer(cmd,&begin),"MMVQ begin");
    VkMemoryBarrier barrier{VK_STRUCTURE_TYPE_MEMORY_BARRIER};
    barrier.srcAccessMask=VK_ACCESS_HOST_WRITE_BIT|VK_ACCESS_SHADER_WRITE_BIT;
    barrier.dstAccessMask=VK_ACCESS_SHADER_READ_BIT|VK_ACCESS_SHADER_WRITE_BIT;
    vkCmdPipelineBarrier(cmd,VK_PIPELINE_STAGE_HOST_BIT|VK_PIPELINE_STAGE_COMPUTE_SHADER_BIT,
        VK_PIPELINE_STAGE_COMPUTE_SHADER_BIT,0,1,&barrier,0,nullptr,0,nullptr);
    vkCmdBindPipeline(cmd,VK_PIPELINE_BIND_POINT_COMPUTE,pipeline);
    vkCmdBindDescriptorSets(cmd,VK_PIPELINE_BIND_POINT_COMPUTE,pl,0,1,&ds,0,nullptr);
    // The original four IDs have stride 4, the shared RHS has one row. Dispatch only rank 0.
    const uint32_t push[12]{2880,2880,2880,2880,2880*2880,2880,2880*4,0,4,1,0,4};
    vkCmdPushConstants(cmd,pl,VK_SHADER_STAGE_COMPUTE_BIT,0,sizeof(push),push);
    vkCmdDispatch(cmd,1440,1,1);
    barrier.srcAccessMask=VK_ACCESS_SHADER_WRITE_BIT;barrier.dstAccessMask=VK_ACCESS_HOST_READ_BIT;
    vkCmdPipelineBarrier(cmd,VK_PIPELINE_STAGE_COMPUTE_SHADER_BIT,VK_PIPELINE_STAGE_HOST_BIT,0,1,&barrier,0,nullptr,0,nullptr);
    vk(vkEndCommandBuffer(cmd),"MMVQ end");
    VkFenceCreateInfo fc{VK_STRUCTURE_TYPE_FENCE_CREATE_INFO};VkFence fence{};vk(vkCreateFence(p.dev,&fc,nullptr,&fence),"MMVQ fence");
    VkSubmitInfo submit{VK_STRUCTURE_TYPE_SUBMIT_INFO};submit.commandBufferCount=1;submit.pCommandBuffers=&cmd;
    for(unsigned i=0;i<2;++i) {
        const uint32_t physical[4]{i==0 ? 3u:2u,14u,6u,35u};
        std::memcpy(ids.p,physical,sizeof(physical));std::memset(dst.p,0xff,dst.bytes);
        vk(vkQueueSubmit(p.queue,1,&submit,fence),"MMVQ submit");
        vk(vkWaitForFences(p.dev,1,&fence,VK_TRUE,1000000000),"MMVQ complete");
        vk(vkResetFences(p.dev,1,&fence),"MMVQ reset");
        need(!std::memcmp(ids.p,physical,sizeof(physical)),"ID buffer mutated");
        const unsigned char *bytes=reinterpret_cast<unsigned char*>(dst.p);
        need(std::all_of(bytes+line_bytes,bytes+dst.bytes,[](auto v){return v==0xff;}),"MMVQ output guard");
        FILE *f=std::fopen(args[7+i],"wbx");need(f,"new F32 output");
        need(std::fwrite(bytes,1,line_bytes,f)==line_bytes && !std::fclose(f),"save MMVQ output");
        std::printf("projection\t%u\t1440\t1\t1\t%u\t2\t%u\n",physical[0],p.subgroup,line_bytes);
    }
    vkDestroyFence(p.dev,fence,nullptr);vkDestroyCommandPool(p.dev,cp,nullptr);vkDestroyDescriptorPool(p.dev,pool,nullptr);
    vkDestroyPipeline(p.dev,pipeline,nullptr);vkDestroyPipelineLayout(p.dev,pl,nullptr);
    vkDestroyDescriptorSetLayout(p.dev,layout,nullptr);vkDestroyShaderModule(p.dev,mod,nullptr);
    for(auto v:{weight,ids,dst}){vkDestroyBuffer(p.dev,v.b,nullptr);vkFreeMemory(p.dev,v.mem,nullptr);free(v.p);}
}
