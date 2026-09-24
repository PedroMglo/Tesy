#!/usr/bin/env bash
set -Eeuo pipefail

if [[ $# -ne 2 ]]; then
  echo "usage: $0 MODEL.gguf OUTPUT_ROOT" >&2
  exit 2
fi

model="$1"
out="$2"
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source_dir="${TESY_LLAMA_CPP_DIR:-$root/.deps/llama.cpp}"
build_dir="${TESY_CROSSOVER_BUILD_DIR:-$root/build/tesy-crossover}"
tool="$build_dir/tesy-expert-crossover"
lock_file="${XDG_RUNTIME_DIR:-/tmp}/tesy-expert-crossover.lock"
stage="initialization"
tool_pid=""
monitor_pid=""

if [[ -e "$out" ]]; then
  echo "refusing to replace output root: $out" >&2
  exit 1
fi
mkdir -p "$out"

cleanup() {
  if [[ -n "$tool_pid" ]] && kill -0 "$tool_pid" 2>/dev/null; then
    kill "$tool_pid" 2>/dev/null || true
    wait "$tool_pid" 2>/dev/null || true
  fi
  if [[ -n "$monitor_pid" ]] && kill -0 "$monitor_pid" 2>/dev/null; then
    wait "$monitor_pid" 2>/dev/null || true
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
    "schema": "tesy.expert_crossover_failure.v1",
    "classification": "FAIL_CAMPAIGN_STAGE",
    "stage": sys.argv[2],
    "exit_code": int(sys.argv[3]),
    "line": int(sys.argv[4]),
    "failed_command": sys.argv[5],
    "claim_boundary": (
        "Execution failure provenance only. No crossover conclusion follows "
        "beyond the failed gate."
    ),
}
try:
    with path.open("x", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
except FileExistsError:
    pass
PY
  echo "FAIL_EXPERT_CROSSOVER stage=$stage line=$line exit=$rc" >&2
  exit "$rc"
}
trap 'rc=$?; cmd=$BASH_COMMAND; line=$LINENO; failure_report "$rc" "$cmd" "$line"' ERR

exec 9>"$lock_file"
if ! flock -n 9; then
  echo "another expert crossover campaign holds $lock_file" >&2
  exit 1
fi

stage="worktree_provenance"
git -C "$root" rev-parse HEAD >"$out/tesy-head.txt"
git -C "$root" status --porcelain=v1 >"$out/tesy-status.txt"
git -C "$source_dir" rev-parse HEAD >"$out/llama-head.txt"
git -C "$source_dir" status --porcelain=v1 >"$out/llama-status.txt"
[[ ! -s "$out/tesy-status.txt" ]] || { echo "Tesy worktree must be clean" >&2; exit 1; }
[[ ! -s "$out/llama-status.txt" ]] || { echo "llama.cpp worktree must be clean" >&2; exit 1; }

stage="model_verify"
python3 -m tesy models verify \
  gpt-oss-20b-mxfp4-gguf "$model" >"$out/model.json"

stage="reference_host"
python3 -m tesy doctor \
  --disk-path "$(dirname "$model")" \
  --reference-profile "$root/configs/reference-host.json" >"$out/doctor.json"

python3 - "$out/doctor.json" <<'PY'
import json
import sys
from pathlib import Path
p = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
if p.get("reference_check", {}).get("status") != "PASS":
    raise SystemExit("reference host identity did not PASS")
apps = p.get("snapshot", {}).get("gpu_compute_processes", {})
if apps.get("status") != "OK":
    raise SystemExit("GPU compute-process probe failed")
if apps.get("stdout", "").strip():
    raise SystemExit("competing GPU compute process detected")
PY

stage="build_identity"
[[ -x "$tool" ]] || {
  echo "missing prebuilt crossover tool: $tool" >&2
  echo "run scripts/bootstrap_expert_crossover.sh first" >&2
  exit 1
}
[[ -f "$build_dir/CMakeCache.txt" ]] || { echo "missing CMake cache" >&2; exit 1; }

python3 - "$build_dir/CMakeCache.txt" >"$out/build-cache-summary.json" <<'PY'
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
    "schema": "tesy.expert_crossover_build_cache.v1",
    "status": "PASS" if not mismatches else "FAIL",
    "selected": {key: cache.get(key) for key in expected},
    "mismatches": mismatches,
}, indent=2, sort_keys=True))
if mismatches:
    raise SystemExit(f"crossover build cache mismatch: {mismatches}")
PY

sha256sum "$tool" >"$out/tool-sha256.txt"
ldd "$tool" >"$out/tool-ldd.txt"

cuda_backend="$(
  python3 - "$build_dir" <<'PY'
import sys
from pathlib import Path
root = Path(sys.argv[1]).resolve(strict=True)
paths = {p.resolve(strict=True) for p in root.rglob("libggml-cuda.so*") if p.is_file()}
if len(paths) != 1:
    raise SystemExit(f"expected exactly one libggml-cuda.so, got {sorted(map(str, paths))}")
print(next(iter(paths)))
PY
)"
printf '%s\n' "$cuda_backend" >"$out/ggml-cuda-path.txt"
sha256sum "$cuda_backend" >"$out/ggml-cuda-sha256.txt"

stage="pre_run_resources"
python3 - "$out/pre-run.json" <<'PY'
import json
import subprocess
import sys
from pathlib import Path
gpu = subprocess.run(
    [
        "nvidia-smi",
        "--query-gpu=name,pci.bus_id,driver_version,memory.total,memory.free,temperature.gpu,pstate,power.draw",
        "--format=csv,noheader,nounits",
    ],
    capture_output=True, text=True, check=True,
)
rows = [line.strip() for line in gpu.stdout.splitlines() if line.strip()]
if len(rows) != 1:
    raise SystemExit(f"expected exactly one GPU row, got {len(rows)}")
parts = [item.strip() for item in rows[0].split(",")]
if len(parts) != 8:
    raise SystemExit(f"unexpected GPU row: {rows[0]!r}")
name, bus, driver, total, free, temp, pstate, power = parts
mem = {}
for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
    if ":" not in line:
        continue
    key, raw = line.split(":", 1)
    if key in {"MemAvailable", "SwapFree", "SwapTotal"}:
        mem[key] = int(raw.strip().split()[0]) * 1024
payload = {
    "schema": "tesy.expert_crossover_pre_run.v1",
    "classification": "MEASURED_PRE_RUN_RESOURCES",
    "gpu": {
        "name": name,
        "pci_bus_id": bus,
        "driver_version": driver,
        "memory_total_bytes": int(float(total) * 1024 * 1024),
        "memory_free_bytes": int(float(free) * 1024 * 1024),
        "temperature_c": float(temp),
        "pstate": pstate,
        "power_w": float(power),
    },
    "memory": {
        "available_bytes": mem["MemAvailable"],
        "swap_free_bytes": mem["SwapFree"],
        "swap_total_bytes": mem["SwapTotal"],
    },
}
Path(sys.argv[1]).write_text(
    json.dumps(payload, indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
)
PY

stage="launch"
cmd=(
  "$tool"
  --model "$model"
  --output "$out/raw.json"
  --layer 0
  --threads 12
  --samples 21
  --warmup 3
  --compute-inner 5
  --transfer-inner 4
  --activation-inner 100
)

python3 - "$out/argv.json" "${cmd[@]}" <<'PY'
import json
import sys
from pathlib import Path
argv = sys.argv[2:]
if not argv or any(not item for item in argv):
    raise SystemExit("invalid crossover argv")
Path(sys.argv[1]).write_text(json.dumps(argv, indent=2) + "\n", encoding="utf-8")
PY

"${cmd[@]}" >"$out/tool.stdout.txt" 2>"$out/tool.stderr.txt" &
tool_pid=$!

python3 -m tesy.resource_monitor \
  --pid "$tool_pid" \
  --output "$out/resources.jsonl" \
  --interval-ms 100 &
monitor_pid=$!

stage="live_provenance"
provenance_pass=0
for _ in $(seq 1 1000); do
  if ! kill -0 "$tool_pid" 2>/dev/null; then
    echo "crossover tool exited before live provenance PASS" >&2
    wait "$tool_pid" || true
    exit 1
  fi
  if grep -F "libggml-cuda.so" "/proc/$tool_pid/maps" >/dev/null 2>&1; then
    python3 -m tesy.crossover_provenance \
      --pid "$tool_pid" \
      --expected-executable "$tool" \
      --build-dir "$build_dir" \
      --expected-argv "$out/argv.json" \
      --output "$out/runtime-provenance.json"
    provenance_pass=1
    break
  fi
  sleep 0.01
done
[[ "$provenance_pass" -eq 1 ]] || {
  echo "timed out waiting for mapped ggml-cuda backend" >&2
  exit 1
}

stage="benchmark_completion"
set +e
wait "$tool_pid"
tool_rc=$?
set -e
tool_pid=""

wait "$monitor_pid" || { echo "resource monitor failed" >&2; exit 1; }
monitor_pid=""

[[ "$tool_rc" -eq 0 ]] || {
  echo "crossover tool failed with exit $tool_rc" >&2
  failure_report "$tool_rc" "tesy-expert-crossover" "$LINENO"
}
[[ -f "$out/raw.json" ]] || { echo "crossover raw result missing" >&2; exit 1; }

stage="measurement_validation"
python3 -m tesy.expert_crossover \
  --input "$out/raw.json" \
  --output "$out/summary.json"

python3 - "$out/resources.jsonl" "$out/pre-run.json" >"$out/resource-summary.json" <<'PY'
import json
import sys
from pathlib import Path
rows = [
    json.loads(line)
    for line in Path(sys.argv[1]).read_text(encoding="utf-8").splitlines()
    if line.strip()
]
pre = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
if not rows:
    raise SystemExit("no resource samples")
gpu = [row["gpu"] for row in rows if row.get("gpu", {}).get("status") == "OK"]
if len(gpu) != len(rows):
    raise SystemExit(f"GPU telemetry incomplete: {len(gpu)} valid of {len(rows)}")
proc = [row.get("process", {}) for row in rows]
system = [row.get("system", {}) for row in rows]
peak_gpu = max(row["memory_used_bytes"] for row in gpu)
gpu_total = pre["gpu"]["memory_total_bytes"]
summary = {
    "schema": "tesy.expert_crossover_resources.v1",
    "classification": "MEASURED_RUNTIME_RESOURCES",
    "samples": len(rows),
    "gpu_valid_samples": len(gpu),
    "gpu_failed_samples": 0,
    "peak_gpu_memory_used_bytes": peak_gpu,
    "min_observed_gpu_free_bytes": gpu_total - peak_gpu,
    "max_gpu_temperature_c": max(row["temperature_c"] for row in gpu),
    "max_gpu_power_w": max(row["power_w"] for row in gpu),
    "peak_process_rss_bytes": max((row.get("VmRSS_bytes", 0) for row in proc), default=0),
    "peak_process_swap_bytes": max((row.get("VmSwap_bytes", 0) for row in proc), default=0),
    "min_mem_available_bytes": min(
        row.get("MemAvailable_bytes", 2**63 - 1) for row in system
    ),
    "min_swap_free_bytes": min(
        row.get("SwapFree_bytes", 2**63 - 1) for row in system
    ),
    "claim_boundary": (
        "Sampled runtime resources for the crossover microbenchmark; not "
        "physical DRAM or PCIe traffic."
    ),
}
print(json.dumps(summary, indent=2, sort_keys=True))
if summary["peak_process_swap_bytes"] != 0:
    raise SystemExit("crossover process used swap")
if summary["min_observed_gpu_free_bytes"] < 1024 * 1024 * 1024:
    raise SystemExit("crossover violated 1024 MiB GPU headroom")
if summary["min_mem_available_bytes"] < 2 * 1024 * 1024 * 1024:
    raise SystemExit("crossover violated 2048 MiB host headroom")
PY

stage="post_run"
nvidia-smi \
  --query-gpu=name,pci.bus_id,driver_version,memory.total,memory.free,temperature.gpu,pstate,power.draw \
  --format=csv,noheader,nounits >"$out/gpu-post.txt"

python3 - "$out/summary.json" <<'PY'
import json
import sys
from pathlib import Path
p = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
if p.get("status") != "PASS":
    raise SystemExit("expert crossover summary did not PASS")
print("PASS_EXPERT_CROSSOVER")
for row in p["results"]:
    m = row["median_ms"]
    print(
        f"k={row['k']} "
        f"requested_weight_bytes={row['requested_weight_bytes']} "
        f"cpu_path_ms={m['cpu_path']:.6f} "
        f"cold_gpu_pageable_ms={m['cold_gpu_pageable']:.6f} "
        f"cold_gpu_pinned_ms={m['cold_gpu_pinned']} "
        f"resident_gpu_ms={m['resident_gpu']:.6f}"
    )
PY

echo "outputs: $out"
