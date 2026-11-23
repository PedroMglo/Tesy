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
stock_source="$root/.deps/llama.cpp"
patched_source="$root/build/tesy-llama-split-src"
patch="$root/patches/llama-cpp-4e416ee73-tesy-split-graph-hook.patch"
stock_build="$root/build/tesy-mixed-residency"
patched_build="$root/build/tesy-split-patched-gcc15"
stock_tool="$stock_build/tesy-mixed-residency"
patched_tool="$patched_build/tesy-mixed-residency"
prompt="$root/benchmarks/prompts/b0-b1-diagnostic.txt"
lock_file="${XDG_RUNTIME_DIR:-/tmp}/tesy-live-moe-split-graph-skip.lock"
stage="initialization"
arm="none"
active_pid=""
monitor_pid=""
active_stopped=0

[[ ! -e "$out" ]] || {
  echo "refusing to replace campaign root: $out" >&2
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
    "$python_bin" - "$out/failure.json" "$stage" "$arm" "$rc" <<'PY' || true
import json
import sys
from pathlib import Path

with Path(sys.argv[1]).open("x", encoding="utf-8") as handle:
    json.dump({
        "schema": "tesy.live_moe_split_graph_skip_failure.v1",
        "classification": "FAIL_CAMPAIGN_STAGE",
        "stage": sys.argv[2],
        "arm": sys.argv[3],
        "exit_code": int(sys.argv[4]),
        "claim_boundary": "Failure evidence only; no correctness GO follows.",
    }, handle, indent=2, sort_keys=True)
    handle.write("\n")
PY
  fi
}
trap cleanup EXIT

exec 9>"$lock_file"
flock -n 9 || { echo "another split-graph campaign holds the lock" >&2; exit 1; }

stage="source_and_inputs"
[[ -x "$python_bin" && -x "$stock_tool" && -x "$patched_tool" ]]
[[ -f "$model" && -f "$prompt" && -f "$patch" ]]
[[ -z "$(git -C "$root" status --porcelain)" ]]
[[ -z "$(git -C "$stock_source" status --porcelain)" ]]
[[ "$(git -C "$stock_source" rev-parse HEAD)" == \
  "4e416ee7308dd6b581796f1a6241276cd5982691" ]]
[[ "$(git -C "$patched_source" rev-parse HEAD)" == \
  "4e416ee7308dd6b581796f1a6241276cd5982691" ]]
[[ "$(sha256sum "$prompt" | awk '{print $1}')" == \
  "431498aa6a73a4e817c5ef58ceabdac5b8336dd95e01a17903e75bc1d27d10c6" ]]
[[ "$(stat -c %s "$model")" == "12109564352" ]]
[[ "$(sha256sum "$model" | awk '{print $1}')" == \
  "52f57ab7d3df3ba9173827c1c6832e73375553a846f3e32b49f1ae2daad688d4" ]]
"$python_bin" -m tesy models verify gpt-oss-20b-mxfp4-gguf "$model" \
  >"$out/model.json"

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
"$python_bin" - "$root" "$out" "$stock_source" "$patched_source" \
  "$patch" "$stock_build" "$patched_build" <<'PY'
import hashlib
import json
import subprocess
import sys
from pathlib import Path

root, out, stock, patched, patch, stock_build, patched_build = map(Path, sys.argv[1:])

def sha(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

def git(path, *args):
    return subprocess.check_output(["git", "-C", str(path), *args]).strip().decode()

patch_bytes = patch.read_bytes()
observed_diff = subprocess.check_output(
    ["git", "-C", str(patched), "diff", "--binary"])
assert observed_diff == patch_bytes, "patched source differs from recorded patch"
assert git(stock, "rev-parse", "HEAD") == git(patched, "rev-parse", "HEAD")
assert git(stock, "rev-parse", "HEAD^{tree}") == git(patched, "rev-parse", "HEAD^{tree}")
assert git(patched, "ls-files", "--others", "--exclude-standard") == ""
stock_tool = stock_build / "tesy-mixed-residency"
patched_tool = patched_build / "tesy-mixed-residency"
assert sha(root / "native/tesy_mixed_residency.cpp")
assert sha(root / "native/CMakeLists.txt")
assert sha(stock_build / "bin/libllama.so") != sha(patched_build / "bin/libllama.so")
manifest = {
    "schema": "tesy.live_moe_split_graph_build_provenance.v1",
    "status": "PASS",
    "tesy_head": git(root, "rev-parse", "HEAD"),
    "tesy_tree": git(root, "rev-parse", "HEAD^{tree}"),
    "upstream_llama_head": git(patched, "rev-parse", "HEAD"),
    "stock_llama_head": git(stock, "rev-parse", "HEAD"),
    "stock_llama_tree": git(stock, "rev-parse", "HEAD^{tree}"),
    "patch_path": str(patch.resolve()),
    "patch_sha256": hashlib.sha256(patch_bytes).hexdigest(),
    "patched_context_cpp_sha256": sha(patched / "src/llama-context.cpp"),
    "patched_context_h_sha256": sha(patched / "src/llama-context.h"),
    "native_source_sha256": sha(root / "native/tesy_mixed_residency.cpp"),
    "cmake_lists_sha256": sha(root / "native/CMakeLists.txt"),
    "stock_binary_path": str(stock_tool.resolve()),
    "stock_binary_sha256": sha(stock_tool),
    "patched_binary_path": str(patched_tool.resolve()),
    "patched_binary_sha256": sha(patched_tool),
    "stock_libllama_sha256": sha(stock_build / "bin/libllama.so"),
    "patched_libllama_sha256": sha(patched_build / "bin/libllama.so"),
    "stock_libggml_cpu_sha256": sha(stock_build / "bin/libggml-cpu.so"),
    "patched_libggml_cpu_sha256": sha(patched_build / "bin/libggml-cpu.so"),
    "stock_libggml_cuda_sha256": sha(stock_build / "bin/libggml-cuda.so"),
    "patched_libggml_cuda_sha256": sha(patched_build / "bin/libggml-cuda.so"),
    "compiler_c": "/usr/bin/gcc-15",
    "compiler_cxx": "/usr/bin/g++-15",
    "cuda_compiler": "/usr/local/cuda/bin/nvcc",
    "cuda_architectures": "89",
    "model_sha256": "52f57ab7d3df3ba9173827c1c6832e73375553a846f3e32b49f1ae2daad688d4",
    "model_size_bytes": 12109564352,
    "prompt_sha256": "431498aa6a73a4e817c5ef58ceabdac5b8336dd95e01a17903e75bc1d27d10c6",
}
with (out / "build-provenance.json").open("x", encoding="utf-8") as handle:
    json.dump(manifest, handle, indent=2, sort_keys=True)
    handle.write("\n")
PY

for arm in stock null segmented skip-stock h2 h3; do
  stage="launch"
  arm_dir="$out/$arm"
  mkdir -p "$arm_dir"
  if [[ "$arm" == stock ]]; then
    tool="$stock_tool"
    build_dir="$stock_build"
  else
    tool="$patched_tool"
    build_dir="$patched_build"
  fi
  cmd=("$tool" --model "$model" --output "$arm_dir/raw.json"
    --layer 0 --threads 12 --split-graph-skip-exactness
    --split-arm "$arm" --prompt-file "$prompt" --ctx 4096)
  "$python_bin" - "$arm_dir/argv.json" "${cmd[@]}" <<'PY'
import json
import sys
from pathlib import Path

Path(sys.argv[1]).write_text(json.dumps(sys.argv[2:], indent=2) + "\n")
PY
  "${cmd[@]}" >"$arm_dir/tool.stdout.txt" 2>"$arm_dir/tool.stderr.txt" &
  active_pid=$!
  "$python_bin" -m tesy.resource_monitor --pid "$active_pid" \
    --output "$arm_dir/resources.jsonl" --interval-ms 100 &
  monitor_pid=$!

  stage="runtime_provenance"
  mapped=0
  for _ in $(seq 1 4000); do
    kill -0 "$active_pid" 2>/dev/null || {
      echo "$arm exited before runtime provenance" >&2
      exit 1
    }
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
    --pid "$active_pid" --expected-executable "$tool" \
    --build-dir "$build_dir" --expected-argv "$arm_dir/argv.json" \
    --output "$arm_dir/runtime-provenance.json"
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
  [[ "$tool_rc" -eq 0 ]] || {
    echo "$arm native execution failed ($tool_rc)" >&2
    exit "$tool_rc"
  }

  stage="resource_validation"
  "$python_bin" - "$out/doctor.json" "$arm_dir/resources.jsonl" \
    "$arm_dir/resource-summary.json" <<'PY'
import json
import math
import sys
from pathlib import Path

doctor = json.loads(Path(sys.argv[1]).read_text())
rows = [json.loads(line) for line in Path(sys.argv[2]).read_text().splitlines()
        if line.strip()]
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
assert all(math.isfinite(row["power_w"]) and math.isfinite(row["temperature_c"])
           for row in gpu)
Path(sys.argv[3]).write_text(json.dumps({
    "schema": "tesy.live_moe_split_graph_resources.v1",
    "status": "PASS", "samples": len(rows), "gpu_failed_samples": 0,
    "peak_process_swap_bytes": peak_swap,
    "min_mem_available_bytes": min_mem,
    "min_observed_gpu_free_bytes": gpu_total - peak_gpu,
    "max_gpu_temperature_c": max(row["temperature_c"] for row in gpu),
    "max_gpu_power_w": max(row["power_w"] for row in gpu),
}, indent=2, sort_keys=True) + "\n")
PY
done

stage="independent_validation"
"$python_bin" -m tesy.live_moe_split_graph_skip_exactness \
  --root "$out" --output "$out/summary.json"

echo "PASS_LIVE_MOE_SPLIT_GRAPH_SKIP_EXACTNESS"
echo "outputs: $out"
