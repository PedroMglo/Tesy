#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
backend=/tmp/tesy-c48-backend-20260928
expected=0bc5c75
[[ "$(git -C "$backend" rev-parse HEAD)" == "$expected"* ]]
[[ -z "$(git -C "$backend" status --porcelain)" ]]
libdir="$backend/build-c48-host/bin"
g++-15 -std=c++17 -O2 -Wall -Wextra -Werror \
  -I "$backend/ggml/include" tools/c48_layer_reference.cpp \
  -L "$libdir" -Wl,-rpath,"$libdir" -lggml -lggml-cpu -lggml-base \
  -o tools/c48_layer_reference
sha256sum tools/c48_layer_reference
