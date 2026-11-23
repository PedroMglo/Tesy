#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
backend=/tmp/tesy-c48-backend-20260928
expected=0bc5c75
[[ "$(git -C "$backend" rev-parse HEAD)" == "$expected"* ]]
[[ -z "$(git -C "$backend" status --porcelain)" ]]
libdir="$backend/build-c48-host/bin"
g++-15 -std=c++17 -O2 -Wall -Wextra -Werror \
  -I "$backend/include" -I "$backend/src" -I "$backend/ggml/include" \
  tools/c48_boundary_capture.cpp -L "$libdir" -Wl,-rpath,"$libdir" \
  -lllama -lggml -lggml-base -ldl -o tools/c48_boundary_capture
sha256sum tools/c48_boundary_capture
