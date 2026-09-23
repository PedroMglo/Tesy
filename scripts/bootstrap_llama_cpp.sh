#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
lock="$root/configs/backends.lock.json"
deps="${TESY_DEPS_DIR:-$root/.deps}"
repo="$deps/llama.cpp"

pin="$(
  python3 - "$lock" <<'PY'
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

mkdir -p "$deps"

if [[ ! -d "$repo/.git" ]]; then
  git clone https://github.com/ggml-org/llama.cpp.git "$repo"
fi

if [[ -n "$(git -C "$repo" status --porcelain)" ]]; then
  echo "refusing to modify dirty llama.cpp checkout: $repo" >&2
  exit 1
fi

git -C "$repo" fetch --tags origin
git -C "$repo" checkout --detach "$pin"

cuda_arch="${TESY_CUDA_ARCH:-89}"
echo "Building pinned llama.cpp $pin for CUDA architecture $cuda_arch"
echo "Override TESY_CUDA_ARCH only after verifying the physical GPU."

cmake -S "$repo" -B "$repo/build"   -DCMAKE_BUILD_TYPE=Release   -DGGML_CUDA=ON   -DCMAKE_CUDA_ARCHITECTURES="$cuda_arch"

cmake --build "$repo/build" --parallel "$(nproc)"   --target llama-cli llama-server llama-bench

git -C "$repo" status --short
"$repo/build/bin/llama-cli" --version
"$repo/build/bin/llama-cli" --list-devices
