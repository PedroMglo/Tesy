#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
backend=/tmp/tesy-c66-wave-id-backend-20260928
expected=1c6f503bbb2ee0ee315540a17cbfb6b2bab68f22
[[ "$(git -C "$backend" rev-parse HEAD)" == "$expected" ]]
[[ -z "$(git -C "$backend" status --porcelain)" ]]
libdir="$backend/build-c66-cuda/bin"
g++-15 -std=c++17 -O2 -Wall -Wextra -Werror \
  -I "$backend/include" -I "$backend/src" -I "$backend/ggml/include" \
  tools/c73_wave_probe.cpp -L "$libdir" -Wl,-rpath,"$libdir" \
  -lllama -lggml -lggml-base -ldl -o tools/c73_wave_probe
sha256sum tools/c73_wave_probe
