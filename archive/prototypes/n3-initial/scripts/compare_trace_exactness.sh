#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 2 || $# -gt 3 ]]; then
  echo "usage: $0 MODEL.gguf OUTPUT_DIR [PROMPT]" >&2
  exit 2
fi

model="$(realpath "$1")"
out="$2"
prompt="${3:-Explain why sparse Mixture-of-Experts models can be memory bound.}"
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
binary="${TESY_TRACE_BINARY:-$root/build/tesy-native/tesy-moe-trace}"

if [[ ! -x "$binary" ]]; then
  echo "missing tracer binary: $binary" >&2
  echo "run scripts/bootstrap_tesy_trace.sh first" >&2
  exit 1
fi
if [[ -e "$out" ]]; then
  echo "output directory already exists: $out" >&2
  exit 1
fi
mkdir -p "$out"

common=(
  --model "$model"
  --prompt "$prompt"
  --n-predict 16
  --ctx 4096
  --ngl 99
  --cpu-moe
)

"$binary" "${common[@]}"   --tokens-out "$out/tokens-off.json"   >"$out/stdout-off.txt" 2>"$out/stderr-off.txt"

"$binary" "${common[@]}"   --trace "$out/routing.jsonl"   --tokens-out "$out/tokens-on.json"   >"$out/stdout-on.txt" 2>"$out/stderr-on.txt"

if ! cmp -s "$out/tokens-off.json" "$out/tokens-on.json"; then
  echo "FAIL_TRACE_EXACTNESS: generated token IDs differ" >&2
  exit 1
fi

python3 -m tesy trace summarize-native "$out/routing.jsonl"   >"$out/trace-summary.json"

echo "PASS_DIAGNOSTIC_TRACE_TOKEN_EQUALITY"
echo "outputs: $out"
