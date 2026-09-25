#!/usr/bin/env bash
set -Eeuo pipefail

if [[ $# -ne 2 ]]; then
  echo "usage: $0 MODEL.gguf OUTPUT_ROOT" >&2
  exit 2
fi
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
model="$(realpath "$1")"
out="$2"
python_bin="$root/.venv/bin/python"
source_dir="$root/.deps/llama.cpp"
build="$root/build/tesy-mixed-residency"
tool="$build/tesy-stock-prefix-logits"
stage="init"
active_pid=""
monitor_pid=""
stopped=0
[[ ! -e "$out" ]] || { echo "refusing reused root: $out" >&2; exit 1; }
mkdir -p "$out"
cleanup() {
  local rc=$?
  if [[ -n "$active_pid" ]] && kill -0 "$active_pid" 2>/dev/null; then
    if [[ "$stopped" -eq 1 ]]; then kill -CONT "$active_pid" 2>/dev/null || true; fi
    kill "$active_pid" 2>/dev/null || true
    wait "$active_pid" 2>/dev/null || true
  fi
  if [[ -n "$monitor_pid" ]] && kill -0 "$monitor_pid" 2>/dev/null; then
    kill "$monitor_pid" 2>/dev/null || true
    wait "$monitor_pid" 2>/dev/null || true
  fi
  if [[ "$rc" -ne 0 ]]; then
    printf '{"schema":"tesy.stock_prefix_characterization_failure.v1","stage":"%s","exit_code":%d}\n' \
      "$stage" "$rc" >"$out/failure.json"
  fi
}
trap cleanup EXIT

stage="source"
[[ -x "$python_bin" && -x "$tool" && -f "$model" ]]
[[ -z "$(git -C "$root" status --porcelain)" ]]
[[ "$(git -C "$source_dir" rev-parse HEAD)" == \
  "4e416ee7308dd6b581796f1a6241276cd5982691" ]]
[[ -z "$(git -C "$source_dir" status --porcelain)" ]]
[[ "$(stat -c %s "$model")" == "12109564352" ]]
[[ "$(sha256sum "$model" | awk '{print $1}')" == \
  "52f57ab7d3df3ba9173827c1c6832e73375553a846f3e32b49f1ae2daad688d4" ]]
[[ "$(sha256sum "$root/benchmarks/prompts/vertical-short-summary.txt" | awk '{print $1}')" == \
  "99b2641845df47370c29f1661ccb7493bb51ce11dd26a0f3afabb5c49cf18710" ]]
[[ "$(sha256sum "$root/benchmarks/prompts/vertical-eval-code-short.txt" | awk '{print $1}')" == \
  "6cab5251b0045b55cbf0dc7212a1c5f799e7777ca6712731933fce9cf7650327" ]]

stage="host"
"$python_bin" -m tesy doctor --disk-path "$(dirname "$model")" \
  --reference-profile "$root/configs/reference-host.json" >"$out/doctor.json"
"$python_bin" - "$out/doctor.json" <<'PY'
import json
import sys
from pathlib import Path
d = json.loads(Path(sys.argv[1]).read_text())
assert d["reference_check"]["status"] == "PASS"
s = d["snapshot"]
assert s["virtualization"]["status"] == "PHYSICAL"
assert s["gpu_compute_processes"]["status"] == "OK"
assert not s["gpu_compute_processes"]["stdout"].strip()
assert s["memory"]["available_bytes"] >= 18 * 1024**3
assert s["gpu"]["gpus"][0]["memory_free_bytes"] >= 6 * 1024**3
PY

stage="build"
cmake --build "$build" --parallel 4 --target tesy-stock-prefix-logits \
  >"$out/build.stdout.txt" 2>"$out/build.stderr.txt"
"$python_bin" - "$root" "$model" "$tool" "$out/build-provenance.json" <<'PY'
import hashlib
import json
import subprocess
import sys
from pathlib import Path
root, model, tool, output = map(Path, sys.argv[1:])
def sha(p):
    h = hashlib.sha256()
    with p.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()
def git(p, *args):
    return subprocess.check_output(["git", "-C", str(p), *args], text=True).strip()
payload = {
    "schema": "tesy.stock_prefix_build_provenance.v1",
    "tesy_head": git(root, "rev-parse", "HEAD"),
    "tesy_tree": git(root, "rev-parse", "HEAD^{tree}"),
    "llama_head": git(root / ".deps/llama.cpp", "rev-parse", "HEAD"),
    "native_source_sha256": sha(root / "native/tesy_stock_prefix_logits.cpp"),
    "native_cmake_sha256": sha(root / "native/CMakeLists.txt"),
    "model_sha256": sha(model), "model_size_bytes": model.stat().st_size,
    "tool_path": str(tool.resolve()), "tool_sha256": sha(tool),
    "libllama_sha256": sha(tool.parent / "bin/libllama.so"),
    "libggml_cpu_sha256": sha(tool.parent / "bin/libggml-cpu.so"),
    "libggml_cuda_sha256": sha(tool.parent / "bin/libggml-cuda.so"),
    "status": "PASS",
}
output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
PY

run_one() {
  local label="$1" repeat="$2" ngl="$3" common="$4"
  local run="$out/$label-r$repeat-ngl$ngl"
  mkdir "$run"
  local prompt="$root/benchmarks/prompts/vertical-short-summary.txt"
  if [[ "$label" == "code" ]]; then
    prompt="$root/benchmarks/prompts/vertical-eval-code-short.txt"
  fi
  local cmd=("$tool" --model "$model" --prompt-file "$prompt"
             --output-dir "$run" --ngl "$ngl")
  if [[ "$common" != "auto" ]]; then cmd+=(--common-token "$common"); fi
  "$python_bin" - "$run/argv.json" "${cmd[@]}" <<'PY'
import json
import sys
from pathlib import Path
Path(sys.argv[1]).write_text(json.dumps(sys.argv[2:], indent=2) + "\n")
PY
  stage="runtime-$label-r$repeat-ngl$ngl"
  "${cmd[@]}" >"$run/stdout.txt" 2>"$run/stderr.txt" &
  active_pid=$!
  "$python_bin" -m tesy.resource_monitor --pid "$active_pid" \
    --output "$run/resources.jsonl" --interval-ms 100 &
  monitor_pid=$!
  local mapped=0
  for _ in $(seq 1 4000); do
    kill -0 "$active_pid" 2>/dev/null || { echo "tool exited before provenance gate" >&2; return 1; }
    if rg -q 'libggml-cuda\.so' "/proc/$active_pid/maps" 2>/dev/null; then
      kill -STOP "$active_pid"
      stopped=1
      mapped=1
      break
    fi
    sleep 0.005
  done
  [[ "$mapped" -eq 1 ]]
  "$python_bin" -m tesy.mixed_residency_provenance \
    --pid "$active_pid" --expected-executable "$tool" \
    --build-dir "$build" --expected-argv "$run/argv.json" \
    --output "$run/runtime-provenance.json"
  kill -CONT "$active_pid"
  stopped=0
  wait "$active_pid"
  active_pid=""
  wait "$monitor_pid"
  monitor_pid=""
  "$python_bin" - "$run/resources.jsonl" "$run/resource-summary.json" "$out/doctor.json" <<'PY'
import json
import math
import sys
from pathlib import Path
rows = [json.loads(s) for s in Path(sys.argv[1]).read_text().splitlines() if s]
valid = [r for r in rows if set(r.get("process", {})) == {"VmRSS_bytes", "VmSwap_bytes"}]
assert len(valid) >= 2
assert all(r["gpu"]["status"] == "OK" for r in rows)
assert all(r["process"]["VmSwap_bytes"] == 0 for r in valid)
assert all(math.isfinite(r["gpu"]["temperature_c"]) and
           math.isfinite(r["gpu"]["power_w"]) for r in valid)
total = json.loads(Path(sys.argv[3]).read_text())["snapshot"]["gpu"]["gpus"][0]["memory_total_bytes"]
min_host = min(r["system"]["MemAvailable_bytes"] for r in valid)
peak_gpu = max(r["gpu"]["memory_used_bytes"] for r in valid)
assert min_host >= 2 * 1024**3
assert total - peak_gpu >= 1024**3
Path(sys.argv[2]).write_text(json.dumps({
    "schema": "tesy.stock_prefix_resource_summary.v1", "status": "PASS",
    "valid_samples": len(valid), "terminal_samples_excluded": len(rows) - len(valid),
    "peak_process_swap_bytes": 0, "gpu_failed_samples": 0,
    "peak_process_rss_bytes": max(r["process"]["VmRSS_bytes"] for r in valid),
    "peak_observed_gpu_used_bytes": peak_gpu, "min_mem_available_bytes": min_host,
}, indent=2, sort_keys=True) + "\n")
PY
}

for label in historical code; do
  run_one "$label" 1 0 auto
  common="$("$python_bin" - "$out/$label-r1-ngl0/raw.json" <<'PY'
import json
import sys
from pathlib import Path
print(json.loads(Path(sys.argv[1]).read_text())["common_token"])
PY
)"
  if [[ "$label" == "historical" ]]; then [[ "$common" == "32" ]]; fi
  run_one "$label" 1 12 "$common"
  run_one "$label" 2 12 "$common"
  run_one "$label" 2 0 "$common"
done
stage="complete"
echo "STOCK_PREFIX_CHARACTERIZATION_LOCAL_EXECUTION_PASS: $out"
