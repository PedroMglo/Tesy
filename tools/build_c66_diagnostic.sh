#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
backend=/tmp/tesy-c66-wave-id-backend-20260928
expected=1c6f503bbb2ee0ee315540a17cbfb6b2bab68f22
[[ "$(git -C "$backend" rev-parse HEAD)" == "$expected" ]]
[[ -z "$(git -C "$backend" status --porcelain)" ]]
libdir="$backend/build-c66-cuda/bin"
for item in c66_plain_probe:c7_profile_probe c66_boundary_capture:c60_boundary_capture; do
  out=${item%%:*}
  source=${item#*:}
  g++-15 -std=c++17 -O2 -Wall -Wextra -Werror \
    -I "$backend/include" -I "$backend/src" -I "$backend/ggml/include" \
    "tools/$source.cpp" -L "$libdir" -Wl,-rpath,"$libdir" \
    -lllama -lggml -lggml-base -ldl -o "tools/$out"
done
sha256sum tools/c66_plain_probe tools/c66_boundary_capture
