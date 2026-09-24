#!/usr/bin/env bash
set -Eeuo pipefail

if [[ $# -ne 2 ]]; then
  echo "usage: $0 MODEL.gguf OUTPUT_ROOT" >&2
  exit 2
fi

model="$1"
out="$2"
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
python_bin="$root/.venv/bin/python"
source_dir="$root/.deps/llama.cpp"
build_dir="$root/build/tesy-mixed-residency"
mixed_tool="$build_dir/tesy-mixed-residency"
capture_tool="$build_dir/tesy-routed-layer-capture"
prompt="$root/benchmarks/prompts/b0-b1-diagnostic.txt"
lock_file="${XDG_RUNTIME_DIR:-/tmp}/tesy-live-moe-reinjection-continuation.lock"
stage="initialization"
active_pid=""
monitor_pid=""
active_stopped=0

[[ ! -e "$out" ]] || {
  echo "refusing to replace output root: $out" >&2
  exit 1
}
mkdir -p "$out"

cleanup() {
  local rc=$?
  if [[ -n "$active_pid" ]] && kill -0 "$active_pid" 2>/dev/null; then
    if [[ "$active_stopped" -eq 1 ]]; then
      kill -CONT "$active_pid" 2>/dev/null || true
    fi
    kill "$active_pid" 2>/dev/null || true
    wait "$active_pid" 2>/dev/null || true
  fi
  if [[ -n "$monitor_pid" ]] && kill -0 "$monitor_pid" 2>/dev/null; then
    kill "$monitor_pid" 2>/dev/null || true
    wait "$monitor_pid" 2>/dev/null || true
  fi
  if [[ "$rc" -ne 0 && ! -e "$out/failure.json" ]]; then
    python3 - "$out/failure.json" "$stage" "$rc" <<'PY' || true
import json
import sys
from pathlib import Path

with Path(sys.argv[1]).open("x", encoding="utf-8") as handle:
    json.dump({
        "schema": "tesy.live_moe_reinjection_continuation_failure.v1",
        "classification": "FAIL_CAMPAIGN_STAGE",
        "stage": sys.argv[2],
        "exit_code": int(sys.argv[3]),
        "claim_boundary": "Failure evidence only; no correctness GO follows.",
    }, handle, indent=2, sort_keys=True)
    handle.write("\n")
PY
  fi
}
trap cleanup EXIT

exec 9>"$lock_file"
flock -n 9 || { echo "another reinjection campaign holds the lock" >&2; exit 1; }

stage="source_and_inputs"
[[ -x "$python_bin" && -x "$mixed_tool" && -x "$capture_tool" ]]
git -C "$root" rev-parse HEAD >"$out/tesy-head.txt"
git -C "$root" rev-parse HEAD^{tree} >"$out/tesy-tree.txt"
git -C "$root" status --porcelain=v1 >"$out/tesy-status.txt"
git -C "$source_dir" rev-parse HEAD >"$out/llama-head.txt"
git -C "$source_dir" status --porcelain=v1 >"$out/llama-status.txt"
[[ ! -s "$out/tesy-status.txt" && ! -s "$out/llama-status.txt" ]]
[[ "$(cat "$out/llama-head.txt")" == "4e416ee7308dd6b581796f1a6241276cd5982691" ]]
[[ "$(sha256sum "$prompt" | awk '{print $1}')" == "431498aa6a73a4e817c5ef58ceabdac5b8336dd95e01a17903e75bc1d27d10c6" ]]
"$python_bin" -m tesy models verify gpt-oss-20b-mxfp4-gguf "$model" >"$out/model.json"
[[ "$(stat -c %s "$model")" == "12109564352" ]]
[[ "$(sha256sum "$model" | awk '{print $1}')" == "52f57ab7d3df3ba9173827c1c6832e73375553a846f3e32b49f1ae2daad688d4" ]]

stage="host"
"$python_bin" -m tesy doctor --disk-path "$(dirname "$model")" \
  --reference-profile "$root/configs/reference-host.json" >"$out/doctor.json"
"$python_bin" - "$out/doctor.json" <<'PY'
import json
import sys
from pathlib import Path

doctor = json.loads(Path(sys.argv[1]).read_text())
assert doctor["reference_check"]["status"] == "PASS"
snapshot = doctor["snapshot"]
assert snapshot["virtualization"]["status"] == "PHYSICAL"
assert snapshot["gpu"]["status"] == "OK"
assert snapshot["gpu_compute_processes"]["status"] == "OK"
assert not snapshot["gpu_compute_processes"]["stdout"].strip()
assert snapshot["storage_topology"]["findmnt"]["status"] == "OK"
PY

stage="build_provenance"
"$python_bin" - "$root" "$build_dir" "$out" <<'PY'
import hashlib
import json
import subprocess
import sys
from pathlib import Path

root, build, out = map(Path, sys.argv[1:])
manifest = json.loads((build / "tesy-routed-layer-build-provenance.json").read_text())

def sha(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

expected = {
    "tesy_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip(),
    "llama_head": "4e416ee7308dd6b581796f1a6241276cd5982691",
    "mixed_source_sha256": sha(root / "native/tesy_mixed_residency.cpp"),
    "capture_source_sha256": sha(root / "native/tesy_routed_layer_capture.cpp"),
    "cmake_lists_sha256": sha(root / "native/CMakeLists.txt"),
    "mixed_tool_sha256": sha(build / "tesy-mixed-residency"),
    "capture_tool_sha256": sha(build / "tesy-routed-layer-capture"),
    "mixed_tool_path": str((build / "tesy-mixed-residency").resolve()),
    "capture_tool_path": str((build / "tesy-routed-layer-capture").resolve()),
}
assert manifest["schema"] == "tesy.routed_layer_native_build.v1"
assert manifest["status"] == "PASS"
assert all(manifest.get(key) == value for key, value in expected.items())
(out / "native-build-provenance-validation.json").write_text(json.dumps({
    "schema": "tesy.live_moe_reinjection_build_validation.v1",
    "status": "PASS", "expected": expected,
}, indent=2, sort_keys=True) + "\n")
PY

stage="launch"
cmd=("$mixed_tool" --model "$model" --output "$out/raw.json"
  --layer 0 --threads 12 --live-reinjection-exactness
  --prompt-file "$prompt" --ctx 4096)
"$python_bin" - "$out/argv.json" "${cmd[@]}" <<'PY'
import json
import sys
from pathlib import Path

Path(sys.argv[1]).write_text(json.dumps(sys.argv[2:], indent=2) + "\n")
PY
"${cmd[@]}" >"$out/tool.stdout.txt" 2>"$out/tool.stderr.txt" &
active_pid=$!
"$python_bin" -m tesy.resource_monitor --pid "$active_pid" \
  --output "$out/resources.jsonl" --interval-ms 100 &
monitor_pid=$!

stage="runtime_provenance"
mapped=0
for _ in $(seq 1 4000); do
  kill -0 "$active_pid" 2>/dev/null || { echo "native process exited before provenance" >&2; exit 1; }
  if rg -q 'libggml-cuda\.so' "/proc/$active_pid/maps" 2>/dev/null; then
    kill -STOP "$active_pid"
    active_stopped=1
    mapped=1
    break
  fi
  sleep 0.005
done
[[ "$mapped" -eq 1 ]]
"$python_bin" -m tesy.mixed_residency_provenance \
  --pid "$active_pid" --expected-executable "$mixed_tool" \
  --build-dir "$build_dir" --expected-argv "$out/argv.json" \
  --output "$out/runtime-provenance.json"
kill -CONT "$active_pid"
active_stopped=0

stage="native_execution"
set +e
wait "$active_pid"
tool_rc=$?
set -e
active_pid=""
wait "$monitor_pid"
monitor_pid=""
[[ "$tool_rc" -eq 0 ]] || { echo "native reinjection failed ($tool_rc)" >&2; exit "$tool_rc"; }

stage="independent_validation"
"$python_bin" -m tesy.live_moe_reinjection_continuation_exactness \
  --input "$out/raw.json" --output "$out/summary.json"

stage="resource_validation"
"$python_bin" - "$out/doctor.json" "$out/resources.jsonl" "$out/resource-summary.json" <<'PY'
import json
import math
import sys
from pathlib import Path

doctor = json.loads(Path(sys.argv[1]).read_text())
rows = [json.loads(line) for line in Path(sys.argv[2]).read_text().splitlines() if line.strip()]
assert rows
assert all(row.get("gpu", {}).get("status") == "OK" for row in rows)
gpu = [row["gpu"] for row in rows]
peak_swap = max(row.get("process", {}).get("VmSwap_bytes", 0) for row in rows)
min_mem = min(row["system"]["MemAvailable_bytes"] for row in rows)
gpu_total = doctor["snapshot"]["gpu"]["gpus"][0]["memory_total_bytes"]
peak_gpu = max(row["memory_used_bytes"] for row in gpu)
assert peak_swap == 0
assert min_mem >= 2 * 1024**3
assert gpu_total - peak_gpu >= 1024**3
assert all(math.isfinite(row["power_w"]) and math.isfinite(row["temperature_c"]) for row in gpu)
Path(sys.argv[3]).write_text(json.dumps({
    "schema": "tesy.live_moe_reinjection_continuation_resources.v1",
    "status": "PASS", "samples": len(rows), "gpu_failed_samples": 0,
    "peak_process_swap_bytes": peak_swap,
    "min_mem_available_bytes": min_mem,
    "min_observed_gpu_free_bytes": gpu_total - peak_gpu,
    "max_gpu_temperature_c": max(row["temperature_c"] for row in gpu),
    "max_gpu_power_w": max(row["power_w"] for row in gpu),
}, indent=2, sort_keys=True) + "\n")
PY

echo "PASS_LIVE_MOE_REINJECTION_CONTINUATION_EXACTNESS"
echo "outputs: $out"
