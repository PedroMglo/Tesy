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
capture_tool="$build_dir/tesy-routed-layer-capture"
mixed_tool="$build_dir/tesy-mixed-residency"
build_manifest="$build_dir/tesy-routed-layer-build-provenance.json"
prompt="$root/benchmarks/prompts/b0-b1-diagnostic.txt"
lock_file="${XDG_RUNTIME_DIR:-/tmp}/tesy-cb-eval-intercept-bound.lock"

expected_llama="4e416ee7308dd6b581796f1a6241276cd5982691"
expected_model_sha="52f57ab7d3df3ba9173827c1c6832e73375553a846f3e32b49f1ae2daad688d4"
expected_prompt_sha="431498aa6a73a4e817c5ef58ceabdac5b8336dd95e01a17903e75bc1d27d10c6"

stage="initialization"
tool_pid=""
monitor_pid=""

if [[ -e "$out" ]]; then
  echo "refusing to replace output root: $out" >&2
  exit 1
fi
mkdir -p "$out"

cleanup() {
  local rc=$?
  if [[ -n "$tool_pid" ]] && kill -0 "$tool_pid" 2>/dev/null; then
    kill "$tool_pid" 2>/dev/null || true
    wait "$tool_pid" 2>/dev/null || true
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
    "schema": "tesy.cb_eval_intercept_bound_failure.v1",
    "classification": "FAIL_CAMPAIGN_STAGE",
    "stage": sys.argv[2],
    "exit_code": int(sys.argv[3]),
    "claim_boundary": (
        "Execution failure provenance only. No cb_eval interception "
        "feasibility or performance conclusion follows."
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
    "schema": "tesy.cb_eval_intercept_bound_failure.v1",
    "classification": "FAIL_CAMPAIGN_STAGE",
    "stage": sys.argv[2],
    "exit_code": int(sys.argv[3]),
    "line": int(sys.argv[4]),
    "failed_command": sys.argv[5],
    "claim_boundary": (
        "Execution failure provenance only. No cb_eval interception "
        "feasibility or performance conclusion follows."
    ),
}
try:
    with path.open("x", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
except FileExistsError:
    pass
PY
  echo "FAIL_CB_EVAL_INTERCEPT_BOUND stage=$stage line=$line exit=$rc" >&2
  exit "$rc"
}
trap 'rc=$?; cmd=$BASH_COMMAND; line=$LINENO; failure_report "$rc" "$cmd" "$line"' ERR

exec 9>"$lock_file"
if ! flock -n 9; then
  echo "another cb_eval intercept-bound campaign holds $lock_file" >&2
  exit 1
fi

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
for tool in "$capture_tool" "$mixed_tool"; do
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
    "schema": "tesy.cb_eval_intercept_build_validation.v1",
    "classification": "MEASURED_LOCAL_BUILD_PROVENANCE",
    "status": "PASS" if not mismatches else "FAIL",
    "expected": expected,
    "mismatches": mismatches,
}, indent=2, sort_keys=True))
if mismatches:
    raise SystemExit(f"routed-layer build provenance mismatch: {mismatches}")
PY

stage="frozen_argv"
cmd=(
  "$capture_tool"
  --model "$model"
  --prompt-file "$prompt"
  --cancel-bound-output "$out/raw.json"
  --ngl 0
  --ctx 4096
  --warmup 6
  --samples 81
)

"$python_bin" - "$out/argv.json" "${cmd[@]}" <<'PY'
import json
import sys
from pathlib import Path

argv = sys.argv[2:]
if not argv or any(not item for item in argv):
    raise SystemExit("invalid frozen argv")
with Path(sys.argv[1]).open("x", encoding="utf-8") as handle:
    json.dump(argv, handle, indent=2)
    handle.write("\n")
PY

stage="launch"
"${cmd[@]}" >"$out/tool.stdout.txt" 2>"$out/tool.stderr.txt" &
tool_pid=$!

"$python_bin" -m tesy.resource_monitor \
  --pid "$tool_pid" \
  --output "$out/resources.jsonl" \
  --interval-ms 100 &
monitor_pid=$!

stage="live_process_identity"
"$python_bin" -m tesy.process_identity \
  --pid "$tool_pid" \
  --expected-executable "$capture_tool" \
  --expected-argv "$out/argv.json" \
  --output "$out/process-identity.json"

stage="benchmark_completion"
set +e
wait "$tool_pid"
tool_rc=$?
set -e
tool_pid=""

wait "$monitor_pid"
monitor_pid=""

[[ "$tool_rc" -eq 0 ]] || {
  echo "cb_eval intercept-bound tool failed with exit $tool_rc" >&2
  exit "$tool_rc"
}
[[ -f "$out/raw.json" ]] || {
  echo "cb_eval intercept-bound raw result missing" >&2
  exit 1
}

stage="bound_validation"
"$python_bin" -m tesy.cb_eval_intercept_bound \
  --input "$out/raw.json" \
  --output "$out/summary.json"

stage="resource_validation"
"$python_bin" - "$out/doctor.json" "$out/resources.jsonl" \
  >"$out/resource-summary.json" <<'PY'
import json
import sys
from pathlib import Path

doctor = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
rows = [
    json.loads(line)
    for line in Path(sys.argv[2]).read_text(encoding="utf-8").splitlines()
    if line.strip()
]
if not rows:
    raise SystemExit("no resource samples recorded")

valid_gpu = [
    row["gpu"]
    for row in rows
    if row.get("gpu", {}).get("status") == "OK"
]
if len(valid_gpu) != len(rows):
    raise SystemExit(
        f"GPU telemetry incomplete: {len(valid_gpu)}/{len(rows)}"
    )

gpu_total = doctor["snapshot"]["gpu"]["gpus"][0]["memory_total_bytes"]
peak_gpu = max(row["memory_used_bytes"] for row in valid_gpu)
peak_swap = max(
    row.get("process", {}).get("VmSwap_bytes", 0)
    for row in rows
)
min_mem = min(
    row["system"]["MemAvailable_bytes"]
    for row in rows
)

summary = {
    "schema": "tesy.cb_eval_intercept_bound_resources.v1",
    "classification": "MEASURED_RUNTIME_RESOURCES",
    "status": "PASS",
    "samples": len(rows),
    "gpu_valid_samples": len(valid_gpu),
    "gpu_failed_samples": 0,
    "peak_process_rss_bytes": max(
        row.get("process", {}).get("VmRSS_bytes", 0)
        for row in rows
    ),
    "peak_process_swap_bytes": peak_swap,
    "peak_gpu_memory_used_bytes": peak_gpu,
    "min_observed_gpu_free_bytes": gpu_total - peak_gpu,
    "min_mem_available_bytes": min_mem,
    "max_gpu_temperature_c": max(
        row["temperature_c"]
        for row in valid_gpu
    ),
    "max_gpu_power_w": max(
        row["power_w"]
        for row in valid_gpu
    ),
    "claim_boundary": (
        "Sampled runtime resources for the zero-Tesy-work cb_eval "
        "interception bound. This is not physical traffic evidence."
    ),
}
if peak_swap != 0:
    raise SystemExit("cb_eval intercept-bound process used swap")
if summary["min_observed_gpu_free_bytes"] < 1024 * 1024 * 1024:
    raise SystemExit("cb_eval bound violated 1024 MiB GPU headroom")
if min_mem < 2 * 1024 * 1024 * 1024:
    raise SystemExit("cb_eval bound violated 2048 MiB host headroom")

print(json.dumps(summary, indent=2, sort_keys=True))
PY

stage="result"
"$python_bin" - "$out/summary.json" <<'PY'
import json
import sys
from pathlib import Path

summary = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
if summary.get("status") != "PASS":
    raise SystemExit("cb_eval intercept-bound summary did not PASS")
if summary.get("decision") not in {
    "CB_EVAL_INTERCEPT_HARD_NO_GO",
    "CB_EVAL_INTERCEPT_BOUND_SURVIVES",
}:
    raise SystemExit("unexpected cb_eval intercept-bound decision")

print("PASS_CB_EVAL_INTERCEPT_BOUND")
print("decision =", summary["decision"])
print("stock_median_ms =", summary["stock_median_ms"])
print("stock_p95_ms =", summary["stock_p95_ms"])
print("cancel_median_ms =", summary["cancel_median_ms"])
print("cancel_p95_ms =", summary["cancel_p95_ms"])
print(
    "cancel_to_stock_median_ratio =",
    summary["cancel_to_stock_median_ratio"],
)
print(
    "cancel_to_stock_p95_ratio =",
    summary["cancel_to_stock_p95_ratio"],
)
print("claim_boundary =", summary["claim_boundary"])
PY

echo "outputs: $out"
