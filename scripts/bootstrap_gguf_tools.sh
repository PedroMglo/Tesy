#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source_dir="${TESY_LLAMA_CPP_DIR:-$root/.deps/llama.cpp}"

if [[ ! -d "$source_dir/gguf-py" ]]; then
  echo "missing pinned llama.cpp gguf-py: $source_dir/gguf-py" >&2
  echo "run scripts/bootstrap_llama_cpp.sh first" >&2
  exit 1
fi

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
actual="$(git -C "$source_dir" rev-parse HEAD)"
[[ "$actual" == "$expected" ]] || {
  echo "llama.cpp source pin mismatch: $actual != $expected" >&2
  exit 1
}
[[ -z "$(git -C "$source_dir" status --porcelain)" ]] || {
  echo "llama.cpp source checkout is dirty" >&2
  exit 1
}

python -m pip install -e "$source_dir/gguf-py"
python - <<'PY'
from gguf.gguf_reader import GGUFReader
print("pinned gguf-py import: OK", GGUFReader)
PY
