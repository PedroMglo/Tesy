#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source_dir="${TESY_LLAMA_CPP_DIR:-$root/.deps/llama.cpp}"
build_dir="${TESY_MIXED_BUILD_DIR:-$root/build/tesy-mixed-residency}"

[[ -z "$(git -C "$root" status --porcelain)" ]] || {
  echo "Tesy checkout must be clean before native campaign build" >&2
  exit 1
}
tesy_head="$(git -C "$root" rev-parse HEAD)"

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

[[ -d "$source_dir/.git" ]] || {
  echo "missing llama.cpp checkout: $source_dir" >&2
  exit 1
}
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
  [[ -x "$tool" ]] || {
    echo "missing compiler: $tool" >&2
    exit 1
  }
done
[[ "$build_jobs" =~ ^[1-9][0-9]*$ ]] || {
  echo "TESY_BUILD_JOBS must be a positive integer" >&2
  exit 2
}

cmake -S "$root/native" -B "$build_dir" \
  -DLLAMA_CPP_SOURCE_DIR="$source_dir" \
  -DGGML_CUDA=ON \
  -DGGML_BACKEND_DL=OFF \
  -DCMAKE_CUDA_ARCHITECTURES=89 \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_C_COMPILER="$cc" \
  -DCMAKE_CXX_COMPILER="$cxx" \
  -DCMAKE_CUDA_COMPILER="$cudacxx" \
  -DCMAKE_CUDA_HOST_COMPILER="$cuda_host"

cmake --build "$build_dir" \
  --parallel "$build_jobs" \
  --target tesy-mixed-residency

tool="$build_dir/tesy-mixed-residency"
"$tool" --help

python3 - \
  "$build_dir/tesy-mixed-residency-build-provenance.json" \
  "$tesy_head" \
  "$actual" \
  "$root/native/tesy_mixed_residency.cpp" \
  "$root/native/CMakeLists.txt" \
  "$tool" <<'PY'
import hashlib
import json
import os
import sys
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


output = Path(sys.argv[1])
payload = {
    "schema": "tesy.mixed_residency_native_build.v1",
    "classification": "MEASURED_LOCAL_BUILD_PROVENANCE",
    "tesy_head": sys.argv[2],
    "llama_head": sys.argv[3],
    "native_source_sha256": sha256(Path(sys.argv[4])),
    "cmake_lists_sha256": sha256(Path(sys.argv[5])),
    "tool_sha256": sha256(Path(sys.argv[6])),
    "tool_path": str(Path(sys.argv[6]).resolve()),
    "status": "PASS",
}
tmp = output.with_name(output.name + ".tmp")
with tmp.open("w", encoding="utf-8") as handle:
    json.dump(payload, handle, indent=2, sort_keys=True)
    handle.write("\n")
os.replace(tmp, output)
PY
