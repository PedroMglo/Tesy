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
cli="${TESY_LLAMA_CLI:-$source_dir/build/bin/llama-cli}"
server="${TESY_LLAMA_SERVER:-$source_dir/build/bin/llama-server}"
prompt_file="$root/benchmarks/prompts/b0-b1-diagnostic.txt"
lock_file="${XDG_RUNTIME_DIR:-/tmp}/tesy-placement-sweep.lock"
base_port="${TESY_SWEEP_PORT_BASE:-18100}"

if [[ -e "$out" ]]; then
  echo "refusing to replace output root: $out" >&2
  exit 1
fi
mkdir -p "$out"

exec 9>"$lock_file"
if ! flock -n 9; then
  echo "another Tesy placement sweep holds $lock_file" >&2
  exit 1
fi

python3 -m tesy models verify gpt-oss-20b-mxfp4-gguf "$model" >"$out/model.json"
python3 -m tesy doctor   --disk-path "$(dirname "$model")"   --reference-profile "$root/configs/reference-host.json" >"$out/doctor.json"

python3 - "$root/configs/b0-b1-toolchain.lock.json" "$out/doctor.json" >"$out/toolchain-check.json" <<'PY'
import json
import re
import subprocess
import sys
from pathlib import Path

lock = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
doctor = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
if lock.get("schema") != "tesy.b0_b1_toolchain_lock.v1":
    raise SystemExit("unsupported B0/B1 toolchain lock schema")

def run(command):
    p = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        env={"LC_ALL": "C"},
    )
    if p.returncode != 0:
        raise SystemExit(
            f"toolchain probe failed: {command!r}: {p.stderr.strip()}"
        )
    return (p.stdout + "\n" + p.stderr).strip()

observed = {
    "nvidia_driver_version": doctor["snapshot"]["gpu"]["gpus"][0]["driver_version"],
    "host_c_compiler_version": run(
        [lock["host_c_compiler"], "-dumpfullversion"]
    ).splitlines()[0],
    "host_cxx_compiler_version": run(
        [lock["host_cxx_compiler"], "-dumpfullversion"]
    ).splitlines()[0],
}
cmake_text = run(["cmake", "--version"])
observed["cmake_version"] = (
    cmake_text.splitlines()[0].removeprefix("cmake version ").strip()
)
nvcc_text = run([lock["cuda_compiler"], "--version"])
match = re.search(r"V([0-9]+(?:\.[0-9]+)+)", nvcc_text)
if not match:
    raise SystemExit("cannot parse nvcc version")
observed["cuda_compiler_version"] = match.group(1)

expected = {key: lock[key] for key in observed}
mismatch = {
    key: {"expected": expected[key], "observed": observed[key]}
    for key in observed
    if observed[key] != expected[key]
}
payload = {
    "schema": "tesy.b0_b1_toolchain_check.v1",
    "classification": "MEASURED_LOCAL_PROVENANCE",
    "source": lock["source"],
    "expected": expected,
    "observed": observed,
    "status": "PASS" if not mismatch else "FAIL",
    "mismatch": mismatch,
}
print(json.dumps(payload, indent=2, sort_keys=True))
if mismatch:
    raise SystemExit("frozen B0/B1 driver/toolchain identity mismatch")
PY

[[ -x "$cli" ]] || { echo "missing llama-cli: $cli" >&2; exit 1; }
[[ -x "$server" ]] || { echo "missing llama-server: $server" >&2; exit 1; }

# The backend feature lock is a llama-cli surface. Probe source identity there,
# then independently bind both selected binaries to that exact locked source
# revision through their embedded version commit before any model measurement.
python3 -m tesy backend probe \
  --binary "$cli" \
  --source-dir "$source_dir" >"$out/backend.json"

"$cli" --version >"$out/cli-version.txt" 2>&1
"$server" --version >"$out/server-version.txt" 2>&1

python3 - \
  "$out/backend.json" \
  "$out/cli-version.txt" \
  "$out/server-version.txt" <<'PY'
import json
import re
import sys
from pathlib import Path

backend = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
if backend.get("status") != "PASS":
    raise SystemExit(f"backend probe did not PASS: {backend.get('status')!r}")

source = backend.get("source")
if not isinstance(source, dict) or source.get("probe_status") != "PASS":
    raise SystemExit("backend source provenance did not PASS")

expected = source.get("expected_head")
if not isinstance(expected, str) or len(expected) != 40:
    raise SystemExit("backend probe did not expose a 40-character expected HEAD")
expected = expected.lower()

pattern = re.compile(r"\bcommit\s+([0-9a-f]{7,40})\b", re.IGNORECASE)
for label, raw_path in (
    ("llama-cli", sys.argv[2]),
    ("llama-server", sys.argv[3]),
):
    text = Path(raw_path).read_text(encoding="utf-8", errors="replace")
    match = pattern.search(text)
    if match is None:
        raise SystemExit(f"{label} --version did not expose a commit id")
    observed = match.group(1).lower()
    if not expected.startswith(observed):
        raise SystemExit(
            f"{label} build revision {observed} does not match locked {expected}"
        )
PY

git -C "$root" rev-parse HEAD >"$out/tesy-head.txt"
git -C "$root" status --porcelain=v1 >"$out/tesy-status.txt"
git -C "$source_dir" rev-parse HEAD >"$out/llama-head.txt"
git -C "$source_dir" status --porcelain=v1 >"$out/llama-status.txt"
[[ ! -s "$out/tesy-status.txt" ]] || { echo "dirty Tesy worktree" >&2; exit 1; }
[[ ! -s "$out/llama-status.txt" ]] || { echo "dirty llama.cpp worktree" >&2; exit 1; }

sha256sum "$cli" >"$out/cli-sha256.txt"
sha256sum "$server" >"$out/server-sha256.txt"
sha256sum "$prompt_file" >"$out/prompt-sha256.txt"

help="$("$server" --help 2>&1)"
for flag in --n-cpu-moe --fit --fit-target --n-gpu-layers --host --port --no-warmup --verbosity; do
  grep -F -- "$flag" <<<"$help" >/dev/null || {
    echo "llama-server missing required flag: $flag" >&2
    exit 1
  }
done

order=(0 4 8 12 16 20 24 24 20 16 12 8 4 0)

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
  n="${order[$index]}"
  run_number=$((index + 1))
  run_dir="$(printf '%s/%02d-n%02d' "$out" "$run_number" "$n")"
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
    --n-cpu-moe "$n"
    --no-warmup
    --verbosity 4
  )

  printf '%q ' "${cmd[@]}" >"$run_dir/server-command.txt"
  printf '\n' >>"$run_dir/server-command.txt"

  ready_start_ns="$(date +%s%N)"
  "${cmd[@]}" >"$run_dir/server.stdout.txt" 2>"$run_dir/server.stderr.txt" &
  server_pid=$!

  python3 -m tesy.resource_monitor     --pid "$server_pid"     --output "$run_dir/resources.jsonl"     --interval-ms 200 &
  monitor_pid=$!

  ready=0
  for _ in $(seq 1 900); do
    if ! kill -0 "$server_pid" 2>/dev/null; then
      echo "server exited before health PASS for n-cpu-moe=$n" >&2
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
    echo "server health timeout for n-cpu-moe=$n" >&2
    exit 1
  }

  python3 - "$run_dir/server.stderr.txt" "$n" "$run_dir/placement.json" <<'PY'
import json
import re
import sys
from pathlib import Path

stderr_path = Path(sys.argv[1])
requested_n = int(sys.argv[2])
output_path = Path(sys.argv[3])
text = stderr_path.read_text(encoding="utf-8", errors="replace")

override_re = re.compile(
    r"tensor (?P<name>blk\.(?P<layer>\d+)\.ffn_"
    r"(?P<kind>gate|up|down)_exps\.(?P<suffix>weight|bias)) "
    r"\([^\n]*?\) buffer type overridden to (?P<buft>\S+)"
)
observed = {}
for match in override_re.finditer(text):
    name = match.group("name")
    buft = match.group("buft")
    old = observed.get(name)
    if old is not None and old != buft:
        raise SystemExit(
            f"conflicting override buffer types for {name}: {old} vs {buft}"
        )
    observed[name] = buft

expected = {
    f"blk.{layer}.ffn_{kind}_exps.{suffix}"
    for layer in range(requested_n)
    for kind in ("gate", "up", "down")
    for suffix in ("weight", "bias")
}
missing = sorted(expected - set(observed))
wrong_buft = {
    name: observed[name]
    for name in sorted(expected & set(observed))
    if not observed[name].startswith("CPU")
}

buffer_re = re.compile(
    r"(?P<name>CPU_Mapped|CPU|CUDA0|CUDA_Host) model buffer size\s*=\s*"
    r"(?P<mib>[0-9]+(?:\.[0-9]+)?) MiB"
)
model_buffers = {}
for match in buffer_re.finditer(text):
    model_buffers[match.group("name")] = float(match.group("mib"))

failures = []
if missing:
    failures.append(f"missing requested CPU overrides: {missing}")
if wrong_buft:
    failures.append(f"requested overrides not on CPU-class buffers: {wrong_buft}")
if "CUDA0" not in model_buffers:
    failures.append("missing CUDA0 model-buffer record")
if requested_n > 0 and not any(
    name.startswith("CPU") for name in model_buffers
):
    failures.append("missing CPU model-buffer record for requested CPU experts")

payload = {
    "schema": "tesy.n_cpu_moe_placement_log.v1",
    "classification": "MEASURED_RUNTIME_PLACEMENT_LOG_DIAGNOSTIC",
    "status": "PASS" if not failures else "FAIL",
    "requested_n_cpu_moe": requested_n,
    "expected_forced_cpu_tensor_count": len(expected),
    "expected_forced_cpu_tensors": sorted(expected),
    "observed_expert_override_buft": observed,
    "model_buffers_mib": model_buffers,
    "failures": failures,
    "claim_boundary": (
        "PASS proves that every expert tensor in the first requested N MoE "
        "layers emitted a pinned loader override to a CPU-class buffer and that "
        "the load log exposed CUDA0/CPU aggregate model-buffer records. Extra "
        "overrides may exist due to other placement mechanisms. This is placement "
        "log evidence, not physical memory traffic."
    ),
}
with output_path.open("x", encoding="utf-8") as handle:
    json.dump(payload, handle, indent=2, sort_keys=True)
    handle.write("\n")
if failures:
    raise SystemExit("; ".join(failures))
PY

  ready_end_ns="$(date +%s%N)"
  python3 - "$ready_start_ns" "$ready_end_ns" "$n" >"$run_dir/server-ready.json" <<'PY'
import json, sys
start, end, n = int(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3])
print(json.dumps({
    "n_cpu_moe": n,
    "server_ready_ms": (end - start) / 1e6,
}, indent=2))
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
    raise SystemExit(
        f"expected exactly 64 generated token IDs, got "
        f"{len(tokens) if isinstance(tokens, list) else 'invalid'}"
    )
blob = json.dumps(tokens, separators=(",", ":")).encode()
print(hashlib.sha256(blob).hexdigest())
PY
  )"
  printf '%s\n' "$token_sha" >"$run_dir/token-sha256.txt"
  if [[ -z "${reference_token_sha:-}" ]]; then
    reference_token_sha="$token_sha"
  elif [[ "$token_sha" != "$reference_token_sha" ]]; then
    echo "FAIL_TRAJECTORY_COMPARABILITY at n-cpu-moe=$n" >&2
    exit 1
  fi

  kill "$server_pid"
  wait "$server_pid" || true
  server_pid=""
  wait "$monitor_pid" || true
  monitor_pid=""

  sha256sum "$run_dir/server.stdout.txt" >"$run_dir/server-stdout-sha256.txt"
  sha256sum "$run_dir/server.stderr.txt" >"$run_dir/server-stderr-sha256.txt"
  sha256sum "$run_dir/placement.json" >"$run_dir/placement-sha256.txt"

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
  "max_gpu_power_w": max((r["power_w"] for r in gpu), default=None),
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

  grep -Ei 'buffer type overridden|llm_load_tensors|load_tensors|offloaded|model buffer|compute buffer|CPU_Mapped|CUDA[0-9]' \
    "$run_dir/server.stderr.txt" >"$run_dir/placement.txt" || true
done

python3 - "$out" >"$out/sweep-summary.json" <<'PY'
from __future__ import annotations
import hashlib
import json
import re
import statistics
import sys
from pathlib import Path

root=Path(sys.argv[1])
rows=[]
pattern=re.compile(r"(?P<idx>\d+)-n(?P<n>\d+)$")

for run_dir in sorted(p for p in root.iterdir() if p.is_dir()):
    match=pattern.fullmatch(run_dir.name)
    if not match:
        continue
    req=json.loads((run_dir/"request.json").read_text())
    res=json.loads((run_dir/"resource-summary.json").read_text())
    ready=json.loads((run_dir/"server-ready.json").read_text())
    placement=json.loads((run_dir/"placement.json").read_text())
    t=req["timings"]
    token_ids=req.get("generated_token_ids")
    if (
        not isinstance(token_ids, list)
        or len(token_ids) != 64
        or t["predicted_n"] != 64
    ):
        raise SystemExit(f"invalid 64-token trajectory in {run_dir}")
    if (
        placement.get("status") != "PASS"
        or placement.get("requested_n_cpu_moe") != int(match.group("n"))
    ):
        raise SystemExit(f"placement evidence did not PASS in {run_dir}")
    stderr_sha = hashlib.sha256(
        (run_dir/"server.stderr.txt").read_bytes()
    ).hexdigest()
    stdout_sha = hashlib.sha256(
        (run_dir/"server.stdout.txt").read_bytes()
    ).hexdigest()
    token_blob=json.dumps(token_ids, separators=(",", ":")).encode()
    rows.append({
        "run": run_dir.name,
        "n_cpu_moe": int(match.group("n")),
        "server_ready_ms": ready["server_ready_ms"],
        "ttft_ms": req["ttft_ms"],
        "prompt_tps": t["prompt_per_second"],
        "decode_tps": t["predicted_per_second"],
        "peak_gpu_memory_bytes": res["peak_gpu_memory_used_bytes"],
        "peak_process_rss_bytes": res["peak_process_rss_bytes"],
        "peak_process_swap_bytes": res["peak_process_swap_bytes"],
        "max_gpu_temperature_c": res["max_gpu_temperature_c"],
        "gpu_failed_samples": res["gpu_failed_samples"],
        "placement_status": placement["status"],
        "expected_forced_cpu_tensor_count": placement[
            "expected_forced_cpu_tensor_count"
        ],
        "server_stdout_sha256": stdout_sha,
        "server_stderr_sha256": stderr_sha,
        "token_count": len(token_ids),
        "token_sha256": hashlib.sha256(token_blob).hexdigest(),
    })

expected=[0,4,8,12,16,20,24]
by_n={}
for n in expected:
    selected=[r for r in rows if r["n_cpu_moe"]==n]
    if len(selected)!=2:
        raise SystemExit(f"expected two observations for N={n}, got {len(selected)}")
    by_n[n]={
        "observations": selected,
        "mean_ttft_ms": statistics.mean(r["ttft_ms"] for r in selected),
        "min_ttft_ms": min(r["ttft_ms"] for r in selected),
        "max_ttft_ms": max(r["ttft_ms"] for r in selected),
        "mean_prompt_tps": statistics.mean(r["prompt_tps"] for r in selected),
        "mean_decode_tps": statistics.mean(r["decode_tps"] for r in selected),
        "mean_peak_gpu_memory_bytes": statistics.mean(r["peak_gpu_memory_bytes"] for r in selected),
        "max_peak_gpu_memory_bytes": max(r["peak_gpu_memory_bytes"] for r in selected),
        "mean_peak_process_rss_bytes": statistics.mean(r["peak_process_rss_bytes"] for r in selected),
        "max_process_swap_bytes": max(r["peak_process_swap_bytes"] for r in selected),
        "max_gpu_temperature_c": max(r["max_gpu_temperature_c"] for r in selected),
        "gpu_failed_samples": sum(r["gpu_failed_samples"] for r in selected),
    }

pareto=[]
for n,a in by_n.items():
    dominated=False
    for m,b in by_n.items():
        if m==n:
            continue
        no_more_vram=b["mean_peak_gpu_memory_bytes"] <= a["mean_peak_gpu_memory_bytes"]
        no_slower=b["mean_decode_tps"] >= a["mean_decode_tps"]
        strictly=(
            b["mean_peak_gpu_memory_bytes"] < a["mean_peak_gpu_memory_bytes"]
            or b["mean_decode_tps"] > a["mean_decode_tps"]
        )
        if no_more_vram and no_slower and strictly:
            dominated=True
            break
    if not dominated:
        pareto.append(n)

trajectory_hashes=sorted({r["token_sha256"] for r in rows})
trajectory_status="PASS" if len(trajectory_hashes)==1 else "FAIL"

payload={
  "schema":"tesy.n_cpu_moe_pareto_sweep.v1",
  "classification":"MEASURED_STOCK_PLACEMENT_DIAGNOSTIC",
  "order":[r["n_cpu_moe"] for r in rows],
  "points":{str(n):by_n[n] for n in expected},
  "decode_vram_pareto_n_cpu_moe":sorted(pareto),
  "trajectory_comparability": {
      "status": trajectory_status,
      "unique_token_trajectory_hashes": trajectory_hashes,
      "required_token_count": 64,
  },
  "claim_boundary":(
    "Stock llama.cpp calibration only. Pareto is defined on mean decode throughput "
    "and mean observed peak GPU memory for this workload. No Tesy speedup, physical "
    "transfer-byte, >RAM or novelty claim follows."
  ),
}
print(json.dumps(payload, indent=2, sort_keys=True))
if trajectory_status != "PASS":
    raise SystemExit("FAIL_TRAJECTORY_COMPARABILITY")
PY

echo "PASS_DIAGNOSTIC_N_CPU_MOE_PARETO_SWEEP"
echo "outputs: $out"
