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
server="${TESY_LLAMA_SERVER:-$source_dir/build/bin/llama-server}"
prompt_file="$root/benchmarks/prompts/b0-b1-diagnostic.txt"
lock_file="${XDG_RUNTIME_DIR:-/tmp}/tesy-b0-b1.lock"

if [[ -e "$out" ]]; then
  echo "refusing to replace output root: $out" >&2
  exit 1
fi
mkdir -p "$out"

exec 9>"$lock_file"
if ! flock -n 9; then
  echo "another Tesy B0/B1 runner holds $lock_file" >&2
  exit 1
fi

python3 -m tesy models verify gpt-oss-20b-mxfp4-gguf "$model" >"$out/model.json"
python3 -m tesy doctor --disk-path "$(dirname "$model")"   --reference-profile "$root/configs/reference-host.json" >"$out/doctor.json"

[[ -x "$server" ]] || { echo "missing llama-server: $server" >&2; exit 1; }
python3 -m tesy backend probe   --binary "$server"   --source-dir "$source_dir" >"$out/backend.json"

help="$("$server" --help 2>&1)"
for flag in --cpu-moe --fit --fit-target --n-gpu-layers --host --port --no-warmup; do
  grep -F -- "$flag" <<<"$help" >/dev/null || {
    echo "llama-server missing required flag: $flag" >&2
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
sha256sum "$prompt_file" >"$out/prompt-sha256.txt"

order=(b0 b1 b1 b0)
base_port="${TESY_BENCH_PORT_BASE:-18080}"

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

for index in "${!order[@]}"; do
  arm="${order[$index]}"
  run_dir="$out/$((index + 1))-$arm"
  mkdir -p "$run_dir"
  port=$((base_port + index))

  cmd=(
    "$server"
    --model "$model"
    --host 127.0.0.1
    --port "$port"
    --ctx-size 4096
    --parallel 1
    --threads 12
    --threads-batch 12
    --gpu-layers auto
    --fit on
    --fit-target 1024
    --no-warmup
  )
  if [[ "$arm" == "b1" ]]; then
    cmd+=(--cpu-moe)
  fi

  printf '%q ' "${cmd[@]}" >"$run_dir/server-command.txt"
  printf '\n' >>"$run_dir/server-command.txt"

  ready_start_ns="$(date +%s%N)"
  "${cmd[@]}" >"$run_dir/server.stdout.txt" 2>"$run_dir/server.stderr.txt" &
  server_pid=$!

  python3 -m tesy.resource_monitor     --pid "$server_pid"     --output "$run_dir/resources.jsonl"     --interval-ms 200 &
  monitor_pid=$!

  ready=0
  for _ in $(seq 1 600); do
    if ! kill -0 "$server_pid" 2>/dev/null; then
      echo "server exited before health PASS for $arm" >&2
      wait "$server_pid" || true
      exit 1
    fi
    if curl -fsS "http://127.0.0.1:$port/health" >"$run_dir/health.json" 2>/dev/null; then
      ready=1
      break
    fi
    sleep 0.1
  done
  [[ "$ready" -eq 1 ]] || { echo "server health timeout for $arm" >&2; exit 1; }
  ready_end_ns="$(date +%s%N)"
  python3 - "$ready_start_ns" "$ready_end_ns" >"$run_dir/server-ready.json" <<'PY'
import json, sys
start, end = map(int, sys.argv[1:3])
print(json.dumps({"server_ready_ms": (end - start) / 1e6}, indent=2))
PY

  python3 -m tesy.server_client     --url "http://127.0.0.1:$port/completion"     --prompt-file "$prompt_file"     --n-predict 64     --output "$run_dir/request.json"

  token_sha="$(
    python3 - "$run_dir/request.json" <<'PY'
import hashlib
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
tokens = payload.get("generated_token_ids")
if not isinstance(tokens, list) or len(tokens) != 64:
    raise SystemExit(f"expected exactly 64 generated token IDs, got {tokens!r}")
blob = json.dumps(tokens, separators=(",", ":")).encode()
print(hashlib.sha256(blob).hexdigest())
PY
  )"
  printf '%s\n' "$token_sha" >"$run_dir/token-sha256.txt"
  if [[ -z "${reference_token_sha:-}" ]]; then
    reference_token_sha="$token_sha"
  elif [[ "$token_sha" != "$reference_token_sha" ]]; then
    echo "FAIL_TRAJECTORY_COMPARABILITY: $arm token IDs differ" >&2
    exit 1
  fi

  kill "$server_pid"
  wait "$server_pid" || true
  server_pid=""
  wait "$monitor_pid" || true
  monitor_pid=""

  cat "$run_dir/server.stderr.txt" "$run_dir/server.stdout.txt" |     grep -Ei 'offload|model buffer|compute buffer|CPU_Mapped|CUDA[0-9]'     >"$run_dir/placement.txt" || true
  if [[ ! -s "$run_dir/placement.txt" ]]; then
    echo "missing required placement telemetry for $arm" >&2
    exit 1
  fi

  python3 - "$run_dir/resources.jsonl" >"$run_dir/resource-summary.json" <<'PY'
import json, sys
from pathlib import Path
rows=[json.loads(x) for x in Path(sys.argv[1]).read_text().splitlines() if x.strip()]
if not rows:
    raise SystemExit("no resource samples")
gpu=[r["gpu"] for r in rows if r.get("gpu",{}).get("status")=="OK"]
proc=[r.get("process",{}) for r in rows]
system=[r.get("system",{}) for r in rows]
summary={
  "samples": len(rows),
  "gpu_valid_samples": len(gpu),
  "gpu_failed_samples": len(rows)-len(gpu),
  "peak_gpu_memory_used_bytes": max((r["memory_used_bytes"] for r in gpu), default=None),
  "max_gpu_temperature_c": max((r["temperature_c"] for r in gpu), default=None),
  "peak_process_rss_bytes": max((r.get("VmRSS_bytes",0) for r in proc), default=0),
  "peak_process_swap_bytes": max((r.get("VmSwap_bytes",0) for r in proc), default=0),
  "min_mem_available_bytes": min((r.get("MemAvailable_bytes",2**63-1) for r in system), default=None),
  "min_swap_free_bytes": min((r.get("SwapFree_bytes",2**63-1) for r in system), default=None),
}
print(json.dumps(summary, indent=2, sort_keys=True))
if summary["gpu_valid_samples"] == 0:
    raise SystemExit("no valid GPU telemetry")
if summary["peak_process_swap_bytes"] != 0:
    raise SystemExit("server process used swap")
PY
done

echo "PASS_DIAGNOSTIC_B0_B1_STOCK_PLACEMENT"
echo "outputs: $out"
