#!/usr/bin/env bash
set -euo pipefail

capacity_only=0
timing_pilot=0
case "${1:-}" in
  --capacity-only)
    capacity_only=1
    shift
    ;;
  --timing-pilot)
    timing_pilot=1
    shift
    ;;
esac

if [[ $# -ne 2 ]]; then
  echo "usage: $0 [--capacity-only|--timing-pilot] MODEL.gguf OUTPUT_ROOT" >&2
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
capacity_evidence_dir="$root/research/results/n-cpu-moe-capacity-20260923T233416Z"
capacity_evidence_commit="5a8bbf08eb95069b1847f724e5d1be98c6392678"
lock_file="${XDG_RUNTIME_DIR:-/tmp}/tesy-placement-capacity-pareto.lock"
base_port="${TESY_SWEEP_PORT_BASE:-18120}"
gpu_target_mib=1024
host_guard_mib=2048
rounding_guard_mib=16
candidates=(0 4 8 12 16 20 24)
if (( timing_pilot == 1 )); then
  candidates=(12 24)
fi

if [[ -e "$out" ]]; then
  echo "refusing to replace output root: $out" >&2
  exit 1
fi
mkdir -p "$out/capacity"

failure_report() {
  local rc="$1"
  local failed_command="$2"
  local failed_line="$3"
  trap - ERR
  python3 - "$out/failure.json" "$rc" "$failed_line" "$failed_command" <<'PY' || true
import json
import sys
from pathlib import Path

out = Path(sys.argv[1])
payload = {
    "schema": "tesy.capacity_campaign_failure.v1",
    "classification": "FAIL_CAMPAIGN_COMMAND",
    "exit_code": int(sys.argv[2]),
    "line": int(sys.argv[3]),
    "failed_command": sys.argv[4],
    "claim_boundary": (
        "Execution failure provenance only. No capacity or performance conclusion follows."
    ),
}
try:
    with out.open("x", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
except FileExistsError:
    pass
PY
  echo "FAIL_CAPACITY_CAMPAIGN line=$failed_line exit=$rc" >&2
  exit "$rc"
}
trap 'rc=$?; cmd=$BASH_COMMAND; line=$LINENO; failure_report "$rc" "$cmd" "$line"' ERR

exec 9>"$lock_file"
if ! flock -n 9; then
  echo "another Tesy placement campaign holds $lock_file" >&2
  exit 1
fi

if (( timing_pilot == 1 )); then
  test -d "$capacity_evidence_dir"
  test -f "$capacity_evidence_dir/capacity-summary.json"
  test -f "$capacity_evidence_dir/auto-fit.json"
  test -f "$capacity_evidence_dir/publication-manifest.json"

  if ! git -C "$root" merge-base --is-ancestor "$capacity_evidence_commit" HEAD; then
    echo "capacity evidence commit is not an ancestor of current HEAD: $capacity_evidence_commit" >&2
    exit 1
  fi

  python3 - "$capacity_evidence_dir" "$capacity_evidence_commit" >"$out/source-capacity.json" <<'PY'
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
commit = sys.argv[2]
summary = json.loads((root / "capacity-summary.json").read_text(encoding="utf-8"))
auto = json.loads((root / "auto-fit.json").read_text(encoding="utf-8"))
manifest = json.loads((root / "publication-manifest.json").read_text(encoding="utf-8"))

if summary.get("schema") != "tesy.n_cpu_moe_capacity_gate.v1":
    raise SystemExit("invalid source capacity schema")
if summary.get("performance_gate") != "PASS":
    raise SystemExit("source capacity gate did not PASS")
if summary.get("admitted_n_cpu_moe") != [12, 16, 20, 24]:
    raise SystemExit("unexpected source admitted set")
if auto.get("schema") != "tesy.llama_fit_args.v1" or auto.get("ctx_size") != 4096:
    raise SystemExit("invalid source auto-fit placement")
if manifest.get("schema") != "tesy.n_cpu_moe_capacity_publication.v1":
    raise SystemExit("invalid source publication manifest")

print(json.dumps({
    "schema": "tesy.timing_pilot_source_capacity.v1",
    "classification": "SOURCE_BACKED_CAPACITY_EVIDENCE",
    "capacity_evidence_commit": commit,
    "admitted_n_cpu_moe": summary["admitted_n_cpu_moe"],
    "auto_fit_argv": auto["argv"],
    "claim_boundary": (
        "Published capacity evidence selecting pilot placements. "
        "Current-host admission is rechecked before timing."
    ),
}, indent=2, sort_keys=True))
PY
fi

python3 -m tesy models verify gpt-oss-20b-mxfp4-gguf "$model" >"$out/model.json"
python3 -m tesy doctor \
  --disk-path "$(dirname "$model")" \
  --reference-profile "$root/configs/reference-host.json" >"$out/doctor.json"

[[ -x "$cli" ]] || { echo "missing llama-cli: $cli" >&2; exit 1; }
[[ -x "$server" ]] || { echo "missing llama-server: $server" >&2; exit 1; }
[[ -x "$fit_tool" ]] || {
  echo "missing llama-fit-params: $fit_tool" >&2
  echo "rebuild the pinned llama.cpp targets before this campaign" >&2
  exit 1
}
python3 -m tesy backend probe \
  --binary "$cli" \
  --source-dir "$source_dir" >"$out/backend.json"

python3 -m tesy.build_provenance \
  --build-dir "$build_dir" \
  --server "$server" \
  --fit-tool "$fit_tool" \
  --reference "$toolchain_lock" >"$out/build-provenance.json"

server_help="$("$server" --help 2>&1)"
for flag in --n-cpu-moe --fit --fit-target --n-gpu-layers --host --port --no-warmup; do
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

git -C "$root" rev-parse HEAD >"$out/tesy-head.txt"
git -C "$root" status --porcelain=v1 >"$out/tesy-status.txt"
git -C "$source_dir" rev-parse HEAD >"$out/llama-head.txt"
git -C "$source_dir" status --porcelain=v1 >"$out/llama-status.txt"
[[ ! -s "$out/tesy-status.txt" ]] || { echo "dirty Tesy worktree" >&2; exit 1; }
[[ ! -s "$out/llama-status.txt" ]] || { echo "dirty llama.cpp worktree" >&2; exit 1; }

sha256sum "$server" >"$out/server-sha256.txt"
sha256sum "$fit_tool" >"$out/fit-tool-sha256.txt"
sha256sum "$prompt_file" >"$out/prompt-sha256.txt"
"$fit_tool" --version >"$out/fit-tool-version.txt" 2>&1

read -r gpu_free_bytes gpu_total_bytes mem_available_bytes < <(
  python3 - "$out/doctor.json" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
if payload["reference_check"]["status"] != "PASS":
    raise SystemExit("reference host identity did not PASS")
snapshot = payload["snapshot"]
if snapshot["gpu"]["status"] != "OK":
    raise SystemExit("GPU snapshot is not OK")
gpus = snapshot["gpu"]["gpus"]
if len(gpus) != 1:
    raise SystemExit(f"expected exactly one reference GPU, got {len(gpus)}")
compute = snapshot["gpu_compute_processes"]
if compute["status"] != "OK" or compute["stdout"].strip():
    raise SystemExit("competing GPU compute process detected")
gpu = gpus[0]
print(
    gpu["memory_free_bytes"],
    gpu["memory_total_bytes"],
    snapshot["memory"]["available_bytes"],
)
PY
)

campaign_mode="capacity-and-timing"
if (( capacity_only == 1 )); then
  campaign_mode="capacity-only"
elif (( timing_pilot == 1 )); then
  campaign_mode="timing-pilot"
fi

python3 - "$gpu_free_bytes" "$gpu_total_bytes" "$mem_available_bytes" \
  "$gpu_target_mib" "$host_guard_mib" "$rounding_guard_mib" "$campaign_mode" \
  >"$out/admission-context.json" <<'PY'
import json
import sys

gpu_free, gpu_total, mem_available, gpu_target, host_guard, rounding_guard = map(
    int, sys.argv[1:7]
)
campaign_mode = sys.argv[7]
print(json.dumps({
    "schema": "tesy.placement_admission_context.v1",
    "classification": "MEASURED_CAMPAIGN_START_RESOURCES",
    "gpu_free_bytes": gpu_free,
    "gpu_total_bytes": gpu_total,
    "mem_available_bytes": mem_available,
    "gpu_target_mib": gpu_target,
    "host_guard_mib": host_guard,
    "rounding_guard_mib": rounding_guard,
    "campaign_mode": campaign_mode,
}, indent=2, sort_keys=True))
PY

# Freeze stock auto-fit once, before timed execution. llama-fit-params is intended
# to emit reusable -c/-ngl/-ts/-ot arguments for the selected stock placement.
"$fit_tool" \
  --model "$model" \
  --ctx-size 4096 \
  --fit on \
  --fit-target "$gpu_target_mib" \
  >"$out/auto-fit.stdout.txt" \
  2>"$out/auto-fit.stderr.txt"

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

for n in "${candidates[@]}"; do
  estimate_stdout="$(printf '%s/capacity/n%02d.stdout.txt' "$out" "$n")"
  estimate_stderr="$(printf '%s/capacity/n%02d.stderr.txt' "$out" "$n")"
  estimate_json="$(printf '%s/capacity/n%02d.json' "$out" "$n")"

  "$fit_tool" \
    --model "$model" \
    --ctx-size 4096 \
    --gpu-layers all \
    --n-cpu-moe "$n" \
    --fit off \
    --fit-print on \
    >"$estimate_stdout" \
    2>"$estimate_stderr"

  python3 -m tesy.placement_capacity evaluate-fit-print \
    --input "$estimate_stdout" \
    --gpu-free-bytes "$gpu_free_bytes" \
    --mem-available-bytes "$mem_available_bytes" \
    --n-cpu-moe "$n" \
    --gpu-target-mib "$gpu_target_mib" \
    --host-guard-mib "$host_guard_mib" \
    --rounding-guard-mib "$rounding_guard_mib" \
    --output "$estimate_json"
done

python3 - "$out/capacity" >"$out/capacity-summary.json" <<'PY'
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
estimates = []
for path in sorted(root.glob("n??.json")):
    payload = json.loads(path.read_text(encoding="utf-8"))
    estimates.append(payload)

expected = [0, 4, 8, 12, 16, 20, 24]
observed = [row["n_cpu_moe"] for row in estimates]
if observed != expected:
    raise SystemExit(f"capacity estimate set mismatch: {observed!r}")

admitted = [row["n_cpu_moe"] for row in estimates if row["admitted"]]
print(json.dumps({
    "schema": "tesy.n_cpu_moe_capacity_gate.v1",
    "classification": "SOURCE_BACKED_CAPACITY_GATE",
    "candidates": expected,
    "admitted_n_cpu_moe": admitted,
    "rejected_n_cpu_moe": [
        row["n_cpu_moe"] for row in estimates if not row["admitted"]
    ],
    "estimates": estimates,
    "performance_gate": "PASS" if len(admitted) >= 2 else "NO_GO_TOO_FEW_POINTS",
    "claim_boundary": (
        "Admission uses llama-fit-params projected integer-MiB memory plus frozen "
        "headroom guards. No rejected point is deliberately loaded or OOM-probed."
    ),
}, indent=2, sort_keys=True))
PY

mapfile -t admitted < <(
  python3 - "$out/capacity-summary.json" <<'PY'
import json
import sys
from pathlib import Path
payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
for value in payload["admitted_n_cpu_moe"]:
    print(value)
PY
)

if (( capacity_only == 1 )); then
  echo "PASS_SOURCE_BACKED_N_CPU_MOE_CAPACITY_ESTIMATION"
  echo "outputs: $out"
  exit 0
fi

if (( ${#admitted[@]} < 2 )); then
  echo "NO_GO_N_CPU_MOE_CAPACITY_FRONTIER: fewer than two manual points admitted"
  echo "outputs: $out"
  exit 0
fi

order=("auto")
for n in "${admitted[@]}"; do
  order+=("n$n")
done
for ((i=${#admitted[@]} - 1; i>=0; i--)); do
  order+=("n${admitted[$i]}")
done
order+=("auto")

cleanup() {
  if [[ -n "${server_pid:-}" ]] && kill -0 "$server_pid" 2>/dev/null; then
    kill "$server_pid" 2>/dev/null || true
    wait "$server_pid" 2>/dev/null || true
  fi
  if [[ -n "${monitor_pid:-}" ]] && kill -0 "$monitor_pid" 2>/dev/null; then
    wait "$monitor_pid" 2>/dev/null || true
  fi
}
trap cleanup EXIT

reference_token_sha=""

for index in "${!order[@]}"; do
  point="${order[$index]}"
  run_number=$((index + 1))
  port=$((base_port + index))

  if [[ "$point" == "auto" ]]; then
    placement_id="auto-fit-frozen"
    run_dir="$(printf '%s/%02d-auto-fit' "$out" "$run_number")"
    n_cpu_moe_json="null"
  else
    n="${point#n}"
    placement_id="n-cpu-moe-$n"
    run_dir="$(printf '%s/%02d-n%02d' "$out" "$run_number" "$n")"
    n_cpu_moe_json="$n"
  fi
  mkdir -p "$run_dir"

  python3 - "$placement_id" "$n_cpu_moe_json" >"$run_dir/run-metadata.json" <<'PY'
import json
import sys

placement_id = sys.argv[1]
n_raw = sys.argv[2]
n = None if n_raw == "null" else int(n_raw)
print(json.dumps({
    "schema": "tesy.stock_placement_run.v1",
    "placement_id": placement_id,
    "n_cpu_moe": n,
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
  if [[ "$point" == "auto" ]]; then
    cmd+=("${auto_fit_args[@]}")
  else
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

  ready_start_ns="$(date +%s%N)"
  "${cmd[@]}" >"$run_dir/server.stdout.txt" 2>"$run_dir/server.stderr.txt" &
  server_pid=$!

  python3 -m tesy.resource_monitor \
    --pid "$server_pid" \
    --output "$run_dir/resources.jsonl" \
    --interval-ms 200 &
  monitor_pid=$!

  ready=0
  for _ in $(seq 1 900); do
    if ! kill -0 "$server_pid" 2>/dev/null; then
      echo "server exited before health PASS for $placement_id" >&2
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
    echo "server health timeout for $placement_id" >&2
    exit 1
  }

  python3 -m tesy.runtime_provenance \
    --pid "$server_pid" \
    --build-provenance "$out/build-provenance.json" \
    >"$run_dir/runtime-provenance.json"

  if grep -F 'failed to fit params to free device memory' "$run_dir/server.stderr.txt" >/dev/null; then
    echo "unexpected fit path executed for frozen placement $placement_id" >&2
    exit 1
  fi

  ready_end_ns="$(date +%s%N)"
  python3 - "$ready_start_ns" "$ready_end_ns" "$placement_id" \
    >"$run_dir/server-ready.json" <<'PY'
import json
import sys
start, end = int(sys.argv[1]), int(sys.argv[2])
print(json.dumps({
    "placement_id": sys.argv[3],
    "server_ready_ms": (end - start) / 1e6,
}, indent=2))
PY

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
    echo "FAIL_TRAJECTORY_COMPARABILITY at $placement_id" >&2
    exit 1
  fi

  kill "$server_pid"
  wait "$server_pid" || true
  server_pid=""
  wait "$monitor_pid" || true
  monitor_pid=""

  python3 - "$run_dir/resources.jsonl" "$gpu_total_bytes" "$gpu_target_mib" "$host_guard_mib" \
    >"$run_dir/resource-summary.json" <<'PY'
import json
import sys
from pathlib import Path

rows = [
    json.loads(line)
    for line in Path(sys.argv[1]).read_text(encoding="utf-8").splitlines()
    if line.strip()
]
gpu_total_bytes = int(sys.argv[2])
gpu_target_bytes = int(sys.argv[3]) * 1024 * 1024
host_guard_bytes = int(sys.argv[4]) * 1024 * 1024

if not rows:
    raise SystemExit("no resource samples")
gpu = [row["gpu"] for row in rows if row.get("gpu", {}).get("status") == "OK"]
proc = [row.get("process", {}) for row in rows]
system = [row.get("system", {}) for row in rows]
peak_gpu = max((row["memory_used_bytes"] for row in gpu), default=None)
if peak_gpu is None:
    raise SystemExit("no valid GPU telemetry")
if peak_gpu > gpu_total_bytes:
    raise SystemExit("observed GPU usage exceeds recorded total memory")

summary = {
    "samples": len(rows),
    "gpu_valid_samples": len(gpu),
    "gpu_failed_samples": len(rows) - len(gpu),
    "peak_gpu_memory_used_bytes": peak_gpu,
    "min_observed_gpu_free_bytes": gpu_total_bytes - peak_gpu,
    "max_gpu_temperature_c": max((row["temperature_c"] for row in gpu), default=None),
    "max_gpu_power_w": max((row["power_w"] for row in gpu), default=None),
    "peak_process_rss_bytes": max((row.get("VmRSS_bytes", 0) for row in proc), default=0),
    "peak_process_swap_bytes": max((row.get("VmSwap_bytes", 0) for row in proc), default=0),
    "min_mem_available_bytes": min(
        (row.get("MemAvailable_bytes", 2**63 - 1) for row in system),
        default=None,
    ),
    "min_swap_free_bytes": min(
        (row.get("SwapFree_bytes", 2**63 - 1) for row in system),
        default=None,
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
    echo "missing required placement telemetry for $placement_id" >&2
    exit 1
  }
done

python3 - "$out" >"$out/sweep-summary.json" <<'PY'
from __future__ import annotations

import hashlib
import json
import statistics
import sys
from pathlib import Path

root = Path(sys.argv[1])
capacity = json.loads((root / "capacity-summary.json").read_text(encoding="utf-8"))
rows = []

for run_dir in sorted(path for path in root.iterdir() if path.is_dir() and path.name[:2].isdigit()):
    meta = json.loads((run_dir / "run-metadata.json").read_text(encoding="utf-8"))
    req = json.loads((run_dir / "request.json").read_text(encoding="utf-8"))
    res = json.loads((run_dir / "resource-summary.json").read_text(encoding="utf-8"))
    ready = json.loads((run_dir / "server-ready.json").read_text(encoding="utf-8"))
    token_ids = req.get("generated_token_ids")
    timings = req["timings"]
    if (
        not isinstance(token_ids, list)
        or len(token_ids) != 64
        or timings["predicted_n"] != 64
    ):
        raise SystemExit(f"invalid 64-token trajectory in {run_dir}")
    token_blob = json.dumps(token_ids, separators=(",", ":")).encode()
    rows.append({
        "run": run_dir.name,
        "placement_id": meta["placement_id"],
        "n_cpu_moe": meta["n_cpu_moe"],
        "server_ready_ms": ready["server_ready_ms"],
        "ttft_ms": req["ttft_ms"],
        "prompt_tps": timings["prompt_per_second"],
        "decode_tps": timings["predicted_per_second"],
        "peak_gpu_memory_bytes": res["peak_gpu_memory_used_bytes"],
        "min_observed_gpu_free_bytes": res["min_observed_gpu_free_bytes"],
        "peak_process_rss_bytes": res["peak_process_rss_bytes"],
        "peak_process_swap_bytes": res["peak_process_swap_bytes"],
        "max_gpu_temperature_c": res["max_gpu_temperature_c"],
        "gpu_failed_samples": res["gpu_failed_samples"],
        "token_sha256": hashlib.sha256(token_blob).hexdigest(),
    })

by_placement = {}
for placement_id in sorted({row["placement_id"] for row in rows}):
    selected = [row for row in rows if row["placement_id"] == placement_id]
    if len(selected) != 2:
        raise SystemExit(
            f"expected two observations for {placement_id}, got {len(selected)}"
        )
    by_placement[placement_id] = {
        "n_cpu_moe": selected[0]["n_cpu_moe"],
        "observations": selected,
        "mean_ttft_ms": statistics.mean(row["ttft_ms"] for row in selected),
        "mean_prompt_tps": statistics.mean(row["prompt_tps"] for row in selected),
        "mean_decode_tps": statistics.mean(row["decode_tps"] for row in selected),
        "mean_peak_gpu_memory_bytes": statistics.mean(
            row["peak_gpu_memory_bytes"] for row in selected
        ),
        "max_peak_gpu_memory_bytes": max(
            row["peak_gpu_memory_bytes"] for row in selected
        ),
        "mean_peak_process_rss_bytes": statistics.mean(
            row["peak_process_rss_bytes"] for row in selected
        ),
        "max_process_swap_bytes": max(
            row["peak_process_swap_bytes"] for row in selected
        ),
        "max_gpu_temperature_c": max(
            row["max_gpu_temperature_c"] for row in selected
        ),
        "gpu_failed_samples": sum(row["gpu_failed_samples"] for row in selected),
    }

pareto = []
for placement_id, a in by_placement.items():
    dominated = False
    for other_id, b in by_placement.items():
        if other_id == placement_id:
            continue
        no_more_vram = (
            b["mean_peak_gpu_memory_bytes"] <= a["mean_peak_gpu_memory_bytes"]
        )
        no_slower = b["mean_decode_tps"] >= a["mean_decode_tps"]
        strictly = (
            b["mean_peak_gpu_memory_bytes"] < a["mean_peak_gpu_memory_bytes"]
            or b["mean_decode_tps"] > a["mean_decode_tps"]
        )
        if no_more_vram and no_slower and strictly:
            dominated = True
            break
    if not dominated:
        pareto.append(placement_id)

trajectory_hashes = sorted({row["token_sha256"] for row in rows})
trajectory_status = "PASS" if len(trajectory_hashes) == 1 else "FAIL"

payload = {
    "schema": "tesy.stock_placement_capacity_pareto.v1",
    "classification": "MEASURED_STOCK_PLACEMENT_FRONTIER_DIAGNOSTIC",
    "capacity_gate": capacity,
    "order": [row["placement_id"] for row in rows],
    "placements": by_placement,
    "decode_vram_pareto_placement_ids": sorted(pareto),
    "trajectory_comparability": {
        "status": trajectory_status,
        "unique_token_trajectory_hashes": trajectory_hashes,
        "required_token_count": 64,
    },
    "claim_boundary": (
        "Stock llama.cpp placement calibration on one locked model/workload. "
        "Capacity admission is estimator-derived; throughput/latency/resource "
        "rows are measured. No Tesy speedup, physical PCIe/NVMe byte, >RAM, "
        "or novelty claim follows."
    ),
}
print(json.dumps(payload, indent=2, sort_keys=True))
if trajectory_status != "PASS":
    raise SystemExit("FAIL_TRAJECTORY_COMPARABILITY")
PY

echo "PASS_DIAGNOSTIC_STOCK_PLACEMENT_CAPACITY_PARETO"
echo "outputs: $out"
