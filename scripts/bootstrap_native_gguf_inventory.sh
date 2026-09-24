#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source_dir="${TESY_LLAMA_CPP_DIR:-$root/.deps/llama.cpp}"
build_dir="${TESY_METADATA_BUILD_DIR:-$root/build/tesy-metadata}"

pin="$(
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

[[ -d "$source_dir/.git" ]] || {
  echo "missing pinned llama.cpp checkout: $source_dir" >&2
  exit 1
}
actual="$(git -C "$source_dir" rev-parse HEAD)"
[[ "$actual" == "$pin" ]] || {
  echo "expected llama.cpp $pin, found $actual" >&2
  exit 1
}
[[ -z "$(git -C "$source_dir" status --porcelain)" ]] || {
  echo "llama.cpp checkout must be clean" >&2
  exit 1
}

build_jobs="${TESY_BUILD_JOBS:-4}"
[[ "$build_jobs" =~ ^[1-9][0-9]*$ ]] || {
  echo "TESY_BUILD_JOBS must be a positive integer" >&2
  exit 2
}

cmake -S "$root/native" -B "$build_dir"   -DLLAMA_CPP_SOURCE_DIR="$source_dir"   -DGGML_CUDA=OFF   -DCMAKE_BUILD_TYPE=Release

cmake --build "$build_dir"   --parallel "$build_jobs"   --target tesy-gguf-inventory

"$build_dir/tesy-gguf-inventory" --help
