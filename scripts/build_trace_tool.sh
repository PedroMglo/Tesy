#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
deps="${TESY_DEPS_DIR:-$root/.deps}"
src="$deps/llama.cpp"
build="${TESY_NATIVE_BUILD_DIR:-$deps/tesy-native-build}"
cuda="${TESY_NATIVE_CUDA:-OFF}"

pin="$(
  python3 - "$root/configs/backends.lock.json" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
print(next(item["commit"] for item in payload["backends"] if item["id"] == "llama-cpp-stock"))
PY
)"

[[ -d "$src/.git" ]] || {
  echo "missing pinned llama.cpp; run scripts/bootstrap_llama_cpp.sh" >&2
  exit 2
}
[[ "$(git -C "$src" rev-parse HEAD)" == "$pin" ]] || {
  echo "llama.cpp HEAD does not match lock" >&2
  exit 2
}
[[ -z "$(git -C "$src" status --porcelain)" ]] || {
  echo "llama.cpp checkout is dirty" >&2
  exit 2
}

cmake -S "$root/native" -B "$build"   -DCMAKE_BUILD_TYPE=Release   -DLLAMA_CPP_DIR="$src"   -DTESY_NATIVE_CUDA="$cuda"
cmake --build "$build" --parallel "$(nproc)" --target tesy-llama-trace

echo "trace tool: $build/tesy-llama-trace"
