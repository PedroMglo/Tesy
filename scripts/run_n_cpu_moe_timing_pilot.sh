#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 2 ]]; then
  echo "usage: $0 MODEL.gguf OUTPUT_ROOT" >&2
  exit 2
fi

model="$1"
out="$2"
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source_dir="${TESY_LLAMA_CPP_DIR:-$root/.deps/llama.cpp}"
build_dir="${TESY_LLAMA_BUILD_DIR:-$source_dir/build}"
cli="${TESY_LLAMA_CLI:-$build_dir/bin/llama-cli}"
server="${TESY_LLAMA_SERVER:-$build_dir/bin/llama-server}"
fit_tool="${TESY_LLAMA_FIT_PARAMS:-$build_dir/bin/llama-fit-params}"
toolchain_lock="$root/configs/reference-llama-toolchain.json"
prompt_file="$root/benchmarks/prompts/b0-b1-diagnostic.txt"
lock_file="${XDG_RUNTIME_DIR:-/tmp}/tesy-placement-timing-pilot.lock"
base_port="${TESY_PILOT_PORT_BASE:-18220}"
gpu_target_mib=1024
host_guard_mib=2048
rounding_guard_mib=16
placements=("auto-fit-frozen" "n-cpu-moe-12" "n-cpu-moe-24")

if [[ -e "$out" ]]; then
  echo "refusing to replace output root: $out" >&2
  exit 1
fi
mkdir -p "$out/capacity" "$out/runs"

current_stage="initialization"
server_pid=""
monitor_pid=""

cleanup() {
  if [[ -n "$server_pid" ]] && kill -0 "$server_pid" 2>/dev/null; then
    kill "$server_pid" 2>/dev/null || true
    wait "$server_pid" 2>/dev/null || true
  fi
  if [[ -n "$monitor_pid" ]] && kill -0 "$monitor_pid" 2>/dev/null; then
    wait "$monitor_pid" 2>/dev/null || true
  fi
}
trap cleanup EXIT

failure_report() {
  local rc="$1"
  local failed_command="$2"
  local failed_line="$3"
  trap - ERR
  python3 - "$out/failure.json" "$current_stage" "$rc" "$failed_line" "$failed_command" <<'PY' || true
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
payload = {
    "schema": "tesy.timing_pilot_failure.v1",
    "classification": "FAIL_CAMPAIGN_STAGE",
    "stage": sys.argv[2],
    "exit_code": int(sys.argv[3]),
    "line": int(sys.argv[4]),
    "failed_command": sys.argv[5],
    "claim_boundary": (
        "Execution-stage failure record only. It is not a performance or "
        "capacity conclusion beyond the failed gate."
    ),
}
try:
    with path.open("x", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
except FileExistsError:
    pass
PY
  echo "FAIL_TIMING_PILOT stage=$current_stage line=$failed_line exit=$rc" >&2
  exit "$rc"
}
trap 'rc=$?; cmd=$BASH_COMMAND; line=$LINENO; failure_report "$rc" "$cmd" "$line"' ERR

exec 9>"$lock_file"
if ! flock -n 9; then
  echo "another Tesy timing pilot holds $lock_file" >&2
  exit 1
fi

current_stage="model_verify"
python3 -m tesy models verify gpt-oss-20b-mxfp4-gguf "$model" >"$out/model.json"

current_stage="host_doctor"
python3 -m tesy doctor \
  --disk-path "$(dirname "$model")" \
  --reference-profile "$root/configs/reference-host.json" >"$out/doctor.json"

for binary in "$cli" "$server" "$fit_tool"; do
  [[ -x "$binary" ]] || { echo "missing required binary: $binary" >&2; exit 1; }
done

current_stage="backend_probe"
python3 -m tesy backend probe \
  --binary "$cli" \
  --source-dir "$source_dir" >"$out/backend.json"

current_stage="build_provenance"
python3 -m tesy.build_provenance \
  --build-dir "$build_dir" \
  --server "$server" \
  --fit-tool "$fit_tool" \
  --reference "$toolchain_lock" >"$out/build-provenance.json"

current_stage="cli_surface_validation"
server_help="$("$server" --help 2>&1)"
for flag in --n-cpu-moe --fit --n-gpu-layers --host --port --no-warmup; do
  grep -F -- "$flag" <<<"$server_help" >/dev/null || {
    echo "llama-server missing required flag: $flag" >&2
    exit 1
  }
done
fit_help="$("$fit_tool" --help 2>&1)"
for flag in --n-cpu-moe --fit --fit-print --fit-target --n-gpu-layers; do
  grep -F -- "$flag" <<<"$fit_help" >/dev/null || {
    echo "llama-fit-params missing required flag: $flag" >&2
    exit 1
  }
done

current_stage="worktree_provenance"
git -C "$root" rev-parse HEAD >"$out/tesy-head.txt"
git -C "$root" status --porcelain=v1 >"$out/tesy-status.txt"
git -C "$source_dir" rev-parse HEAD >"$out/llama-head.txt"
git -C "$source_dir" status --porcelain=v1 >"$out/llama-status.txt"
[[ ! -s "$out/tesy-status.txt" ]] || { echo "dirty Tesy worktree" >&2; exit 1; }
[[ ! -s "$out/llama-status.txt" ]] || { echo "dirty llama.cpp worktree" >&2; exit 1; }
sha256sum "$server" >"$out/server-sha256.txt"
sha256sum "$fit_tool" >"$out/fit-tool-sha256.txt"
sha256sum "$prompt_file" >"$out/prompt-sha256.txt"

snapshot_resources() {
  local output="$1"
  python3 - "$output" <<'PY'
import json
import subprocess
import sys
from pathlib import Path

out = Path(sys.argv[1])
gpu = subprocess.run(
    [
        "nvidia-smi",
        "--query-gpu=name,memory.total,memory.free,temperature.gpu,pstate,pci.bus_id",
        "--format=csv,noheader,nounits",
    ],
    capture_output=True,
    text=True,
    check=False,
)
if gpu.returncode != 0:
    raise SystemExit(f"nvidia-smi GPU snapshot failed: {gpu.stderr.strip()}")
rows = [line.strip() for line in gpu.stdout.splitlines() if line.strip()]
if len(rows) != 1:
    raise SystemExit(f"expected exactly one GPU row, got {len(rows)}")
parts = [value.strip() for value in rows[0].split(",")]
if len(parts) != 6:
    raise SystemExit(f"unexpected GPU row: {rows[0]!r}")
name, total_mib, free_mib, temperature_c, pstate, pci_bus_id = parts

compute = subprocess.run(
    [
        "nvidia-smi",
        "--query-compute-apps=pid,process_name,used_memory",
        "--format=csv,noheader,nounits",
    ],
    capture_output=True,
    text=True,
    check=False,
)
if compute.returncode != 0:
    raise SystemExit(
        f"nvidia-smi compute-process snapshot failed: {compute.stderr.strip()}"
    )
if compute.stdout.strip():
    raise SystemExit(f"competing GPU compute process detected: {compute.stdout.strip()}")

meminfo = {}
for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
    if ":" not in line:
        continue
    key, raw = line.split(":", 1)
    fields = raw.strip().split()
    if key in {"MemAvailable", "SwapFree", "SwapTotal"} and fields:
        meminfo[key] = int(fields[0]) * 1024
for key in ("MemAvailable", "SwapFree", "SwapTotal"):
    if key not in meminfo:
        raise SystemExit(f"missing /proc/meminfo field: {key}")

payload = {
    "schema": "tesy.timing_pilot_resource_snapshot.v1",
    "classification": "MEASURED_PRE_RUN_RESOURCES",
    "gpu": {
        "name": name,
        "memory_total_bytes": int(float(total_mib) * 1024 * 1024),
        "memory_free_bytes": int(float(free_mib) * 1024 * 1024),
        "temperature_c": float(temperature_c),
        "pstate": pstate,
        "pci_bus_id": pci_bus_id,
    },
    "memory": {
        "available_bytes": meminfo["MemAvailable"],
        "swap_free_bytes": meminfo["SwapFree"],
        "swap_total_bytes": meminfo["SwapTotal"],
    },
    "claim_boundary": (
        "Measured immediately before one pilot placement. It qualifies admission "
        "inputs and process isolation only, not subsequent performance."
    ),
}
with out.open("x", encoding="utf-8") as handle:
    json.dump(payload, handle, indent=2, sort_keys=True)
    handle.write("\n")
PY
}

current_stage="freeze_auto_fit"
"$fit_tool" \
  --model "$model" \
  --ctx-size 4096 \
  --fit on \
  --fit-target "$gpu_target_mib" \
  >"$out/auto-fit.stdout.txt" \
  2>"$out/auto-fit.stderr.txt"

current_stage="parse_auto_fit"
python3 -m tesy.placement_capacity parse-fitted-cli \
  --input "$out/auto-fit.stdout.txt" \
  --expected-ctx 4096 \
  --output "$out/auto-fit.json"

mapfile -d '' -t auto_fit_args < <(
  python3 - "$out/auto-fit.json" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
argv = payload.get("argv")
if not isinstance(argv, list) or not argv:
    raise SystemExit("invalid frozen auto-fit argv")
for value in argv:
    if not isinstance(value, str) or not value:
        raise SystemExit("invalid frozen auto-fit argument")
    sys.stdout.write(value)
    sys.stdout.write("\0")
PY
)

capacity_estimate() {
  local placement="$1"
  local snapshot="$2"
  local stdout_path="$3"
  local stderr_path="$4"
  local json_path="$5"

  if [[ "$placement" == "auto-fit-frozen" ]]; then
    "$fit_tool" \
      --model "$model" \
      "${auto_fit_args[@]}" \
      --fit off \
      --fit-print on \
      >"$stdout_path" \
      2>"$stderr_path"
  else
    local n="${placement#n-cpu-moe-}"
    "$fit_tool" \
      --model "$model" \
      --ctx-size 4096 \
      --gpu-layers all \
      --n-cpu-moe "$n" \
      --fit off \
      --fit-print on \
      >"$stdout_path" \
      2>"$stderr_path"
  fi

  read -r gpu_free_bytes mem_available_bytes < <(
    python3 - "$snapshot" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
print(
    payload["gpu"]["memory_free_bytes"],
    payload["memory"]["available_bytes"],
)
PY
  )

  python3 -m tesy.placement_capacity evaluate-placement-fit-print \
    --input "$stdout_path" \
    --gpu-free-bytes "$gpu_free_bytes" \
    --mem-available-bytes "$mem_available_bytes" \
    --placement-id "$placement" \
    --gpu-target-mib "$gpu_target_mib" \
    --host-guard-mib "$host_guard_mib" \
    --rounding-guard-mib "$rounding_guard_mib" \
    --output "$json_path"

  python3 - "$json_path" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
if not payload["admitted"]:
    raise SystemExit(
        f"placement rejected by fresh capacity gate: "
        f"{payload['placement_id']} {payload['rejection_reasons']}"
    )
PY
}

reference_token_sha=""

for index in "${!placements[@]}"; do
  placement="${placements[$index]}"
  run_number=$((index + 1))
  port=$((base_port + index))
  run_dir="$(printf '%s/runs/%02d-%s' "$out" "$run_number" "$placement")"
  mkdir -p "$run_dir"

  current_stage="preflight_${placement}"
  snapshot_resources "$run_dir/pre-run-resources.json"

  current_stage="capacity_${placement}"
  capacity_estimate \
    "$placement" \
    "$run_dir/pre-run-resources.json" \
    "$out/capacity/${placement}.stdout.txt" \
    "$out/capacity/${placement}.stderr.txt" \
    "$out/capacity/${placement}.json"

  python3 - "$placement" >"$run_dir/run-metadata.json" <<'PY'
import json
import sys

placement = sys.argv[1]
n = None if placement == "auto-fit-frozen" else int(placement.rsplit("-", 1)[1])
print(json.dumps({
    "schema": "tesy.stock_placement_pilot_run.v1",
    "placement_id": placement,
    "n_cpu_moe": n,
    "observation_index": 1,
}, indent=2, sort_keys=True))
PY

  cmd=(
    "$server"
    --model "$model"
    --host 127.0.0.1
    --port "$port"
    --parallel 1
    --threads 12
    --threads-batch 12
    --fit off
    --no-warmup
  )
  if [[ "$placement" == "auto-fit-frozen" ]]; then
    cmd+=("${auto_fit_args[@]}")
  else
    n="${placement#n-cpu-moe-}"
    cmd+=(
      --ctx-size 4096
      --gpu-layers all
      --n-cpu-moe "$n"
    )
  fi

  {
    printf '%q' "${cmd[0]}"
    for arg in "${cmd[@]:1}"; do
      printf ' %q' "$arg"
    done
    printf '\n'
  } >"$run_dir/server-command.txt"

  current_stage="server_start_${placement}"
  ready_start_ns="$(date +%s%N)"
  "${cmd[@]}" >"$run_dir/server.stdout.txt" 2>"$run_dir/server.stderr.txt" &
  server_pid=$!

  python3 -m tesy.resource_monitor \
    --pid "$server_pid" \
    --output "$run_dir/resources.jsonl" \
    --interval-ms 200 &
  monitor_pid=$!

  ready=0
  for _ in $(seq 1 1800); do
    if ! kill -0 "$server_pid" 2>/dev/null; then
      echo "server exited before health PASS for $placement" >&2
      wait "$server_pid" || true
      exit 1
    fi
    if curl -fsS "http://127.0.0.1:$port/health" >"$run_dir/health.json" 2>/dev/null; then
      ready=1
      break
    fi
    sleep 0.1
  done
  [[ "$ready" -eq 1 ]] || {
    echo "server health timeout for $placement" >&2
    exit 1
  }

  current_stage="runtime_provenance_${placement}"
  python3 -m tesy.runtime_provenance \
    --pid "$server_pid" \
    --build-provenance "$out/build-provenance.json" \
    >"$run_dir/runtime-provenance.json"

  if grep -F 'failed to fit params to free device memory' "$run_dir/server.stderr.txt" >/dev/null; then
    echo "unexpected fit path executed for frozen placement $placement" >&2
    exit 1
  fi

  ready_end_ns="$(date +%s%N)"
  python3 - "$ready_start_ns" "$ready_end_ns" "$placement" \
    >"$run_dir/server-ready.json" <<'PY'
import json
import sys

start, end = int(sys.argv[1]), int(sys.argv[2])
print(json.dumps({
    "schema": "tesy.stock_server_ready.v1",
    "placement_id": sys.argv[3],
    "server_ready_ms": (end - start) / 1e6,
}, indent=2, sort_keys=True))
PY

  current_stage="request_${placement}"
  python3 -m tesy.server_client \
    --url "http://127.0.0.1:$port/completion" \
    --prompt-file "$prompt_file" \
    --n-predict 64 \
    --output "$run_dir/request.json"

  token_sha="$(
    python3 - "$run_dir/request.json" <<'PY'
import hashlib
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
tokens = payload.get("generated_token_ids")
if not isinstance(tokens, list) or len(tokens) != 64:
    raise SystemExit(
        f"expected exactly 64 generated token IDs, got "
        f"{len(tokens) if isinstance(tokens, list) else 'invalid'}"
    )
blob = json.dumps(tokens, separators=(",", ":")).encode()
print(hashlib.sha256(blob).hexdigest())
PY
  )"
  printf '%s\n' "$token_sha" >"$run_dir/token-sha256.txt"
  if [[ -z "$reference_token_sha" ]]; then
    reference_token_sha="$token_sha"
  elif [[ "$token_sha" != "$reference_token_sha" ]]; then
    echo "FAIL_TRAJECTORY_COMPARABILITY at $placement" >&2
    exit 1
  fi

  current_stage="shutdown_${placement}"
  kill "$server_pid"
  wait "$server_pid" || true
  server_pid=""
  wait "$monitor_pid" || true
  monitor_pid=""

  current_stage="resource_summary_${placement}"
  python3 - \
    "$run_dir/resources.jsonl" \
    "$run_dir/pre-run-resources.json" \
    "$gpu_target_mib" \
    "$host_guard_mib" \
    >"$run_dir/resource-summary.json" <<'PY'
import json
import sys
from pathlib import Path

rows = [
    json.loads(line)
    for line in Path(sys.argv[1]).read_text(encoding="utf-8").splitlines()
    if line.strip()
]
pre = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
gpu_target_bytes = int(sys.argv[3]) * 1024 * 1024
host_guard_bytes = int(sys.argv[4]) * 1024 * 1024
gpu_total_bytes = pre["gpu"]["memory_total_bytes"]

if not rows:
    raise SystemExit("no resource samples")

gpu = [row["gpu"] for row in rows if row.get("gpu", {}).get("status") == "OK"]
if len(gpu) != len(rows):
    raise SystemExit(
        f"GPU telemetry incomplete: {len(gpu)} valid of {len(rows)} samples"
    )
proc = [row.get("process", {}) for row in rows]
system = [row.get("system", {}) for row in rows]

peak_gpu = max(row["memory_used_bytes"] for row in gpu)
if peak_gpu > gpu_total_bytes:
    raise SystemExit("observed GPU usage exceeds recorded total memory")

summary = {
    "schema": "tesy.stock_placement_pilot_resources.v1",
    "classification": "MEASURED_RUNTIME_RESOURCES",
    "samples": len(rows),
    "gpu_valid_samples": len(gpu),
    "gpu_failed_samples": 0,
    "peak_gpu_memory_used_bytes": peak_gpu,
    "min_observed_gpu_free_bytes": gpu_total_bytes - peak_gpu,
    "max_gpu_temperature_c": max(row["temperature_c"] for row in gpu),
    "max_gpu_power_w": max(row["power_w"] for row in gpu),
    "peak_process_rss_bytes": max(
        (row.get("VmRSS_bytes", 0) for row in proc),
        default=0,
    ),
    "peak_process_swap_bytes": max(
        (row.get("VmSwap_bytes", 0) for row in proc),
        default=0,
    ),
    "min_mem_available_bytes": min(
        row.get("MemAvailable_bytes", 2**63 - 1) for row in system
    ),
    "min_swap_free_bytes": min(
        row.get("SwapFree_bytes", 2**63 - 1) for row in system
    ),
    "claim_boundary": (
        "Runtime RSS/swap and sampled whole-GPU memory/temperature/power for one "
        "pilot observation. These are not physical PCIe, DRAM or NVMe byte counts."
    ),
}
print(json.dumps(summary, indent=2, sort_keys=True))

if summary["peak_process_swap_bytes"] != 0:
    raise SystemExit("server process used swap")
if summary["min_observed_gpu_free_bytes"] < gpu_target_bytes:
    raise SystemExit("measured GPU free-memory target violated")
if summary["min_mem_available_bytes"] < host_guard_bytes:
    raise SystemExit("measured host-memory guard violated")
PY

  grep -Ei 'tensor overrides|offload|model buffer|compute buffer|CPU_Mapped|CUDA[0-9]' \
    "$run_dir/server.stderr.txt" >"$run_dir/placement.txt" || true
  [[ -s "$run_dir/placement.txt" ]] || {
    echo "missing required placement telemetry for $placement" >&2
    exit 1
  }
done

current_stage="pilot_summary"
python3 - "$out" >"$out/pilot-summary.json" <<'PY'
from __future__ import annotations

import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
expected = ["auto-fit-frozen", "n-cpu-moe-12", "n-cpu-moe-24"]
rows = []
token_hashes = set()

for run_dir in sorted((root / "runs").iterdir()):
    if not run_dir.is_dir():
        continue
    meta = json.loads((run_dir / "run-metadata.json").read_text(encoding="utf-8"))
    req = json.loads((run_dir / "request.json").read_text(encoding="utf-8"))
    res = json.loads((run_dir / "resource-summary.json").read_text(encoding="utf-8"))
    ready = json.loads((run_dir / "server-ready.json").read_text(encoding="utf-8"))
    cap = json.loads(
        (root / "capacity" / f"{meta['placement_id']}.json").read_text(
            encoding="utf-8"
        )
    )
    runtime = json.loads(
        (run_dir / "runtime-provenance.json").read_text(encoding="utf-8")
    )
    token_hash = (run_dir / "token-sha256.txt").read_text(encoding="utf-8").strip()

    if runtime.get("status") != "PASS":
        raise SystemExit(f"runtime provenance failed for {meta['placement_id']}")
    if not cap.get("admitted"):
        raise SystemExit(f"capacity admission failed for {meta['placement_id']}")
    if req.get("generated_token_count") != 64:
        raise SystemExit(f"invalid token count for {meta['placement_id']}")

    token_hashes.add(token_hash)
    timings = req["timings"]
    rows.append({
        "placement_id": meta["placement_id"],
        "n_cpu_moe": meta["n_cpu_moe"],
        "observation_count": 1,
        "ttft_ms": req["ttft_ms"],
        "request_wall_ms": req["request_wall_ms"],
        "prompt_tps": timings["prompt_per_second"],
        "decode_tps": timings["predicted_per_second"],
        "server_ready_ms": ready["server_ready_ms"],
        "peak_gpu_memory_used_bytes": res["peak_gpu_memory_used_bytes"],
        "min_observed_gpu_free_bytes": res["min_observed_gpu_free_bytes"],
        "peak_process_rss_bytes": res["peak_process_rss_bytes"],
        "peak_process_swap_bytes": res["peak_process_swap_bytes"],
        "max_gpu_temperature_c": res["max_gpu_temperature_c"],
        "max_gpu_power_w": res["max_gpu_power_w"],
        "capacity_gpu_required_mib": cap["gpu_required_mib"],
        "capacity_host_required_mib": cap["host_required_mib"],
        "token_sha256": token_hash,
    })

observed = [row["placement_id"] for row in rows]
if observed != expected:
    raise SystemExit(f"pilot placement order mismatch: {observed!r}")
if len(token_hashes) != 1:
    raise SystemExit("FAIL_TRAJECTORY_COMPARABILITY")

payload = {
    "schema": "tesy.stock_placement_timing_pilot.v1",
    "classification": "MEASURED_SINGLE_OBSERVATION_PILOT_DIAGNOSTIC",
    "placements": rows,
    "trajectory_comparability": {
        "status": "PASS",
        "required_token_count": 64,
        "unique_token_trajectory_hashes": sorted(token_hashes),
    },
    "next_gate": "MANUAL_REVIEW_REQUIRED",
    "claim_boundary": (
        "Exactly one fresh-process observation per placement. This pilot can reject "
        "grossly poor placements or justify a fuller repeated campaign, but it is "
        "not a stable throughput/latency ranking and makes no Tesy speedup claim."
    ),
}
print(json.dumps(payload, indent=2, sort_keys=True))
PY

echo "PASS_STOCK_PLACEMENT_TIMING_PILOT"
echo "outputs: $out"
