#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
deps="${TESY_DEPS_DIR:-$root/.deps}"
binary="${TESY_NATIVE_BUILD_DIR:-$deps/tesy-native-build}/tesy-llama-trace"

model="${1:-}"
output="${2:-}"
prompt="${3:-Explain briefly why a sparse mixture-of-experts model can have many total parameters but fewer active parameters per token.}"

[[ -x "$binary" ]] || {
  echo "missing tracer; run scripts/build_trace_tool.sh" >&2
  exit 2
}
[[ -f "$model" ]] || {
  echo "usage: $0 MODEL.gguf TRACE.jsonl [raw-prompt]" >&2
  exit 2
}
[[ -n "$output" ]] || {
  echo "usage: $0 MODEL.gguf TRACE.jsonl [raw-prompt]" >&2
  exit 2
}
[[ ! -e "$output" ]] || {
  echo "refusing to replace existing output: $output" >&2
  exit 2
}

exec "$binary"   -m "$model"   -o "$output"   -n 16   -ngl 99   --cpu-moe   "$prompt"
