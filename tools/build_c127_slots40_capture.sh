#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
backend=/tmp/tesy-c75-backend-20260928
expected=27d2e42d8c994507ee6d71acc7c58d3eddd3f7a5
[[ "$(git -C "$backend" rev-parse HEAD)" == "$expected" ]]
[[ -z "$(git -C "$backend" status --porcelain)" ]]
libdir="$backend/build-c75-cuda/bin"
outdir=results/c127-slots40-numeric-20260929T1654Z/build
mkdir -p "$outdir"
g++-15 -std=c++17 -O2 -Wall -Wextra -Werror \
  -I "$backend/include" -I "$backend/src" -I "$backend/ggml/include" \
  tools/c127_slots40_boundary_capture.cpp \
  "$libdir/libllama.so" "$libdir/libggml.so" "$libdir/libggml-base.so" \
  -Wl,-rpath,"$libdir" -ldl -o "$outdir/c127_slots40_boundary_capture"
sha256sum "$outdir/c127_slots40_boundary_capture"
