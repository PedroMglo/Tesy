#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 2 || $# -gt 3 ]]; then
  echo "usage: $0 MODEL.gguf OUTPUT_DIR [PROMPT]" >&2
  exit 2
fi

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
model_input="$1"
out="$2"
prompt="${3:-Explain in two paragraphs why sparse Mixture-of-Experts models can reduce active compute.}"
source_dir="${TESY_LLAMA_CPP_DIR:-$root/.deps/llama.cpp}"
binary="${TESY_LLAMA_CLI:-$source_dir/build/bin/llama-cli}"

if [[ -e "$out" ]]; then
  echo "refusing to replace existing output directory: $out" >&2
  exit 1
fi
mkdir -p "$out"

if [[ ! -x "$binary" ]]; then
  echo "missing stock llama-cli: $binary" >&2
  echo "run scripts/bootstrap_llama_cpp.sh first" >&2
  exit 1
fi

python3 -m tesy models verify \
  gpt-oss-20b-mxfp4-gguf "$model_input" >"$out/model.json"
model="$(python3 - "$model_input" <<'PY'
import sys
from pathlib import Path
print(Path(sys.argv[1]).resolve(strict=True))
PY
)"

python3 -m tesy doctor --disk-path "$(dirname "$model")" >"$out/doctor.json"
python3 -m tesy backend probe \
  --binary "$binary" \
  --source-dir "$source_dir" >"$out/backend.json"
python3 -m tesy plan \
  --model gpt-oss-20b-mxfp4-gguf \
  --path "$model" >"$out/capacity.json"

if command -v nvidia-smi >/dev/null 2>&1; then
  nvidia-smi -q >"$out/nvidia-before.txt" || true
fi
cat /proc/meminfo >"$out/meminfo-before.txt"

cmd=(
  "$binary"
  --model "$model"
  --ctx-size 4096
  --n-predict 16
  --gpu-layers auto
  --fit on
  --fit-target 1024
  --temperature 0
  --top-k 1
  --seed 42
  --no-warmup
  --simple-io
  --no-display-prompt
  --single-turn
  --prompt "$prompt"
)

printf '%q ' "${cmd[@]}" >"$out/command.txt"
printf '\n' >>"$out/command.txt"

set +e
/usr/bin/time -v "${cmd[@]}"   >"$out/stdout.txt"   2>"$out/stderr-and-time.txt"
rc=$?
set -e

printf '%s\n' "$rc" >"$out/return-code.txt"
cat /proc/meminfo >"$out/meminfo-after.txt"
if command -v nvidia-smi >/dev/null 2>&1; then
  nvidia-smi -q >"$out/nvidia-after.txt" || true
fi

if [[ "$rc" -ne 0 ]]; then
  echo "FAIL_STOCK_SMOKE: llama-cli returned $rc" >&2
  exit "$rc"
fi

echo "PASS_DIAGNOSTIC_STOCK_SMOKE"
echo "outputs: $out"
