#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
backend=/tmp/tesy-c84-backend-20260928
bin="$backend/build-c84-cuda/bin"
out=/tmp/c84_trace_smoke_verified
test ! -e "$out"
g++-15 -std=c++17 -O2 -Wall -Wextra -Werror -DTESY_C84_EXPERT_TRACE \
  -I "$backend/src" -I "$backend/ggml/include" -I "$backend/ggml/src" \
  tools/c84_trace_smoke.cpp -L "$bin" -Wl,-rpath,"$bin" \
  -lllama -lggml-cpu -lggml-base -lggml -o "$out"
sha256sum "$out"
callback=/tmp/c84_stream_callback_smoke_verified
test ! -e "$callback"
g++-15 -std=c++17 -O2 -Wall -Wextra -Werror -DTESY_C84_EXPERT_TRACE \
  -I "$backend/src" -I "$backend/ggml/include" -I "$backend/ggml/src" \
  tools/c84_stream_callback_smoke.cpp -L "$bin" -Wl,-rpath,"$bin" \
  -lllama -lggml-cpu -lggml-base -lggml -o "$callback"
sha256sum "$callback"
control_backend=/tmp/tesy-c75-backend-20260928
control_bin="$control_backend/build-c75-cuda/bin"
control=/tmp/c75_stream_callback_control
test ! -e "$control"
g++-15 -std=c++17 -O2 -Wall -Wextra -Werror \
  -I "$control_backend/src" -I "$control_backend/ggml/include" -I "$control_backend/ggml/src" \
  tools/c84_stream_callback_smoke.cpp -L "$control_bin" -Wl,-rpath,"$control_bin" \
  -lllama -lggml-cpu -lggml-base -lggml -o "$control"
sha256sum "$control"
