#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source_dir="${TESY_LLAMA_CPP_DIR:-$root/.deps/llama.cpp}"
build_dir="${TESY_CROSSOVER_BUILD_DIR:-$root/build/tesy-crossover}"

expected="$(
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

[[ -d "$source_dir/.git" ]] || { echo "missing llama.cpp checkout" >&2; exit 1; }
actual="$(git -C "$source_dir" rev-parse HEAD)"
[[ "$actual" == "$expected" ]] || {
  echo "llama.cpp pin mismatch: $actual != $expected" >&2
  exit 1
}
[[ -z "$(git -C "$source_dir" status --porcelain)" ]] || {
  echo "llama.cpp checkout must be clean" >&2
  exit 1
}

cc="${CC:-/usr/bin/gcc-15}"
cxx="${CXX:-/usr/bin/g++-15}"
cudacxx="${CUDACXX:-/usr/local/cuda/bin/nvcc}"
cuda_host="${CUDAHOSTCXX:-/usr/bin/g++-15}"
build_jobs="${TESY_BUILD_JOBS:-4}"

for tool in "$cc" "$cxx" "$cudacxx" "$cuda_host"; do
  [[ -x "$tool" ]] || { echo "missing compiler: $tool" >&2; exit 1; }
done
[[ "$build_jobs" =~ ^[1-9][0-9]*$ ]] || {
  echo "TESY_BUILD_JOBS must be a positive integer" >&2
  exit 2
}

cmake -S "$root/native" -B "$build_dir" \
  -DLLAMA_CPP_SOURCE_DIR="$source_dir" \
  -DGGML_CUDA=ON \
  -DCMAKE_CUDA_ARCHITECTURES=89 \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_C_COMPILER="$cc" \
  -DCMAKE_CXX_COMPILER="$cxx" \
  -DCMAKE_CUDA_COMPILER="$cudacxx" \
  -DCMAKE_CUDA_HOST_COMPILER="$cuda_host"

cmake --build "$build_dir" \
  --parallel "$build_jobs" \
  --target tesy-expert-crossover

"$build_dir/tesy-expert-crossover" --help
