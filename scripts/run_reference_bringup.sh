#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 2 || $# -gt 3 ]]; then
  echo "usage: $0 MODEL.gguf OUTPUT_ROOT [PROMPT]" >&2
  exit 2
fi

model_input="$1"
out="$2"
prompt="${3:-Explain why sparse Mixture-of-Experts models can reduce active compute.}"
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source_dir="${TESY_LLAMA_CPP_DIR:-$root/.deps/llama.cpp}"

if [[ -e "$out" ]]; then
  echo "refusing to replace existing output root: $out" >&2
  exit 1
fi
mkdir -p "$out"

git -C "$root" rev-parse HEAD >"$out/tesy-head.txt"
git -C "$root" status --porcelain=v1 >"$out/tesy-status.txt"
if [[ -s "$out/tesy-status.txt" ]]; then
  echo "Tesy worktree is dirty; refusing bring-up campaign" >&2
  exit 1
fi

python3 -m tesy doctor \
  --disk-path "$(dirname "$model_input")" \
  --reference-profile "$root/configs/reference-host.json" \
  >"$out/doctor-reference.json"

python3 -m tesy models verify \
  gpt-oss-20b-mxfp4-gguf "$model_input" \
  >"$out/model-preflight.json"

python3 -m tesy plan \
  --model gpt-oss-20b-mxfp4-gguf \
  --path "$model_input" \
  >"$out/capacity-preflight.json"

bash "$root/scripts/bootstrap_llama_cpp.sh" \
  >"$out/bootstrap-llama.stdout.txt" \
  2>"$out/bootstrap-llama.stderr.txt"

bash "$root/scripts/bootstrap_tesy_trace.sh" \
  >"$out/bootstrap-trace.stdout.txt" \
  2>"$out/bootstrap-trace.stderr.txt"

bash "$root/scripts/bootstrap_gguf_tools.sh" \
  >"$out/bootstrap-gguf.stdout.txt" \
  2>"$out/bootstrap-gguf.stderr.txt"

bash "$root/scripts/run_stock_smoke.sh" \
  "$model_input" "$out/stock-smoke" "$prompt"

bash "$root/scripts/compare_trace_exactness.sh" \
  "$model_input" "$out/trace-exactness" "$prompt"

python3 -m tesy models inventory-experts \
  gpt-oss-20b-mxfp4-gguf "$model_input" \
  --llama-source "$source_dir" \
  >"$out/expert-inventory.json"

echo "PASS_DIAGNOSTIC_REFERENCE_BRINGUP_PIPELINE"
echo "No performance/Tesy-optimization claim is implied."
echo "outputs: $out"
