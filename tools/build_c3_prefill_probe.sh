#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
backend=backends/streaming
[[ "$(git -C "$backend" rev-parse HEAD)" == 1248fd8fa8cfebaece5ea992e4d951c1e18bb9d5 ]]
libdir="$PWD/$backend/build-gcc15/bin"
g++-15 -std=c++17 -O2 -Wall -Wextra -Werror \
  -I "$backend/include" -I "$backend/ggml/include" \
  tools/c3_prefill_probe.cpp -L "$libdir" -Wl,-rpath,"$libdir" \
  -lllama -lggml -lggml-base -ldl -o tools/c3_prefill_probe
sha256sum tools/c3_prefill_probe
