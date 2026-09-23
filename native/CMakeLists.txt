cmake_minimum_required(VERSION 3.20)
project(tesy_native LANGUAGES C CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

if(NOT DEFINED LLAMA_CPP_DIR)
  message(FATAL_ERROR "Pass -DLLAMA_CPP_DIR=/path/to/pinned/llama.cpp")
endif()

option(TESY_NATIVE_CUDA "Build the embedded llama.cpp dependency with CUDA" OFF)

set(GGML_CUDA ${TESY_NATIVE_CUDA} CACHE BOOL "" FORCE)
set(LLAMA_CURL OFF CACHE BOOL "" FORCE)
set(LLAMA_BUILD_TESTS OFF CACHE BOOL "" FORCE)
set(LLAMA_BUILD_EXAMPLES OFF CACHE BOOL "" FORCE)
set(LLAMA_BUILD_TOOLS OFF CACHE BOOL "" FORCE)

add_subdirectory("${LLAMA_CPP_DIR}" llama_cpp EXCLUDE_FROM_ALL)

add_executable(tesy-llama-trace tesy_llama_trace.cpp)
target_link_libraries(tesy-llama-trace PRIVATE llama)
target_include_directories(tesy-llama-trace PRIVATE
  "${LLAMA_CPP_DIR}/ggml/include"
)
