#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 2 || $# -gt 3 ]]; then
  echo "usage: $0 MODEL.gguf OUTPUT_DIR [PROMPT]" >&2
  exit 2
fi

model_input="$1"
out="$2"
prompt="${3:-Explain why sparse Mixture-of-Experts models can be memory bound.}"
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
binary="${TESY_TRACE_BINARY:-$root/build/tesy-native/tesy-moe-trace}"
source_dir="${TESY_LLAMA_CPP_DIR:-$root/.deps/llama.cpp}"
trace_ngl="${TESY_TRACE_NGL:-0}"

if ! [[ "$trace_ngl" =~ ^[0-9]+$ ]]; then
  echo "TESY_TRACE_NGL must be a non-negative integer" >&2
  exit 2
fi

if [[ ! -x "$binary" ]]; then
  echo "missing tracer binary: $binary" >&2
  echo "run scripts/bootstrap_tesy_trace.sh first" >&2
  exit 1
fi
if [[ ! -d "$source_dir/.git" ]]; then
  echo "missing pinned llama.cpp source: $source_dir" >&2
  exit 1
fi
if [[ -e "$out" ]]; then
  echo "output directory already exists: $out" >&2
  exit 1
fi
mkdir -p "$out"

# Verify the originally supplied path before resolving it; otherwise a symlink
# could be hidden by realpath and bypass the model admission rule.
python3 -m tesy models verify \
  gpt-oss-20b-mxfp4-gguf "$model_input" >"$out/model.json"
model="$(python3 - "$model_input" <<'PY'
import sys
from pathlib import Path
print(Path(sys.argv[1]).resolve(strict=True))
PY
)"

python3 -m tesy doctor --disk-path "$(dirname "$model")" >"$out/doctor.json"
git -C "$root" rev-parse HEAD >"$out/tesy-head.txt"
git -C "$root" status --porcelain=v1 >"$out/tesy-status.txt"
git -C "$source_dir" rev-parse HEAD >"$out/llama-head.txt"
git -C "$source_dir" status --porcelain=v1 >"$out/llama-status.txt"
sha256sum "$binary" >"$out/tracer-sha256.txt"

if [[ -s "$out/tesy-status.txt" ]]; then
  echo "Tesy worktree is dirty; refusing diagnostic campaign" >&2
  exit 1
fi
if [[ -s "$out/llama-status.txt" ]]; then
  echo "llama.cpp worktree is dirty; refusing diagnostic campaign" >&2
  exit 1
fi

expected_llama="$(
  python3 - "$root/configs/backends.lock.json" <<'PY'
import json
import sys
from pathlib import Path
payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
for backend in payload["backends"]:
    if backend["id"] == "llama-cpp-stock":
        print(backend["commit"])
        break
else:
    raise SystemExit("llama-cpp-stock missing from backend lock")
PY
)"
observed_llama="$(cat "$out/llama-head.txt")"
if [[ "$observed_llama" != "$expected_llama" ]]; then
  echo "llama.cpp HEAD mismatch: $observed_llama != $expected_llama" >&2
  exit 1
fi

common=(
  --model "$model"
  --prompt "$prompt"
  --n-predict 16
  --ctx 4096
  --ngl "$trace_ngl"
  --raw-prompt
)

printf '%q ' "$binary" "${common[@]}" >"$out/command-common.txt"
printf '\n' >>"$out/command-common.txt"

"$binary" "${common[@]}" \
  --tokens-out "$out/tokens-off.json" \
  >"$out/stdout-off.txt" 2>"$out/stderr-off.txt"

"$binary" "${common[@]}" \
  --trace "$out/routing.jsonl" \
  --tokens-out "$out/tokens-on.json" \
  >"$out/stdout-on.txt" 2>"$out/stderr-on.txt"

if ! cmp -s "$out/tokens-off.json" "$out/tokens-on.json"; then
  echo "FAIL_TRACE_EXACTNESS: generated token IDs differ" >&2
  exit 1
fi

python3 -m tesy trace summarize-native "$out/routing.jsonl" \
  >"$out/trace-summary.json"
python3 -m tesy trace headroom-native "$out/routing.jsonl" \
  --slots 0,16,32,64,128,256 >"$out/headroom-count-space.json"

echo "PASS_DIAGNOSTIC_TRACE_TOKEN_EQUALITY"
echo "outputs: $out"
