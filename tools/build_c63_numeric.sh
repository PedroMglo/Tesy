#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
backend=/tmp/tesy-c35-backend-20260928
expected=c3759bad92c0e6f71bb936afea9b0a162fb83f76
[[ "$(git -C "$backend" rev-parse HEAD)" == "$expected" ]]
[[ -z "$(git -C "$backend" status --porcelain)" ]]
libdir="$backend/build-c35-gcc15/bin"
for name in c63_profile_probe c63_boundary_capture; do
  g++-15 -std=c++17 -O2 -Wall -Wextra -Werror \
    -I "$backend/include" -I "$backend/src" -I "$backend/ggml/include" \
    "tools/$name.cpp" -L "$libdir" -Wl,-rpath,"$libdir" \
    -lllama -lggml -lggml-base -ldl -o "tools/$name"
done
g++-15 -std=c++17 -O2 -Wall -Wextra -Werror \
  -I "$backend/ggml/include" tools/c63_layer_reference.cpp \
  -L "$libdir" -Wl,-rpath,"$libdir" -lggml -lggml-cpu -lggml-base \
  -o tools/c63_layer_reference
sha256sum tools/c63_profile_probe tools/c63_boundary_capture tools/c63_layer_reference
