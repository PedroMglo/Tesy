#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
backend="${1:?usage: build.sh stock|streaming}"
case "$backend" in stock|streaming) ;; *) exit 2 ;; esac
cmake -S "backends/$backend" -B "backends/$backend/build-gcc15" -G Ninja \
  -DGGML_CUDA=ON \
  -DCMAKE_C_COMPILER=/usr/bin/gcc-15 \
  -DCMAKE_CXX_COMPILER=/usr/bin/g++-15 \
  -DCMAKE_CUDA_COMPILER=/usr/local/cuda/bin/nvcc \
  -DCMAKE_CUDA_HOST_COMPILER=/usr/bin/g++-15 \
  -DCMAKE_CUDA_ARCHITECTURES=89 \
  -DLLAMA_BUILD_TESTS=OFF -DLLAMA_BUILD_SERVER=ON -DCMAKE_BUILD_TYPE=Release
cmake --build "backends/$backend/build-gcc15" --target llama-cli llama-server -j 4
