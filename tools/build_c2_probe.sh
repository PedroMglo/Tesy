#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

case "${1:?usage: build_c2_probe.sh streaming|reference}" in
  streaming)
    backend=backends/streaming
    expected=1248fd8fa8cfebaece5ea992e4d951c1e18bb9d5
    output=tools/c2_logits_probe_streaming
    ;;
  reference)
    backend=backends/streaming-reference-c2
    expected=e5230b922aa4b4b410b2aaa38bd291fe9bd40bcd
    output=tools/c2_logits_probe_reference
    ;;
  *) exit 2 ;;
esac

actual="$(git -C "$backend" rev-parse HEAD)"
[[ "$actual" == "$expected" ]] || { echo "backend SHA mismatch: $actual" >&2; exit 1; }
libdir="$PWD/$backend/build-gcc15/bin"
[[ -f "$libdir/libllama.so" ]] || { echo "build $backend first" >&2; exit 1; }
g++-15 -std=c++17 -O2 -Wall -Wextra -Werror \
  -I "$backend/include" -I "$backend/ggml/include" \
  tools/c2_logits_probe.cpp -L "$libdir" -Wl,-rpath,"$libdir" \
  -lllama -o "$output"
sha256sum "$output"
