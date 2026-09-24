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
source_dir="${TESY_LLAMA_CPP_DIR:-$root/.deps/llama.cpp}"
build_dir="${TESY_MIXED_BUILD_DIR:-$root/build/tesy-mixed-residency}"
mixed_tool="$build_dir/tesy-mixed-residency"
capture_tool="$build_dir/tesy-routed-layer-capture"
build_manifest="$build_dir/tesy-routed-layer-build-provenance.json"
prompt="$root/benchmarks/prompts/b0-b1-diagnostic.txt"
lock_file="${XDG_RUNTIME_DIR:-/tmp}/tesy-routed-layer-exactness.lock"

expected_llama="4e416ee7308dd6b581796f1a6241276cd5982691"
expected_model_sha="52f57ab7d3df3ba9173827c1c6832e73375553a846f3e32b49f1ae2daad688d4"
expected_prompt_sha="431498aa6a73a4e817c5ef58ceabdac5b8336dd95e01a17903e75bc1d27d10c6"

stage="initialization"
active_pid=""
monitor_pid=""
active_stopped=0

if [[ -e "$out" ]]; then
  echo "refusing to replace output root: $out" >&2
  exit 1
fi
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
    wait "$monitor_pid" 2>/dev/null || true
  fi
  if [[ "$rc" -ne 0 && ! -e "$out/failure.json" ]]; then
    python3 - "$out/failure.json" "$stage" "$rc" <<'PY' || true
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
payload = {
    "schema": "tesy.routed_layer_exactness_failure.v1",
    "classification": "FAIL_CAMPAIGN_STAGE",
    "stage": sys.argv[2],
    "exit_code": int(sys.argv[3]),
    "claim_boundary": (
        "Execution failure provenance only. No routed-layer correctness or "
        "performance conclusion follows beyond the failed gate."
    ),
}
try:
    with path.open("x", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
except FileExistsError:
    pass
PY
  fi
}
trap cleanup EXIT

failure_report() {
  local rc="$1"
  local command="$2"
  local line="$3"
  trap - ERR
  python3 - "$out/failure.json" "$stage" "$rc" "$line" "$command" <<'PY' || true
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
payload = {
    "schema": "tesy.routed_layer_exactness_failure.v1",
    "classification": "FAIL_CAMPAIGN_STAGE",
    "stage": sys.argv[2],
    "exit_code": int(sys.argv[3]),
    "line": int(sys.argv[4]),
    "failed_command": sys.argv[5],
    "claim_boundary": (
        "Execution failure provenance only. No routed-layer correctness or "
        "performance conclusion follows beyond the failed gate."
    ),
}
try:
    with path.open("x", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
except FileExistsError:
    pass
PY
  echo "FAIL_ROUTED_LAYER_EXACTNESS stage=$stage line=$line exit=$rc" >&2
  exit "$rc"
}
trap 'rc=$?; cmd=$BASH_COMMAND; line=$LINENO; failure_report "$rc" "$cmd" "$line"' ERR

exec 9>"$lock_file"
if ! flock -n 9; then
  echo "another routed-layer exactness campaign holds $lock_file" >&2
  exit 1
fi

write_argv() {
  local path="$1"
  shift
  "$python_bin" - "$path" "$@" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
argv = sys.argv[2:]
if not argv or any(not item for item in argv):
    raise SystemExit("invalid frozen argv")
with path.open("x", encoding="utf-8") as handle:
    json.dump(argv, handle, indent=2)
    handle.write("\n")
PY
}

stage="python_environment"
[[ -x "$python_bin" ]] || {
  echo "missing project virtualenv Python: $python_bin" >&2
  exit 1
}
"$python_bin" - "$root" >"$out/python-provenance.json" <<'PY'
import json
import sys
from pathlib import Path

import tesy

root = Path(sys.argv[1]).resolve()
module = Path(tesy.__file__).resolve()
if root not in module.parents:
    raise SystemExit(
        f"tesy imported outside current worktree: {module} not under {root}"
    )
print(json.dumps({
    "schema": "tesy.python_environment.v1",
    "classification": "MEASURED_LOCAL_PROVENANCE",
    "executable": str(Path(sys.executable).resolve()),
    "version": sys.version,
    "tesy_module": str(module),
    "status": "PASS",
}, indent=2, sort_keys=True))
PY

stage="source_provenance"
git -C "$root" rev-parse HEAD >"$out/tesy-head.txt"
git -C "$root" rev-parse HEAD^{tree} >"$out/tesy-tree.txt"
git -C "$root" status --porcelain=v1 >"$out/tesy-status.txt"
git -C "$source_dir" rev-parse HEAD >"$out/llama-head.txt"
git -C "$source_dir" status --porcelain=v1 >"$out/llama-status.txt"

[[ ! -s "$out/tesy-status.txt" ]] || {
  echo "Tesy worktree must be clean" >&2
  exit 1
}
[[ ! -s "$out/llama-status.txt" ]] || {
  echo "llama.cpp worktree must be clean" >&2
  exit 1
}
[[ "$(cat "$out/llama-head.txt")" == "$expected_llama" ]] || {
  echo "llama.cpp pin mismatch" >&2
  exit 1
}

stage="input_identity"
[[ -f "$prompt" ]] || {
  echo "missing frozen prompt: $prompt" >&2
  exit 1
}
observed_prompt_sha="$(sha256sum "$prompt" | awk '{print $1}')"
[[ "$observed_prompt_sha" == "$expected_prompt_sha" ]] || {
  echo "frozen prompt SHA mismatch" >&2
  exit 1
}
printf '%s\n' "$observed_prompt_sha" >"$out/prompt-sha256.txt"

"$python_bin" -m tesy models verify \
  gpt-oss-20b-mxfp4-gguf \
  "$model" >"$out/model.json"
observed_model_sha="$(sha256sum "$model" | awk '{print $1}')"
[[ "$observed_model_sha" == "$expected_model_sha" ]] || {
  echo "model SHA mismatch" >&2
  exit 1
}

stage="reference_host"
"$python_bin" -m tesy doctor \
  --disk-path "$(dirname "$model")" \
  --reference-profile "$root/configs/reference-host.json" \
  >"$out/doctor.json"

"$python_bin" - "$out/doctor.json" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
if payload.get("reference_check", {}).get("status") != "PASS":
    raise SystemExit("reference host identity did not PASS")
virtualization = payload.get("snapshot", {}).get("virtualization", {})
if virtualization.get("status") != "PHYSICAL":
    raise SystemExit("reference host is not proven PHYSICAL")
apps = payload.get("snapshot", {}).get("gpu_compute_processes", {})
if apps.get("status") != "OK":
    raise SystemExit("GPU compute-process probe failed")
if apps.get("stdout", "").strip():
    raise SystemExit("competing GPU compute process detected")
PY

stage="native_build_identity"
for tool in "$mixed_tool" "$capture_tool"; do
  [[ -x "$tool" ]] || {
    echo "missing native tool: $tool" >&2
    echo "run scripts/bootstrap_routed_layer_exactness.sh first" >&2
    exit 1
  }
done
[[ -f "$build_manifest" ]] || {
  echo "missing routed-layer build provenance: $build_manifest" >&2
  exit 1
}

"$python_bin" - \
  "$build_manifest" \
  "$out/tesy-head.txt" \
  "$out/llama-head.txt" \
  "$root/native/tesy_mixed_residency.cpp" \
  "$root/native/tesy_routed_layer_capture.cpp" \
  "$root/native/CMakeLists.txt" \
  "$mixed_tool" \
  "$capture_tool" \
  >"$out/native-build-provenance-validation.json" <<'PY'
import hashlib
import json
import sys
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


manifest = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
if manifest.get("schema") != "tesy.routed_layer_native_build.v1":
    raise SystemExit("unexpected routed-layer build provenance schema")
if manifest.get("status") != "PASS":
    raise SystemExit("routed-layer build provenance did not PASS")

expected = {
    "tesy_head": Path(sys.argv[2]).read_text(encoding="utf-8").strip(),
    "llama_head": Path(sys.argv[3]).read_text(encoding="utf-8").strip(),
    "mixed_source_sha256": sha256(Path(sys.argv[4])),
    "capture_source_sha256": sha256(Path(sys.argv[5])),
    "cmake_lists_sha256": sha256(Path(sys.argv[6])),
    "mixed_tool_sha256": sha256(Path(sys.argv[7])),
    "capture_tool_sha256": sha256(Path(sys.argv[8])),
    "mixed_tool_path": str(Path(sys.argv[7]).resolve()),
    "capture_tool_path": str(Path(sys.argv[8]).resolve()),
}
mismatches = {
    key: {"expected": value, "observed": manifest.get(key)}
    for key, value in expected.items()
    if manifest.get(key) != value
}
print(json.dumps({
    "schema": "tesy.routed_layer_native_build_validation.v1",
    "classification": "MEASURED_LOCAL_BUILD_PROVENANCE",
    "status": "PASS" if not mismatches else "FAIL",
    "expected": expected,
    "mismatches": mismatches,
}, indent=2, sort_keys=True))
if mismatches:
    raise SystemExit(f"routed-layer build provenance mismatch: {mismatches}")
PY

stage="build_cache"
"$python_bin" - "$build_dir/CMakeCache.txt" >"$out/build-cache-summary.json" <<'PY'
import json
import sys
from pathlib import Path

expected = {
    "CMAKE_BUILD_TYPE": "Release",
    "GGML_CUDA": "ON",
    "GGML_BACKEND_DL": "OFF",
    "CMAKE_CUDA_ARCHITECTURES": "89",
    "CMAKE_C_COMPILER": "/usr/bin/gcc-15",
    "CMAKE_CXX_COMPILER": "/usr/bin/g++-15",
    "CMAKE_CUDA_COMPILER": "/usr/local/cuda/bin/nvcc",
}
cache = {}
for raw in Path(sys.argv[1]).read_text(encoding="utf-8").splitlines():
    line = raw.strip()
    if not line or line.startswith(("#", "//")) or "=" not in line:
        continue
    left, value = line.split("=", 1)
    if ":" not in left:
        continue
    key, _ = left.split(":", 1)
    cache[key] = value

mismatches = {
    key: {"expected": value, "observed": cache.get(key)}
    for key, value in expected.items()
    if cache.get(key) != value
}
print(json.dumps({
    "schema": "tesy.routed_layer_build_cache.v1",
    "status": "PASS" if not mismatches else "FAIL",
    "selected": {key: cache.get(key) for key in expected},
    "mismatches": mismatches,
}, indent=2, sort_keys=True))
if mismatches:
    raise SystemExit(f"routed-layer build cache mismatch: {mismatches}")
PY

run_capture() {
  local mode="$1"
  local dir="$out/capture-$mode"
  mkdir "$dir"

  local tokens="$dir/tokens.json"
  local argv_json="$dir/argv.json"
  local identity="$dir/process-identity.json"
  local resources="$dir/resources.jsonl"
  local stdout="$dir/tool.stdout.txt"
  local stderr="$dir/tool.stderr.txt"

  local cmd=(
    "$capture_tool"
    --model "$model"
    --prompt-file "$prompt"
    --tokens-out "$tokens"
    --ngl 0
    --ctx 4096
  )
  if [[ "$mode" == "on" ]]; then
    cmd+=(--capture-dir "$dir/capture")
  fi

  write_argv "$argv_json" "${cmd[@]}"

  "${cmd[@]}" >"$stdout" 2>"$stderr" &
  active_pid=$!

  "$python_bin" -m tesy.resource_monitor \
    --pid "$active_pid" \
    --output "$resources" \
    --interval-ms 100 &
  monitor_pid=$!

  "$python_bin" -m tesy.process_identity \
    --pid "$active_pid" \
    --expected-executable "$capture_tool" \
    --expected-argv "$argv_json" \
    --output "$identity"

  set +e
  wait "$active_pid"
  local rc=$?
  set -e
  active_pid=""

  wait "$monitor_pid"
  monitor_pid=""

  [[ "$rc" -eq 0 ]] || {
    echo "stock capture $mode failed with exit $rc" >&2
    return "$rc"
  }
  [[ -f "$tokens" ]] || {
    echo "stock capture $mode token output missing" >&2
    return 1
  }
}

stage="stock_capture_off"
run_capture off

stage="stock_capture_on"
run_capture on

stage="capture_validation"
"$python_bin" - "$out/capture-on/capture/metadata.json" \
  "$out/capture-on/capture/activation.f32" \
  "$out/capture-on/capture/stock-output.f32" \
  >"$out/capture-validation.json" <<'PY'
import hashlib
import json
import sys
from pathlib import Path

from tesy.routed_layer_exactness import validate_capture_metadata


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


metadata_path = Path(sys.argv[1])
activation = Path(sys.argv[2])
stock_output = Path(sys.argv[3])
payload = json.loads(metadata_path.read_text(encoding="utf-8"))
validated = validate_capture_metadata(payload)

expected_bytes = 2880 * 4
if activation.stat().st_size != expected_bytes:
    raise SystemExit("captured activation byte size mismatch")
if stock_output.stat().st_size != expected_bytes:
    raise SystemExit("captured stock output byte size mismatch")

print(json.dumps({
    "schema": "tesy.routed_layer_capture_validation.v1",
    "classification": "MEASURED_STOCK_ROUTED_LAYER_CAPTURE",
    "status": "PASS",
    **validated,
    "activation_sha256": sha256(activation),
    "stock_output_sha256": sha256(stock_output),
    "activation_bytes": activation.stat().st_size,
    "stock_output_bytes": stock_output.stat().st_size,
}, indent=2, sort_keys=True))
PY

mapfile -t routed_values < <(
  "$python_bin" - "$out/capture-on/capture/metadata.json" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
experts = payload["selected_experts"]
weights = payload["routing_weights"]
print(",".join(str(value) for value in experts))
print(",".join(format(float(value), ".9g") for value in weights))
PY
)
[[ "${#routed_values[@]}" -eq 2 ]] || {
  echo "failed extracting routed expert IDs/weights" >&2
  exit 1
}
experts_csv="${routed_values[0]}"
weights_csv="${routed_values[1]}"

run_replay() {
  local h="$1"
  local dir="$out/replay-h$h"
  mkdir "$dir"

  local raw="$dir/raw.json"
  local argv_json="$dir/argv.json"
  local provenance="$dir/runtime-provenance.json"
  local resources="$dir/resources.jsonl"
  local stdout="$dir/tool.stdout.txt"
  local stderr="$dir/tool.stderr.txt"

  local cmd=(
    "$mixed_tool"
    --model "$model"
    --output "$raw"
    --layer 0
    --threads 12
    --async-overlap
    --routed-exactness
    --routed-input-f32 "$out/capture-on/capture/activation.f32"
    --routed-reference-f32 "$out/capture-on/capture/stock-output.f32"
    --routed-experts "$experts_csv"
    --routed-weights "$weights_csv"
    --routed-gpu-hits "$h"
  )

  write_argv "$argv_json" "${cmd[@]}"

  "${cmd[@]}" >"$stdout" 2>"$stderr" &
  active_pid=$!

  "$python_bin" -m tesy.resource_monitor \
    --pid "$active_pid" \
    --output "$resources" \
    --interval-ms 50 &
  monitor_pid=$!

  active_stopped=0
  local mapped=0
  for _ in $(seq 1 2000); do
    if ! kill -0 "$active_pid" 2>/dev/null; then
      echo "replay h=$h exited before live CUDA provenance" >&2
      return 1
    fi
    if grep -F "libggml-cuda.so" "/proc/$active_pid/maps" >/dev/null 2>&1; then
      kill -STOP "$active_pid"
      active_stopped=1
      mapped=1
      break
    fi
    sleep 0.005
  done
  [[ "$mapped" -eq 1 ]] || {
    echo "timed out waiting for replay h=$h CUDA mapping" >&2
    return 1
  }

  "$python_bin" -m tesy.mixed_residency_provenance \
    --pid "$active_pid" \
    --expected-executable "$mixed_tool" \
    --build-dir "$build_dir" \
    --expected-argv "$argv_json" \
    --output "$provenance"

  kill -CONT "$active_pid"
  active_stopped=0

  set +e
  wait "$active_pid"
  local rc=$?
  set -e
  active_pid=""

  wait "$monitor_pid"
  monitor_pid=""

  [[ "$rc" -eq 0 ]] || {
    echo "routed replay h=$h failed with exit $rc" >&2
    return "$rc"
  }
  [[ -f "$raw" ]] || {
    echo "routed replay h=$h raw result missing" >&2
    return 1
  }
}

stage="routed_replay_h2"
run_replay 2

stage="routed_replay_h3"
run_replay 3

stage="exactness_validation"
"$python_bin" -m tesy.routed_layer_exactness \
  --capture-metadata "$out/capture-on/capture/metadata.json" \
  --off-tokens "$out/capture-off/tokens.json" \
  --on-tokens "$out/capture-on/tokens.json" \
  --replay-h2 "$out/replay-h2/raw.json" \
  --replay-h3 "$out/replay-h3/raw.json" \
  --output "$out/exactness-summary.json"

stage="resource_validation"
"$python_bin" - "$out/doctor.json" "$out" >"$out/resource-summary.json" <<'PY'
import json
import sys
from pathlib import Path

doctor = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
root = Path(sys.argv[2])
paths = [
    root / "capture-off" / "resources.jsonl",
    root / "capture-on" / "resources.jsonl",
    root / "replay-h2" / "resources.jsonl",
    root / "replay-h3" / "resources.jsonl",
]

per_process = {}
all_rows = []
for path in paths:
    rows = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if not rows:
        raise SystemExit(f"no resource samples in {path}")
    valid_gpu = [
        row["gpu"]
        for row in rows
        if row.get("gpu", {}).get("status") == "OK"
    ]
    if len(valid_gpu) != len(rows):
        raise SystemExit(
            f"GPU telemetry incomplete for {path}: "
            f"{len(valid_gpu)}/{len(rows)}"
        )
    label = path.parent.name
    per_process[label] = {
        "samples": len(rows),
        "gpu_valid_samples": len(valid_gpu),
        "peak_process_rss_bytes": max(
            row.get("process", {}).get("VmRSS_bytes", 0)
            for row in rows
        ),
        "peak_process_swap_bytes": max(
            row.get("process", {}).get("VmSwap_bytes", 0)
            for row in rows
        ),
    }
    all_rows.extend(rows)

gpu_rows = [row["gpu"] for row in all_rows]
system_rows = [row["system"] for row in all_rows]
gpu_total = doctor["snapshot"]["gpu"]["gpus"][0]["memory_total_bytes"]
peak_gpu = max(row["memory_used_bytes"] for row in gpu_rows)
peak_swap = max(
    row.get("process", {}).get("VmSwap_bytes", 0)
    for row in all_rows
)
min_mem = min(row["MemAvailable_bytes"] for row in system_rows)

summary = {
    "schema": "tesy.routed_layer_exactness_resources.v1",
    "classification": "MEASURED_RUNTIME_RESOURCES",
    "status": "PASS",
    "per_process": per_process,
    "samples": len(all_rows),
    "gpu_valid_samples": len(gpu_rows),
    "gpu_failed_samples": 0,
    "peak_gpu_memory_used_bytes": peak_gpu,
    "min_observed_gpu_free_bytes": gpu_total - peak_gpu,
    "peak_process_swap_bytes": peak_swap,
    "min_mem_available_bytes": min_mem,
    "max_gpu_temperature_c": max(
        row["temperature_c"] for row in gpu_rows
    ),
    "max_gpu_power_w": max(row["power_w"] for row in gpu_rows),
    "claim_boundary": (
        "Sampled resources for stock OFF/ON capture and h=2/h=3 "
        "correctness replays. This is not latency or physical traffic."
    ),
}
if peak_swap != 0:
    raise SystemExit("routed exactness process used swap")
if summary["min_observed_gpu_free_bytes"] < 1024 * 1024 * 1024:
    raise SystemExit("routed exactness violated 1024 MiB GPU headroom")
if min_mem < 2 * 1024 * 1024 * 1024:
    raise SystemExit("routed exactness violated 2048 MiB host headroom")

print(json.dumps(summary, indent=2, sort_keys=True))
PY

stage="result"
"$python_bin" - "$out/exactness-summary.json" <<'PY'
import json
import sys
from pathlib import Path

result = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
if result.get("status") != "PASS":
    raise SystemExit("routed layer exactness summary did not PASS")
if result.get("decision") != "ROUTED_LAYER_EXACTNESS_GO":
    raise SystemExit("routed layer exactness did not GO")

print("PASS_ROUTED_LAYER_EXACTNESS")
print("decision:", result["decision"])
print("token_ids:", result["token_ids"])
print("selected_experts:", result["selected_experts"])
print("routing_weight_tensor:", result["routing_weight_tensor"])
for row in result["cases"]:
    print(
        f"h={row['gpu_hits']} "
        f"serial_vs_stock={row['serial_vs_stock']['status']} "
        f"async_vs_stock={row['async_vs_stock']['status']} "
        f"async_vs_serial={row['async_vs_serial']['status']}"
    )
print("claim_boundary:", result["claim_boundary"])
PY

echo "outputs: $out"
