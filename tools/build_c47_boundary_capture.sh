#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
backend=/tmp/tesy-c47-backend-20260928
expected=6a2c6c1
[[ "$(git -C "$backend" rev-parse HEAD)" == "$expected"* ]]
[[ -z "$(git -C "$backend" status --porcelain)" ]]
libdir="$backend/build-c47-skip/bin"
g++-15 -std=c++17 -O2 -Wall -Wextra -Werror \
  -I "$backend/include" -I "$backend/src" -I "$backend/ggml/include" \
  tools/c47_boundary_capture.cpp -L "$libdir" -Wl,-rpath,"$libdir" \
  -lllama -lggml -lggml-base -ldl -o tools/c47_boundary_capture
sha256sum tools/c47_boundary_capture
