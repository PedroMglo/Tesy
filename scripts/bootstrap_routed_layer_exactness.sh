#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source_dir="${TESY_LLAMA_CPP_DIR:-$root/.deps/llama.cpp}"
build_dir="${TESY_MIXED_BUILD_DIR:-$root/build/tesy-mixed-residency}"
build_jobs="${TESY_BUILD_JOBS:-4}"

bash "$root/scripts/bootstrap_mixed_residency.sh"

test -z "$(git -C "$root" status --porcelain)" || {
  echo "Tesy checkout must remain clean after mixed-residency bootstrap" >&2
  exit 1
}

cmake --build "$build_dir" \
  --parallel "$build_jobs" \
  --target tesy-routed-layer-capture

mixed_tool="$build_dir/tesy-mixed-residency"
capture_tool="$build_dir/tesy-routed-layer-capture"
manifest="$build_dir/tesy-routed-layer-build-provenance.json"

"$mixed_tool" --help >/dev/null
"$capture_tool" --help >/dev/null

tesy_head="$(git -C "$root" rev-parse HEAD)"
llama_head="$(git -C "$source_dir" rev-parse HEAD)"

python3 - \
  "$manifest" \
  "$tesy_head" \
  "$llama_head" \
  "$root/native/tesy_mixed_residency.cpp" \
  "$root/native/tesy_routed_layer_capture.cpp" \
  "$root/native/CMakeLists.txt" \
  "$mixed_tool" \
  "$capture_tool" <<'PY'
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
    "schema": "tesy.routed_layer_native_build.v1",
    "classification": "MEASURED_LOCAL_BUILD_PROVENANCE",
    "tesy_head": sys.argv[2],
    "llama_head": sys.argv[3],
    "mixed_source_sha256": sha256(Path(sys.argv[4])),
    "capture_source_sha256": sha256(Path(sys.argv[5])),
    "cmake_lists_sha256": sha256(Path(sys.argv[6])),
    "mixed_tool_sha256": sha256(Path(sys.argv[7])),
    "capture_tool_sha256": sha256(Path(sys.argv[8])),
    "mixed_tool_path": str(Path(sys.argv[7]).resolve()),
    "capture_tool_path": str(Path(sys.argv[8]).resolve()),
    "status": "PASS",
}
tmp = output.with_name(output.name + ".tmp")
with tmp.open("w", encoding="utf-8") as handle:
    json.dump(payload, handle, indent=2, sort_keys=True)
    handle.write("\n")
os.replace(tmp, output)
PY

echo "PASS_ROUTED_LAYER_BUILD"
echo "manifest: $manifest"
