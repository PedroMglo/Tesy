#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 2 ]]; then
  echo "usage: $0 MODEL.gguf OUTPUT_ROOT" >&2
  exit 2
fi

model="$1"
out="$2"
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source_dir="${TESY_LLAMA_CPP_DIR:-$root/.deps/llama.cpp}"
build_dir="${TESY_METADATA_BUILD_DIR:-$root/build/tesy-metadata}"
tool="$build_dir/tesy-gguf-inventory"
lock_file="${XDG_RUNTIME_DIR:-/tmp}/tesy-native-gguf-inventory.lock"

if [[ -e "$out" ]]; then
  echo "refusing to replace output root: $out" >&2
  exit 1
fi
mkdir -p "$out"

exec 9>"$lock_file"
if ! flock -n 9; then
  echo "another native GGUF inventory campaign holds $lock_file" >&2
  exit 1
fi

git -C "$root" rev-parse HEAD >"$out/tesy-head.txt"
git -C "$root" status --porcelain=v1 >"$out/tesy-status.txt"
git -C "$source_dir" rev-parse HEAD >"$out/llama-head.txt"
git -C "$source_dir" status --porcelain=v1 >"$out/llama-status.txt"

[[ ! -s "$out/tesy-status.txt" ]] || {
  echo "Tesy worktree must be clean" >&2
  exit 1
}
[[ ! -s "$out/llama-status.txt" ]] || {
  echo "llama.cpp worktree must be clean" >&2
  exit 1
}

python3 -m tesy models verify   gpt-oss-20b-mxfp4-gguf   "$model" >"$out/model.json"

bash "$root/scripts/bootstrap_native_gguf_inventory.sh"   >"$out/bootstrap.stdout.txt"   2>"$out/bootstrap.stderr.txt"

[[ -x "$tool" ]] || {
  echo "missing native inventory tool after bootstrap: $tool" >&2
  exit 1
}

sha256sum "$tool" >"$out/tool-sha256.txt"
ldd "$tool" >"$out/tool-ldd.txt"

"$tool" "$model" >"$out/raw-tensors.jsonl"

python3 -m tesy.native_gguf_inventory   --input "$out/raw-tensors.jsonl"   --output "$out/expert-inventory.json"

python3 - "$out/expert-inventory.json" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
if payload.get("schema") != "tesy.gguf_expert_inventory.v1":
    raise SystemExit("unexpected expert inventory schema")
if payload.get("status") != "PASS_DERIVATION":
    raise SystemExit(f"expert inventory did not pass: {payload.get('status')}")
layers = payload.get("layers")
if not isinstance(layers, list) or not layers:
    raise SystemExit("expert inventory contains no admitted layers")

expert_counts = sorted({row["expert_count"] for row in layers})
bytes_per_expert = sorted({
    row["encoded_payload_bytes_per_expert"] for row in layers
})
tensor_types = sorted({
    tensor["tensor_type"]
    for row in layers
    for tensor in row["tensors"]
})
shapes = sorted({
    tuple(tensor["shape"])
    for row in layers
    for tensor in row["tensors"]
})

print("PASS_NATIVE_GGUF_EXPERT_INVENTORY")
print("layers:", len(layers))
print("expert_counts:", expert_counts)
print("encoded_payload_bytes_per_expert:", bytes_per_expert)
print("tensor_types:", tensor_types)
print("tensor_shapes:", [list(shape) for shape in shapes])
PY

echo "outputs: $out"
