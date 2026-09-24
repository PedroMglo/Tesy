#!/usr/bin/env bash
set -Eeuo pipefail

if [[ $# -lt 3 || $# -gt 5 ]]; then
  echo "usage: $0 MODEL.gguf PROMPT.txt OUTPUT_ROOT [N_GPU_LAYERS] [N_PREDICT]" >&2
  exit 2
fi

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
model="$1"
prompt_file="$2"
out="$3"
ngl="${4:-0}"
n_predict="${5:-128}"
binary="$root/.deps/llama.cpp/build/bin/llama-cli"
fit_tool="$root/.deps/llama.cpp/build/bin/llama-fit-params"
python_bin="$root/.venv/bin/python"

[[ "$ngl" =~ ^[0-9]+$ && "$n_predict" =~ ^[1-9][0-9]*$ ]] || {
  echo "N_GPU_LAYERS and N_PREDICT must be non-negative/positive integers" >&2
  exit 2
}
[[ ! -e "$out" ]] || { echo "refusing to reuse output root: $out" >&2; exit 1; }
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
    printf '{"schema":"tesy.full_model_stock_failure.v1","stage":"%s","exit_code":%d}\n' \
      "$stage" "$rc" >"$out/failure.json"
  fi
}
trap cleanup EXIT

[[ -x "$binary" && -x "$fit_tool" && -x "$python_bin" && -f "$model" && -f "$prompt_file" ]]
[[ -z "$(git -C "$root" status --porcelain)" ]]
[[ "$(git -C "$root/.deps/llama.cpp" rev-parse HEAD)" == \
  "4e416ee7308dd6b581796f1a6241276cd5982691" ]]
[[ -z "$(git -C "$root/.deps/llama.cpp" status --porcelain)" ]]
[[ "$(stat -c %s "$model")" == "12109564352" ]]
[[ "$(sha256sum "$model" | awk '{print $1}')" == \
  "52f57ab7d3df3ba9173827c1c6832e73375553a846f3e32b49f1ae2daad688d4" ]]
"$python_bin" -m tesy models verify gpt-oss-20b-mxfp4-gguf "$model" \
  >"$out/model.json"
sha256sum "$binary" "$prompt_file" >"$out/input-sha256.txt"

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
assert snapshot["gpu_compute_processes"]["status"] == "OK"
assert not snapshot["gpu_compute_processes"]["stdout"].strip()
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
snapshot = doctor["snapshot"]
result = evaluate_placement_capacity(
    Path(sys.argv[2]).read_text(),
    gpu_free_bytes=snapshot["gpu"]["gpus"][0]["memory_free_bytes"],
    mem_available_bytes=snapshot["memory"]["available_bytes"],
    placement_id=f"stock-ngl-{sys.argv[4]}",
)
Path(sys.argv[3]).write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
assert result["admitted"], result["rejection_reasons"]
PY

prompt="$(<"$prompt_file")"
cmd=(
  "$binary" --model "$model" --ctx-size 4096
  --threads 12 --threads-batch 12
  --n-gpu-layers "$ngl" --fit off
  --n-predict "$n_predict" --temperature 0 --top-k 1 --seed 42
  --jinja --chat-template gpt-oss --reasoning off
  --no-warmup --no-context-shift --simple-io --no-display-prompt
  --single-turn --color off --prompt "$prompt"
)
"$python_bin" - "$out/argv.json" "${cmd[@]}" <<'PY'
import json
import sys
from pathlib import Path

Path(sys.argv[1]).write_text(json.dumps(sys.argv[2:], indent=2) + "\n")
PY
stage="generation"
"${cmd[@]}" >"$out/stdout.txt" 2>"$out/stderr.txt" &
active_pid=$!
"$python_bin" -m tesy.resource_monitor --pid "$active_pid" \
  --output "$out/resources.jsonl" --interval-ms 100 &
monitor_pid=$!
wait "$active_pid"
active_pid=""
wait "$monitor_pid"
monitor_pid=""
printf '0\n' >"$out/return-code.txt"
echo "FULL_MODEL_STOCK_GENERATION_COMPLETED: $out"
