#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source_dir="${TESY_LLAMA_CPP_DIR:-$root/.deps/llama.cpp}"
build_dir="${TESY_NATIVE_BUILD_DIR:-$root/build/tesy-native}"

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

if [[ ! -d "$source_dir/.git" ]]; then
  echo "missing pinned llama.cpp checkout: $source_dir" >&2
  echo "run scripts/bootstrap_llama_cpp.sh first" >&2
  exit 1
fi

actual="$(git -C "$source_dir" rev-parse HEAD)"
if [[ "$actual" != "$pin" ]]; then
  echo "expected llama.cpp $pin, found $actual" >&2
  exit 1
fi
if [[ -n "$(git -C "$source_dir" status --porcelain)" ]]; then
  echo "llama.cpp checkout must be clean" >&2
  exit 1
fi

cuda_arch="${TESY_CUDA_ARCH:-89}"

cmake -S "$root/native" -B "$build_dir"   -DLLAMA_CPP_SOURCE_DIR="$source_dir"   -DGGML_CUDA=ON   -DCMAKE_CUDA_ARCHITECTURES="$cuda_arch"   -DCMAKE_BUILD_TYPE=Release

cmake --build "$build_dir" --parallel "$(nproc)" --target tesy-moe-trace

"$build_dir/tesy-moe-trace" --help
