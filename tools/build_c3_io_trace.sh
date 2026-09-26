#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
backend=backends/streaming
[[ "$(git -C "$backend" rev-parse HEAD)" == 1248fd8fa8cfebaece5ea992e4d951c1e18bb9d5 ]]
gcc-15 -std=gnu11 -shared -fPIC -O2 -Wall -Wextra -Werror \
  -I "$backend/ggml/include" tools/c3_io_trace.c -ldl -o tools/libc3_io_trace.so
sha256sum tools/libc3_io_trace.so
