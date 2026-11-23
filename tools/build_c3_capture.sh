#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

backend=backends/streaming
expected=1248fd8fa8cfebaece5ea992e4d951c1e18bb9d5
actual="$(git -C "$backend" rev-parse HEAD)"
[[ "$actual" == "$expected" ]] || { echo "backend SHA mismatch: $actual" >&2; exit 1; }
libdir="$PWD/$backend/build-gcc15/bin"
[[ -f "$libdir/libllama.so" && -f "$libdir/libggml.so" ]] || {
  echo "pinned backend build missing" >&2; exit 1;
}
g++-15 -std=c++17 -O2 -Wall -Wextra -Werror \
  -I "$backend/include" -I "$backend/src" -I "$backend/ggml/include" \
  tools/c3_boundary_capture.cpp -L "$libdir" -Wl,-rpath,"$libdir" \
  -lllama -lggml -lggml-base -ldl -o tools/c3_boundary_capture
sha256sum tools/c3_boundary_capture
