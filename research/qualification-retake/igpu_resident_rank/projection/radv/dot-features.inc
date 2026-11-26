    const bool has_dot=std::any_of(ex.begin(),ex.end(),[](auto &e){
        return !strcmp(e.extensionName,"VK_KHR_shader_integer_dot_product");
    });
    supported(has_dot,"integer dot extension");
    VkPhysicalDeviceShaderIntegerDotProductPropertiesKHR dotp{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_SHADER_INTEGER_DOT_PRODUCT_PROPERTIES_KHR};
    VkPhysicalDeviceSubgroupSizeControlPropertiesEXT sizep{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_SUBGROUP_SIZE_CONTROL_PROPERTIES_EXT,&dotp};
    VkPhysicalDeviceProperties2 dd{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_PROPERTIES_2,&sizep};
    vkGetPhysicalDeviceProperties2(gpu,&dd);
    VkPhysicalDeviceShaderIntegerDotProductFeaturesKHR dotf{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_SHADER_INTEGER_DOT_PRODUCT_FEATURES_KHR};
    VkPhysicalDeviceFeatures2 dotq{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_FEATURES_2,&dotf};
    vkGetPhysicalDeviceFeatures2(gpu,&dotq);
    supported(dotp.integerDotProduct4x8BitPackedSignedAccelerated && dotf.shaderIntegerDotProduct &&
          size.subgroupSizeControl && (sizep.requiredSubgroupSizeStages & VK_SHADER_STAGE_COMPUTE_BIT) &&
          sizep.minSubgroupSize<=group && group<=sizep.maxSubgroupSize && size.computeFullSubgroups && clustered &&
          (sg.supportedOperations&VK_SUBGROUP_FEATURE_ARITHMETIC_BIT) && f12.storageBuffer8BitAccess,
          "C269 packed signed dot, 8-bit storage or required subgroup");
    std::printf("mmvq_admitted\t%u\t%u\t%u\t%u\n",dotf.shaderIntegerDotProduct,
                dotp.integerDotProduct4x8BitPackedSignedAccelerated,sizep.minSubgroupSize,sizep.maxSubgroupSize);
