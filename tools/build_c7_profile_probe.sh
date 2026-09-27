#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
backend=/home/pmglo/Projects/Tesy/tesy-scale-lab/backends/streaming
expected=1248fd8fa8cfebaece5ea992e4d951c1e18bb9d5
[[ "$(git -C "$backend" rev-parse HEAD)" == "$expected" ]]
[[ -z "$(git -C "$backend" status --porcelain)" ]]
libdir="$backend/build-gcc15/bin"
g++-15 -std=c++17 -O2 -Wall -Wextra -Werror \
  -I "$backend/include" -I "$backend/ggml/include" \
  tools/c7_profile_probe.cpp -L "$libdir" -Wl,-rpath,"$libdir" \
  -lllama -lggml -lggml-base -ldl -o tools/c7_profile_probe
sha256sum tools/c7_profile_probe
