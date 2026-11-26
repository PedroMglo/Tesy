// The authenticated predecessor provides deployment, import, identity, queue and cgroup gates.
#include "host-functions.inc"
#include <array>
#include <chrono>
#include <iterator>

constexpr uint32_t width = 2880;
constexpr uint32_t output_size = 23 * 144;

std::vector<uint32_t> words(const char *path, size_t lo, size_t hi) {
    std::ifstream f(path,std::ios::binary | std::ios::ate);
    need(f.good(),"open input");
    const auto n = size_t(f.tellg());
    need(n >= lo && n <= hi && n % 4 == 0,"input size");
    std::vector<uint32_t> data(n/4);
    f.seekg(0);
    need(bool(f.read(reinterpret_cast<char*>(data.data()), n)),"read input");
    return data;
}

void compute(char **args) {
#include "host-acquire.inc"
    VkPhysicalDeviceSubgroupProperties sg{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_SUBGROUP_PROPERTIES};
    VkPhysicalDeviceProperties2 pr{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_PROPERTIES_2,&sg};
    vkGetPhysicalDeviceProperties2(gpu,&pr);
    const uint32_t group = sg.subgroupSize;
    const bool clustered = (sg.supportedStages & VK_SHADER_STAGE_COMPUTE_BIT) &&
        (sg.supportedOperations & VK_SUBGROUP_FEATURE_CLUSTERED_BIT);
    const bool has_size = std::any_of(ex.begin(), ex.end(), [](auto &e){
        return !strcmp(e.extensionName,"VK_EXT_subgroup_size_control");
    });
    VkPhysicalDeviceSubgroupSizeControlFeaturesEXT size{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_SUBGROUP_SIZE_CONTROL_FEATURES_EXT};
    VkPhysicalDeviceVulkan12Features f12{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_VULKAN_1_2_FEATURES};
    f12.pNext=has_size ? &size : nullptr;
    VkPhysicalDeviceVulkan11Features f11{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_VULKAN_1_1_FEATURES,&f12};
    VkPhysicalDeviceFeatures2 f2{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_FEATURES_2,&f11};
    vkGetPhysicalDeviceFeatures2(gpu,&f2);
    supported(group == 32 || group == 64,"unexpected AMD subgroup");
    const bool sub = clustered && size.computeFullSubgroups;
    supported(sub || (92 % (group/8) == 0),"partial shared-memory workgroup barrier");
    const uint32_t count = (width + 4*group-1)/(4*group);
    std::printf("variant\t%s\t%u\t%u\t%u\t%u\t%u\n",sub ? "subgroup":"shared",clustered,
                size.computeFullSubgroups,group,count,width);
    supported(f11.storageBuffer16BitAccess && f12.shaderInt8,"arithmetic and 16-bit storage");
    VkPhysicalDeviceFeatures core{};
    core.shaderInt16=f2.features.shaderInt16;
    core.shaderInt64=f2.features.shaderInt64;
    VkPhysicalDeviceSubgroupSizeControlFeaturesEXT eSize{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_SUBGROUP_SIZE_CONTROL_FEATURES_EXT};
    eSize.computeFullSubgroups=sub;
    VkPhysicalDeviceVulkan12Features e12{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_VULKAN_1_2_FEATURES};
    e12.shaderInt8=VK_TRUE; e12.shaderFloat16=f12.shaderFloat16;
    e12.pNext=sub ? &eSize : nullptr;
    VkPhysicalDeviceVulkan11Features e11{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_VULKAN_1_1_FEATURES,&e12};
    e11.storageBuffer16BitAccess=VK_TRUE;
    std::array<const char *,2> extNames{"VK_EXT_external_memory_host","VK_EXT_subgroup_size_control"};
    VkDeviceCreateInfo dc{VK_STRUCTURE_TYPE_DEVICE_CREATE_INFO,&e11};
    dc.queueCreateInfoCount=1; dc.pQueueCreateInfos=&qc; dc.pEnabledFeatures=&core;
    dc.enabledExtensionCount=sub ? 2 : 1; dc.ppEnabledExtensionNames=extNames.data();
    VkDevice dev{}; vk(vkCreateDevice(gpu,&dc,nullptr,&dev),"create device");
    auto get=reinterpret_cast<PFN_vkGetMemoryHostPointerPropertiesEXT>(vkGetDeviceProcAddr(dev,"vkGetMemoryHostPointerPropertiesEXT"));
    need(get,"host import entry");
    providers();
    auto input=buffer(dev,mp,hp.minImportedHostPointerAlignment,get,features & VK_EXTERNAL_MEMORY_FEATURE_DEDICATED_ONLY_BIT);
    auto dst=buffer(dev,mp,hp.minImportedHostPointerAlignment,get,features & VK_EXTERNAL_MEMORY_FEATURE_DEDICATED_ONLY_BIT);
    auto src=words(args[1],width*4,width*4);
    std::memcpy(input.p,src.data(),width*4); std::memset(dst.p,0xa5,dst.bytes);
    auto spv=words(args[sub ? 3:2],20,1<<20);
    need(spv[0]==0x07230203,"SPIR-V magic");
    VkShaderModuleCreateInfo sm{VK_STRUCTURE_TYPE_SHADER_MODULE_CREATE_INFO};
    sm.codeSize=spv.size()*4; sm.pCode=spv.data();
    VkShaderModule mod{}; vk(vkCreateShaderModule(dev,&sm,nullptr,&mod),"module");
    VkDescriptorSetLayoutBinding bindings[2]{};
    for(uint32_t i=0;i<2;++i) bindings[i]={i,VK_DESCRIPTOR_TYPE_STORAGE_BUFFER,1,VK_SHADER_STAGE_COMPUTE_BIT,nullptr};
    VkDescriptorSetLayoutCreateInfo li{VK_STRUCTURE_TYPE_DESCRIPTOR_SET_LAYOUT_CREATE_INFO};
    li.bindingCount=2; li.pBindings=bindings;
    VkDescriptorSetLayout layout{}; vk(vkCreateDescriptorSetLayout(dev,&li,nullptr,&layout),"descriptor layout");
    VkPushConstantRange range{VK_SHADER_STAGE_COMPUTE_BIT,0,8};
    VkPipelineLayoutCreateInfo pi{VK_STRUCTURE_TYPE_PIPELINE_LAYOUT_CREATE_INFO};
    pi.setLayoutCount=1; pi.pSetLayouts=&layout; pi.pushConstantRangeCount=1; pi.pPushConstantRanges=&range;
    VkPipelineLayout pl{}; vk(vkCreatePipelineLayout(dev,&pi,nullptr,&pl),"pipeline layout");
    VkSpecializationMapEntry entry{0,0,sizeof(group)};
    VkSpecializationInfo spec{1,&entry,sizeof(group),&group};
    VkComputePipelineCreateInfo ci{VK_STRUCTURE_TYPE_COMPUTE_PIPELINE_CREATE_INFO};
    ci.stage.sType=VK_STRUCTURE_TYPE_PIPELINE_SHADER_STAGE_CREATE_INFO;
    ci.stage.flags=sub ? VK_PIPELINE_SHADER_STAGE_CREATE_REQUIRE_FULL_SUBGROUPS_BIT_EXT : 0;
    ci.stage.stage=VK_SHADER_STAGE_COMPUTE_BIT; ci.stage.module=mod;
    ci.stage.pName="main"; ci.stage.pSpecializationInfo=&spec; ci.layout=pl;
    VkPipeline pipeline{};vk(vkCreateComputePipelines(dev,VK_NULL_HANDLE,1,&ci,nullptr,&pipeline),"compute pipeline");
    VkDescriptorPoolSize ps{VK_DESCRIPTOR_TYPE_STORAGE_BUFFER,2};
    VkDescriptorPoolCreateInfo dpci{VK_STRUCTURE_TYPE_DESCRIPTOR_POOL_CREATE_INFO};
    dpci.poolSizeCount=1;dpci.pPoolSizes=&ps;dpci.maxSets=1;
    VkDescriptorPool dpHandle{};vk(vkCreateDescriptorPool(dev,&dpci,nullptr,&dpHandle),"descriptor pool");
    VkDescriptorSetAllocateInfo dai{VK_STRUCTURE_TYPE_DESCRIPTOR_SET_ALLOCATE_INFO};
    dai.descriptorPool=dpHandle;dai.descriptorSetCount=1;dai.pSetLayouts=&layout;
    VkDescriptorSet ds{};vk(vkAllocateDescriptorSets(dev,&dai,&ds),"descriptor set");
    VkDescriptorBufferInfo buffers[2]{{input.b,0,width*4},{dst.b,0,output_size}};
    VkWriteDescriptorSet updates[2]{};
    for(uint32_t i=0;i<2;++i) {
        updates[i].sType=VK_STRUCTURE_TYPE_WRITE_DESCRIPTOR_SET;updates[i].dstSet=ds;updates[i].dstBinding=i;
        updates[i].descriptorCount=1;updates[i].descriptorType=VK_DESCRIPTOR_TYPE_STORAGE_BUFFER;updates[i].pBufferInfo=buffers+i;
    }
    vkUpdateDescriptorSets(dev,2,updates,0,nullptr);
    VkQueue queue{};vkGetDeviceQueue(dev,q,0,&queue);
    VkCommandPoolCreateInfo pc{VK_STRUCTURE_TYPE_COMMAND_POOL_CREATE_INFO};pc.queueFamilyIndex=q;
    VkCommandPool pool{};vk(vkCreateCommandPool(dev,&pc,nullptr,&pool),"command pool");
    VkCommandBufferAllocateInfo ac{VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO};
    ac.commandPool=pool;ac.commandBufferCount=1;ac.level=VK_COMMAND_BUFFER_LEVEL_PRIMARY;
    VkCommandBuffer cb{};vk(vkAllocateCommandBuffers(dev,&ac,&cb),"command buffer");
    VkCommandBufferBeginInfo bi{VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO};vk(vkBeginCommandBuffer(cb,&bi),"begin");
    VkMemoryBarrier barrier{VK_STRUCTURE_TYPE_MEMORY_BARRIER};
    barrier.srcAccessMask=VK_ACCESS_HOST_WRITE_BIT;barrier.dstAccessMask=VK_ACCESS_SHADER_READ_BIT|VK_ACCESS_SHADER_WRITE_BIT;
    vkCmdPipelineBarrier(cb,VK_PIPELINE_STAGE_HOST_BIT,VK_PIPELINE_STAGE_COMPUTE_SHADER_BIT,0,1,&barrier,0,nullptr,0,nullptr);
    vkCmdBindPipeline(cb,VK_PIPELINE_BIND_POINT_COMPUTE,pipeline);
    vkCmdBindDescriptorSets(cb,VK_PIPELINE_BIND_POINT_COMPUTE,pl,0,1,&ds,0,nullptr);
    uint32_t push[2]{width,count};vkCmdPushConstants(cb,pl,VK_SHADER_STAGE_COMPUTE_BIT,0,sizeof(push),push);
    vkCmdDispatch(cb,count,1,1);
    barrier.srcAccessMask=VK_ACCESS_SHADER_WRITE_BIT;barrier.dstAccessMask=VK_ACCESS_HOST_READ_BIT;
    vkCmdPipelineBarrier(cb,VK_PIPELINE_STAGE_COMPUTE_SHADER_BIT,VK_PIPELINE_STAGE_HOST_BIT,0,1,&barrier,0,nullptr,0,nullptr);
    vk(vkEndCommandBuffer(cb),"end");
    VkFenceCreateInfo fc{VK_STRUCTURE_TYPE_FENCE_CREATE_INFO};VkFence fence{};vk(vkCreateFence(dev,&fc,nullptr,&fence),"fence");
    VkSubmitInfo submit{VK_STRUCTURE_TYPE_SUBMIT_INFO};submit.commandBufferCount=1;submit.pCommandBuffers=&cb;
    auto start=std::chrono::steady_clock::now();
    vk(vkQueueSubmit(queue,1,&submit,fence),"submit");
    vk(vkWaitForFences(dev,1,&fence,VK_TRUE,1000000000),"wait fence");
    auto ns=std::chrono::duration_cast<std::chrono::nanoseconds>(std::chrono::steady_clock::now()-start).count();
    std::printf("submit_fence_ns\t%lld\n",static_cast<long long>(ns));
    need(!std::memcmp(input.p,src.data(),width*4),"mutated input");
    auto bytes=reinterpret_cast<unsigned char*>(dst.p);
    need(std::all_of(bytes+output_size,bytes+dst.bytes,[](unsigned char b){return b==0xa5;}),"output guard");
    FILE *f=std::fopen(args[4],"wbx"); need(f,"open new raw");
    need(std::fwrite(bytes,1,output_size,f)==output_size && !std::fclose(f),"write raw");
    providers();
    vkDestroyFence(dev,fence,nullptr);vkDestroyCommandPool(dev,pool,nullptr);vkDestroyDescriptorPool(dev,dpHandle,nullptr);
    vkDestroyPipeline(dev,pipeline,nullptr);vkDestroyPipelineLayout(dev,pl,nullptr);
    vkDestroyDescriptorSetLayout(dev,layout,nullptr);vkDestroyShaderModule(dev,mod,nullptr);
    for(auto v:{input,dst}) {vkDestroyBuffer(dev,v.b,nullptr);vkFreeMemory(dev,v.mem,nullptr);free(v.p);}
    vkDestroyDevice(dev,nullptr);vkDestroyInstance(in,nullptr);guard();
}
int main(int argc,char **argv) {
    setvbuf(stdout,nullptr,_IOLBF,0);
    try {need(argc==5,"input, two modules and new output");compute(argv);std::puts("PASS_RHS_DISPATCH");return 0;}
    catch(const Unsupported &e){std::printf("NOT_ADMITTED\t%s\n",e.what());return 3;}
    catch(const std::exception &e){std::fprintf(stderr,"FAIL\t%s\n",e.what());return 2;}
}
