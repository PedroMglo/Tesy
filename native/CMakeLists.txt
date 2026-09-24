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
    "${LLAMA_CPP_SOURCE_DIR}/include"
    "${LLAMA_CPP_SOURCE_DIR}/ggml/include"
)
target_link_libraries(tesy-expert-crossover PRIVATE llama ggml)
