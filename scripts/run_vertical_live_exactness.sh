#!/usr/bin/env bash
set -Eeuo pipefail

if [[ $# -ne 5 && $# -ne 6 ]]; then
  echo "usage: $0 MODEL.gguf PROMPT.txt OUTPUT_ROOT LAYERS TOKENS [diagnostic|down-matrix]" >&2
  exit 2
fi
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
model="$(realpath "$1")"
prompt="$(realpath "$2")"
out="$3"
layers="$4"
tokens="$5"
diagnostic="${6:-}"
python_bin="$root/.venv/bin/python"
stock_source="$root/.deps/llama.cpp"
patched_source="$root/build/tesy-llama-split-src"
patch="$root/patches/llama-cpp-4e416ee73-tesy-split-graph-hook.patch"
build="$root/build/tesy-split-patched-gcc15"
tool="$build/tesy-mixed-residency"
stage="init"
active_pid=""
monitor_pid=""
stopped=0
[[ "$layers" =~ ^([1-9]|1[0-9]|2[0-4])$ ]]
[[ "$tokens" =~ ^[1-9][0-9]*$ && "$tokens" -le 128 ]]
if [[ -n "$diagnostic" ]]; then
  [[ "$diagnostic" == "diagnostic" || "$diagnostic" == "down-matrix" ]]
  [[ "$layers" == "3" && "$tokens" == "1" ]]
  [[ "$(sha256sum "$prompt" | awk '{print $1}')" == \
    "99b2641845df47370c29f1661ccb7493bb51ce11dd26a0f3afabb5c49cf18710" ]]
fi
sidecars="$root/research/vertical-numerical-blocker-20260925/diagnostic-233715"
if [[ "$diagnostic" == "down-matrix" ]]; then
  "$python_bin" - "$root" "$sidecars" <<'PY'
import hashlib
import json
import sys
from pathlib import Path

root, sidecars = map(Path, sys.argv[1:])
manifest = json.loads((root / "research/vertical-numerical-blocker-20260925/evidence-manifest-n2.json").read_text())
files = {item["path"]: item for item in manifest["files"]}
for arm in ("stock", "mixed"):
    for stage in ("ffn_moe_swiglu_oai", "ffn_moe_down"):
        name = f"layer2-{arm}-{stage}.f32"
        info = files[name]
        data = (sidecars / name).read_bytes()
        assert len(data) == info["size_bytes"] == 46080
        assert hashlib.sha256(data).hexdigest() == info["sha256"]
PY
fi
[[ ! -e "$out" ]] || { echo "refusing to reuse output root" >&2; exit 1; }
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
  if [[ "$rc" -ne 0 && ! -e "$out/failure.json" ]]; then
    printf '{"schema":"tesy.vertical_live_failure.v1","stage":"%s","exit_code":%d}\n' \
      "$stage" "$rc" >"$out/failure.json"
  fi
}
trap cleanup EXIT

stage="source"
[[ -x "$python_bin" && -x "$tool" && -f "$model" && -f "$prompt" ]]
[[ -z "$(git -C "$root" status --porcelain)" ]]
[[ -z "$(git -C "$stock_source" status --porcelain)" ]]
[[ "$(git -C "$stock_source" rev-parse HEAD)" == \
  "4e416ee7308dd6b581796f1a6241276cd5982691" ]]
[[ "$(git -C "$patched_source" rev-parse HEAD)" == \
  "4e416ee7308dd6b581796f1a6241276cd5982691" ]]
cmp "$patch" <(git -C "$patched_source" diff --binary)
[[ "$(stat -c %s "$model")" == "12109564352" ]]
[[ "$(sha256sum "$model" | awk '{print $1}')" == \
  "52f57ab7d3df3ba9173827c1c6832e73375553a846f3e32b49f1ae2daad688d4" ]]

stage="host"
"$python_bin" -m tesy doctor --disk-path "$(dirname "$model")" \
  --reference-profile "$root/configs/reference-host.json" >"$out/doctor.json"
"$python_bin" - "$out/doctor.json" <<'PY'
import json
import sys
from pathlib import Path

doctor = json.loads(Path(sys.argv[1]).read_text())
assert doctor["reference_check"]["status"] == "PASS"
s = doctor["snapshot"]
assert s["virtualization"]["status"] == "PHYSICAL"
assert s["gpu_compute_processes"]["status"] == "OK"
assert not s["gpu_compute_processes"]["stdout"].strip()
assert s["memory"]["available_bytes"] >= 18 * 1024**3
assert s["gpu"]["gpus"][0]["memory_free_bytes"] >= 6 * 1024**3
PY

stage="build"
cmake --build "$build" --parallel 4 --target tesy-mixed-residency \
  >"$out/build.stdout.txt" 2>"$out/build.stderr.txt"
"$python_bin" - "$root" "$out/build-provenance.json" "$model" "$prompt" \
  "$tool" "$patched_source" "$patch" <<'PY'
import hashlib
import json
import subprocess
import sys
from pathlib import Path

root, path, model, prompt, tool, patched, patch = map(Path, sys.argv[1:])
def sha(p):
    h = hashlib.sha256()
    with p.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()
def git(p, *args):
    return subprocess.check_output(["git", "-C", str(p), *args], text=True).strip()
payload = {
    "schema": "tesy.vertical_live_build_provenance.v1",
    "tesy_head": git(root, "rev-parse", "HEAD"),
    "tesy_tree": git(root, "rev-parse", "HEAD^{tree}"),
    "llama_base_head": git(patched, "rev-parse", "HEAD"),
    "patch_path": str(patch.resolve()),
    "patch_sha256": sha(patch),
    "native_source_sha256": sha(root / "native/tesy_mixed_residency.cpp"),
    "native_cmake_sha256": sha(root / "native/CMakeLists.txt"),
    "patched_context_cpp_sha256": sha(patched / "src/llama-context.cpp"),
    "patched_context_h_sha256": sha(patched / "src/llama-context.h"),
    "tool_path": str(tool.resolve()),
    "tool_sha256": sha(tool),
    "libllama_sha256": sha(tool.parent / "bin/libllama.so"),
    "libggml_cpu_sha256": sha(tool.parent / "bin/libggml-cpu.so"),
    "libggml_cuda_sha256": sha(tool.parent / "bin/libggml-cuda.so"),
    "model_sha256": sha(model),
    "model_size_bytes": model.stat().st_size,
    "prompt_sha256": sha(prompt),
    "status": "PASS",
}
path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
PY

cmd=("$tool" --model "$model" --output "$out/raw.json"
  --prompt-file "$prompt" --ctx 4096 --threads 12
  --vertical-live-exactness --vertical-layers "$layers" --vertical-tokens "$tokens")
if [[ -n "$diagnostic" ]]; then cmd+=(--vertical-numerical-diagnostic); fi
if [[ "$diagnostic" == "down-matrix" ]]; then
  cmd+=(--vertical-down-matrix --matrix-sidecars-dir "$sidecars")
fi
"$python_bin" - "$out/argv.json" "${cmd[@]}" <<'PY'
import json
import sys
from pathlib import Path

Path(sys.argv[1]).write_text(json.dumps(sys.argv[2:], indent=2) + "\n")
PY

stage="runtime_provenance"
"${cmd[@]}" >"$out/tool.stdout.txt" 2>"$out/tool.stderr.txt" &
active_pid=$!
"$python_bin" -m tesy.resource_monitor --pid "$active_pid" \
  --output "$out/resources.jsonl" --interval-ms 100 &
monitor_pid=$!
mapped=0
for _ in $(seq 1 4000); do
  kill -0 "$active_pid" 2>/dev/null || { echo "tool exited before provenance gate" >&2; exit 1; }
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
  --build-dir "$build" --expected-argv "$out/argv.json" \
  --output "$out/runtime-provenance.json"
kill -CONT "$active_pid"
stopped=0

stage="native"
set +e
wait "$active_pid"
tool_rc=$?
set -e
active_pid=""
wait "$monitor_pid"
monitor_pid=""
[[ "$tool_rc" -eq 0 ]] || exit "$tool_rc"

stage="resources"
"$python_bin" - "$out/doctor.json" "$out/resources.jsonl" \
  "$out/resource-summary.json" <<'PY'
import json
import math
import sys
from pathlib import Path

doctor = json.loads(Path(sys.argv[1]).read_text())
rows = [json.loads(x) for x in Path(sys.argv[2]).read_text().splitlines() if x]
valid = [r for r in rows if set(r.get("process", {})) == {"VmRSS_bytes", "VmSwap_bytes"}]
assert len(valid) >= 2
assert all(r["gpu"]["status"] == "OK" for r in rows)
assert all(r["process"]["VmSwap_bytes"] == 0 for r in valid)
assert all(math.isfinite(r["gpu"]["temperature_c"]) and
           math.isfinite(r["gpu"]["power_w"]) for r in valid)
gpu_total = doctor["snapshot"]["gpu"]["gpus"][0]["memory_total_bytes"]
min_host = min(r["system"]["MemAvailable_bytes"] for r in valid)
peak_gpu = max(r["gpu"]["memory_used_bytes"] for r in valid)
assert min_host >= 2 * 1024**3
assert gpu_total - peak_gpu >= 1024**3
Path(sys.argv[3]).write_text(json.dumps({
    "schema": "tesy.vertical_live_resource_summary.v1",
    "status": "PASS", "valid_samples": len(valid),
    "terminal_samples_excluded": len(rows) - len(valid),
    "gpu_failed_samples": 0, "peak_process_swap_bytes": 0,
    "peak_process_rss_bytes": max(r["process"]["VmRSS_bytes"] for r in valid),
    "peak_observed_gpu_used_bytes": peak_gpu,
    "min_mem_available_bytes": min_host,
}, indent=2, sort_keys=True) + "\n")
PY
echo "VERTICAL_LIVE_LOCAL_RUN_PASS: $out"
