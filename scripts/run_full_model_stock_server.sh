#!/usr/bin/env bash
set -Eeuo pipefail

if [[ $# -lt 5 || $# -gt 6 ]]; then
  echo "usage: $0 MODEL.gguf PROMPT.txt OUTPUT_ROOT N_GPU_LAYERS PORT [count-only]" >&2
  exit 2
fi
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
model="$1"
prompt_file="$2"
out="$3"
ngl="$4"
port="$5"
mode="${6:-generate}"
server="$root/.deps/llama.cpp/build/bin/llama-server"
fit_tool="$root/.deps/llama.cpp/build/bin/llama-fit-params"
python_bin="$root/.venv/bin/python"
[[ "$ngl" =~ ^[0-9]+$ && "$port" =~ ^[0-9]+$ ]] || exit 2
[[ "$mode" == "generate" || "$mode" == "count-only" ]] || exit 2
[[ ! -e "$out" ]] || { echo "refusing existing root: $out" >&2; exit 1; }
mkdir -p "$out"
stage="inputs"
active_pid=""
monitor_pid=""
cleanup() {
  local rc=$?
  if [[ -n "$active_pid" ]] && kill -0 "$active_pid" 2>/dev/null; then
    kill "$active_pid" 2>/dev/null || true
    wait "$active_pid" 2>/dev/null || true
  fi
  if [[ -n "$monitor_pid" ]] && kill -0 "$monitor_pid" 2>/dev/null; then
    kill "$monitor_pid" 2>/dev/null || true
    wait "$monitor_pid" 2>/dev/null || true
  fi
  if [[ "$rc" -ne 0 ]]; then
    printf '{"schema":"tesy.full_model_stock_chat_failure.v1","stage":"%s","exit_code":%d}\n' \
      "$stage" "$rc" >"$out/failure.json"
  fi
}
trap cleanup EXIT

[[ -x "$server" && -x "$fit_tool" && -x "$python_bin" && -f "$model" && -f "$prompt_file" ]]
[[ -z "$(git -C "$root" status --porcelain)" ]]
[[ "$(git -C "$root/.deps/llama.cpp" rev-parse HEAD)" == \
  "4e416ee7308dd6b581796f1a6241276cd5982691" ]]
[[ -z "$(git -C "$root/.deps/llama.cpp" status --porcelain)" ]]
[[ "$(stat -c %s "$model")" == "12109564352" ]]
[[ "$(sha256sum "$model" | awk '{print $1}')" == \
  "52f57ab7d3df3ba9173827c1c6832e73375553a846f3e32b49f1ae2daad688d4" ]]
"$python_bin" -m tesy models verify gpt-oss-20b-mxfp4-gguf "$model" >"$out/model.json"
sha256sum "$server" "$prompt_file" >"$out/input-sha256.txt"

stage="host"
"$python_bin" -m tesy doctor --disk-path "$(dirname "$model")" \
  --reference-profile "$root/configs/reference-host.json" >"$out/doctor.json"
"$python_bin" - "$out/doctor.json" <<'PY'
import json
import sys
from pathlib import Path

doctor = json.loads(Path(sys.argv[1]).read_text())
assert doctor["reference_check"]["status"] == "PASS"
snap = doctor["snapshot"]
assert snap["virtualization"]["status"] == "PHYSICAL"
assert snap["gpu_compute_processes"]["status"] == "OK"
assert not snap["gpu_compute_processes"]["stdout"].strip()
PY

stage="capacity"
"$fit_tool" --model "$model" --ctx-size 4096 \
  --n-gpu-layers "$ngl" --fit off --fit-print on \
  >"$out/fit-print.stdout.txt" 2>"$out/fit-print.stderr.txt"
"$python_bin" - "$out/doctor.json" "$out/fit-print.stdout.txt" \
  "$out/placement-capacity.json" "$ngl" <<'PY'
import json
import sys
from pathlib import Path
from tesy.placement_capacity import evaluate_placement_capacity

doctor = json.loads(Path(sys.argv[1]).read_text())
snap = doctor["snapshot"]
result = evaluate_placement_capacity(
    Path(sys.argv[2]).read_text(),
    gpu_free_bytes=snap["gpu"]["gpus"][0]["memory_free_bytes"],
    mem_available_bytes=snap["memory"]["available_bytes"],
    placement_id=f"stock-chat-ngl-{sys.argv[4]}",
)
Path(sys.argv[3]).write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
assert result["admitted"], result["rejection_reasons"]
PY

cmd=(
  "$server" --model "$model" --ctx-size 4096
  --threads 12 --threads-batch 12
  --n-gpu-layers "$ngl" --fit off
  --jinja --chat-template gpt-oss --reasoning off
  --host 127.0.0.1 --port "$port" --parallel 1
  --no-warmup --no-cache-prompt
)
"$python_bin" - "$out/argv.json" "${cmd[@]}" <<'PY'
import json
import sys
from pathlib import Path
Path(sys.argv[1]).write_text(json.dumps(sys.argv[2:], indent=2) + "\n")
PY
stage="server"
"${cmd[@]}" >"$out/server.stdout.txt" 2>"$out/server.stderr.txt" &
active_pid=$!
"$python_bin" -m tesy.resource_monitor --pid "$active_pid" \
  --output "$out/resources.jsonl" --interval-ms 100 &
monitor_pid=$!
stage="request"
client_args=(--prompt "$prompt_file" --output "$out/run.json" --port "$port" --max-tokens 128)
if [[ "$mode" == "count-only" ]]; then
  client_args+=(--count-only)
fi
"$python_bin" -m tesy.full_stock_eval "${client_args[@]}"
stage="telemetry"
kill "$active_pid" 2>/dev/null || true
wait "$active_pid" 2>/dev/null || true
active_pid=""
wait "$monitor_pid"
monitor_pid=""
"$python_bin" - "$out/resources.jsonl" <<'PY'
import json
import sys
from pathlib import Path

rows = [json.loads(line) for line in Path(sys.argv[1]).read_text().splitlines() if line]
valid = [r for r in rows if set(r.get("process", {})) == {"VmRSS_bytes", "VmSwap_bytes"}]
assert valid and all(r["process"]["VmSwap_bytes"] == 0 for r in valid)
assert all(r.get("gpu", {}).get("status") == "OK" for r in rows)
PY
echo "FULL_MODEL_STOCK_CHAT_RUN_COMPLETED: $out"
