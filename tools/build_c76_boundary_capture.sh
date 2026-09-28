#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
backend=/tmp/tesy-c75-backend-20260928
expected=27d2e42d8c994507ee6d71acc7c58d3eddd3f7a5
[[ "$(git -C "$backend" rev-parse HEAD)" == "$expected" ]]
[[ -z "$(git -C "$backend" status --porcelain)" ]]
libdir="$backend/build-c75-cuda/bin"
g++-15 -std=c++17 -O2 -Wall -Wextra -Werror \
  -I "$backend/include" -I "$backend/src" -I "$backend/ggml/include" \
  tools/c70_boundary_capture.cpp \
  "$libdir/libllama.so" "$libdir/libggml.so" "$libdir/libggml-base.so" \
  -Wl,-rpath,"$libdir" -ldl -o /tmp/c76_boundary_capture
sha256sum /tmp/c76_boundary_capture
