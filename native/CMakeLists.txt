cmake_minimum_required(VERSION 3.20)
project(tesy_native LANGUAGES C CXX)

if(NOT DEFINED LLAMA_CPP_SOURCE_DIR)
  message(FATAL_ERROR "LLAMA_CPP_SOURCE_DIR must point to the pinned llama.cpp checkout")
endif()

get_filename_component(LLAMA_CPP_SOURCE_DIR "${LLAMA_CPP_SOURCE_DIR}" REALPATH)
if(NOT EXISTS "${LLAMA_CPP_SOURCE_DIR}/CMakeLists.txt")
  message(FATAL_ERROR "invalid LLAMA_CPP_SOURCE_DIR: ${LLAMA_CPP_SOURCE_DIR}")
endif()

set(LLAMA_BUILD_TESTS OFF CACHE BOOL "" FORCE)
set(LLAMA_BUILD_EXAMPLES OFF CACHE BOOL "" FORCE)
set(LLAMA_BUILD_TOOLS OFF CACHE BOOL "" FORCE)
set(LLAMA_BUILD_SERVER OFF CACHE BOOL "" FORCE)
set(LLAMA_CURL OFF CACHE BOOL "" FORCE)

add_subdirectory("${LLAMA_CPP_SOURCE_DIR}" "${CMAKE_BINARY_DIR}/llama.cpp" EXCLUDE_FROM_ALL)

add_executable(tesy-moe-trace tesy_moe_trace.cpp)
target_compile_features(tesy-moe-trace PRIVATE cxx_std_17)
target_compile_options(tesy-moe-trace PRIVATE -Wall -Wextra -Wpedantic -Werror)
target_include_directories(
  tesy-moe-trace
  PRIVATE
    "${LLAMA_CPP_SOURCE_DIR}/include"
    "${LLAMA_CPP_SOURCE_DIR}/ggml/include"
)
target_link_libraries(tesy-moe-trace PRIVATE llama ggml)


add_executable(tesy-gguf-inventory tesy_gguf_inventory.cpp)
target_compile_features(tesy-gguf-inventory PRIVATE cxx_std_17)
target_compile_options(tesy-gguf-inventory PRIVATE -Wall -Wextra -Wpedantic -Werror)
target_include_directories(
  tesy-gguf-inventory
  PRIVATE
    "${LLAMA_CPP_SOURCE_DIR}/ggml/include"
)
target_link_libraries(tesy-gguf-inventory PRIVATE ggml)


add_executable(tesy-expert-crossover tesy_expert_crossover.cpp)
target_compile_features(tesy-expert-crossover PRIVATE cxx_std_17)
target_compile_options(tesy-expert-crossover PRIVATE -Wall -Wextra -Wpedantic -Werror)
target_include_directories(
  tesy-expert-crossover
  PRIVATE
    "${LLAMA_CPP_SOURCE_DIR}/ggml/include"
)
target_link_libraries(tesy-expert-crossover PRIVATE ggml)


add_executable(tesy-mixed-residency tesy_mixed_residency.cpp)
target_compile_features(tesy-mixed-residency PRIVATE cxx_std_17)
target_compile_options(tesy-mixed-residency PRIVATE -Wall -Wextra -Wpedantic -Werror)
target_include_directories(
  tesy-mixed-residency
  PRIVATE
    "${LLAMA_CPP_SOURCE_DIR}/include"
    "${LLAMA_CPP_SOURCE_DIR}/ggml/include"
)
target_link_libraries(tesy-mixed-residency PRIVATE llama ggml)


add_executable(tesy-routed-layer-capture tesy_routed_layer_capture.cpp)
target_compile_features(tesy-routed-layer-capture PRIVATE cxx_std_17)
target_compile_options(tesy-routed-layer-capture PRIVATE -Wall -Wextra -Wpedantic -Werror)
target_include_directories(
  tesy-routed-layer-capture
  PRIVATE
    "${LLAMA_CPP_SOURCE_DIR}/include"
    "${LLAMA_CPP_SOURCE_DIR}/ggml/include"
)
target_link_libraries(tesy-routed-layer-capture PRIVATE llama ggml)

add_executable(tesy-split-graph-model-free tesy_split_graph_model_free.cpp)
target_compile_features(tesy-split-graph-model-free PRIVATE cxx_std_17)
target_compile_options(tesy-split-graph-model-free PRIVATE -Wall -Wextra -Wpedantic -Werror)
target_include_directories(
  tesy-split-graph-model-free
  PRIVATE
    "${LLAMA_CPP_SOURCE_DIR}/ggml/include"
)
target_include_directories(
  tesy-split-graph-model-free
  SYSTEM PRIVATE
    "${LLAMA_CPP_SOURCE_DIR}/ggml/src"
)
target_link_libraries(tesy-split-graph-model-free PRIVATE ggml ggml-cpu)
