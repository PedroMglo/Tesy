#!/usr/bin/env bash
# Explicit user action: downloads SOURCE only; no models. No system changes.
set -euo pipefail
cd "$(dirname "$0")/.."
readarray -t LOCK < <(python3 -c 'import json; d=json.load(open("configs/backend.lock.json")); print(d["repository"]); print(d["commit"])')
DEST="third_party/llama.cpp"
if [[ -e "$DEST" ]]; then
    echo "Refusing existing source destination: $DEST" >&2
    exit 2
fi
mkdir -p third_party
git init "$DEST"
git -C "$DEST" remote add origin "${LOCK[0]}"
git -C "$DEST" fetch --depth 1 origin "${LOCK[1]}"
git -C "$DEST" checkout --detach FETCH_HEAD
test "$(git -C "$DEST" rev-parse HEAD)" = "${LOCK[1]}"
cmake -S "$DEST" -B "$DEST/build-tesy" -DGGML_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES=89 -DCMAKE_BUILD_TYPE=Release
cmake --build "$DEST/build-tesy" --parallel 4 --target llama-cli
sha256sum "$DEST/build-tesy/bin/llama-cli"
echo "Build only; no model executed. Inspect runtime dependencies with ldd before running."
