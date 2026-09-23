#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 2 ]]; then
  echo "usage: $0 TIMING_PILOT_ROOT PUBLISH_DIR" >&2
  exit 2
fi

campaign="$1"
publish_dir="$2"

[[ -d "$campaign" ]] || { echo "missing pilot directory: $campaign" >&2; exit 1; }
if [[ -e "$publish_dir" ]]; then
  echo "refusing to replace publication directory: $publish_dir" >&2
  exit 1
fi

required=(
  model.json
  doctor.json
  backend.json
  build-provenance.json
  tesy-head.txt
  tesy-status.txt
  llama-head.txt
  llama-status.txt
  server-sha256.txt
  fit-tool-sha256.txt
  prompt-sha256.txt
  auto-fit.json
  auto-fit.stdout.txt
  auto-fit.stderr.txt
  pilot-summary.json
)

for rel in "${required[@]}"; do
  [[ -f "$campaign/$rel" ]] || {
    echo "missing required timing-pilot artifact: $campaign/$rel" >&2
    exit 1
  }
done

if find "$campaign" -type l -print -quit | grep -q .; then
  echo "refusing timing-pilot publication containing symlinks" >&2
  exit 1
fi

python3 - "$campaign" <<'PY'
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])

if (root / "tesy-status.txt").read_text(encoding="utf-8"):
    raise SystemExit("pilot Tesy worktree was dirty")
if (root / "llama-status.txt").read_text(encoding="utf-8"):
    raise SystemExit("pilot llama.cpp worktree was dirty")

build = json.loads((root / "build-provenance.json").read_text(encoding="utf-8"))
if build.get("schema") != "tesy.llama_build_provenance.v1":
    raise SystemExit("unexpected build-provenance schema")
if build.get("status") != "PASS":
    raise SystemExit("build provenance did not PASS")

auto = json.loads((root / "auto-fit.json").read_text(encoding="utf-8"))
if auto.get("schema") != "tesy.llama_fit_args.v1" or auto.get("ctx_size") != 4096:
    raise SystemExit("invalid frozen auto-fit placement")

summary = json.loads((root / "pilot-summary.json").read_text(encoding="utf-8"))
if summary.get("schema") != "tesy.stock_placement_timing_pilot.v1":
    raise SystemExit("unexpected pilot-summary schema")
if summary.get("classification") != "MEASURED_SINGLE_OBSERVATION_PILOT_DIAGNOSTIC":
    raise SystemExit("unexpected pilot classification")
trajectory = summary.get("trajectory_comparability", {})
if trajectory.get("status") != "PASS":
    raise SystemExit("trajectory comparability did not PASS")
if trajectory.get("required_token_count") != 64:
    raise SystemExit("pilot did not preserve the 64-token contract")
if summary.get("next_gate") != "MANUAL_REVIEW_REQUIRED":
    raise SystemExit("pilot must stop at manual review")

expected = ["auto-fit-frozen", "n-cpu-moe-12", "n-cpu-moe-24"]
placements = summary.get("placements")
if not isinstance(placements, list):
    raise SystemExit("pilot placements must be a list")
if [row.get("placement_id") for row in placements] != expected:
    raise SystemExit("unexpected pilot placement order")
if any(row.get("observation_count") != 1 for row in placements):
    raise SystemExit("pilot must contain exactly one observation per placement")
if any(row.get("peak_process_swap_bytes") != 0 for row in placements):
    raise SystemExit("pilot contains process swap")

expected_runs = {
    "auto-fit-frozen": root / "runs" / "01-auto-fit-frozen",
    "n-cpu-moe-12": root / "runs" / "02-n-cpu-moe-12",
    "n-cpu-moe-24": root / "runs" / "03-n-cpu-moe-24",
}
summary_by_placement = {row["placement_id"]: row for row in placements}
token_hashes = set()

for placement, run_dir in expected_runs.items():
    if not run_dir.is_dir():
        raise SystemExit(f"missing pilot run directory: {run_dir}")

    required_run_files = (
        "pre-run-resources.json",
        "run-metadata.json",
        "server-command.txt",
        "server.stdout.txt",
        "server.stderr.txt",
        "resources.jsonl",
        "health.json",
        "runtime-provenance.json",
        "server-ready.json",
        "request.json",
        "token-sha256.txt",
        "resource-summary.json",
        "placement.txt",
    )
    for name in required_run_files:
        if not (run_dir / name).is_file():
            raise SystemExit(f"missing run artifact for {placement}: {name}")

    for suffix in ("json", "stdout.txt", "stderr.txt"):
        capacity_path = root / "capacity" / f"{placement}.{suffix}"
        if not capacity_path.is_file():
            raise SystemExit(f"missing capacity artifact: {capacity_path}")

    runtime = json.loads(
        (run_dir / "runtime-provenance.json").read_text(encoding="utf-8")
    )
    if runtime.get("schema") != "tesy.runtime_backend_provenance.v1":
        raise SystemExit(f"unexpected runtime provenance schema for {placement}")
    if runtime.get("status") != "PASS":
        raise SystemExit(f"runtime provenance failed for {placement}")

    request = json.loads((run_dir / "request.json").read_text(encoding="utf-8"))
    if request.get("schema") != "tesy.stock_server_request.v1":
        raise SystemExit(f"unexpected request schema for {placement}")
    if request.get("generated_token_count") != 64:
        raise SystemExit(f"invalid token count for {placement}")

    resources = json.loads(
        (run_dir / "resource-summary.json").read_text(encoding="utf-8")
    )
    if resources.get("schema") != "tesy.stock_placement_pilot_resources.v1":
        raise SystemExit(f"unexpected resource schema for {placement}")
    if resources.get("peak_process_swap_bytes") != 0:
        raise SystemExit(f"process swap observed for {placement}")
    if resources.get("gpu_failed_samples") != 0:
        raise SystemExit(f"GPU telemetry failure for {placement}")

    capacity = json.loads(
        (root / "capacity" / f"{placement}.json").read_text(encoding="utf-8")
    )
    if capacity.get("schema") != "tesy.placement_capacity_estimate.v1":
        raise SystemExit(f"unexpected capacity schema for {placement}")
    if capacity.get("placement_id") != placement or not capacity.get("admitted"):
        raise SystemExit(f"capacity admission failed for {placement}")

    token_hash = (run_dir / "token-sha256.txt").read_text(
        encoding="utf-8"
    ).strip()
    if not token_hash:
        raise SystemExit(f"missing token hash for {placement}")
    token_hashes.add(token_hash)

    row = summary_by_placement[placement]
    timings = request["timings"]
    checks = {
        "ttft_ms": request["ttft_ms"],
        "request_wall_ms": request["request_wall_ms"],
        "prompt_tps": timings["prompt_per_second"],
        "decode_tps": timings["predicted_per_second"],
        "peak_gpu_memory_used_bytes": resources["peak_gpu_memory_used_bytes"],
        "min_observed_gpu_free_bytes": resources["min_observed_gpu_free_bytes"],
        "peak_process_rss_bytes": resources["peak_process_rss_bytes"],
        "peak_process_swap_bytes": resources["peak_process_swap_bytes"],
        "token_sha256": token_hash,
    }
    for key, observed in checks.items():
        if row.get(key) != observed:
            raise SystemExit(
                f"pilot summary mismatch for {placement} {key}: "
                f"{row.get(key)!r} != {observed!r}"
            )

if len(token_hashes) != 1:
    raise SystemExit("run token hashes are not identical")
summary_hashes = trajectory.get("unique_token_trajectory_hashes")
if summary_hashes != sorted(token_hashes):
    raise SystemExit("summary token hashes do not match run artifacts")

for path in root.rglob("*"):
    if path.is_file() and path.stat().st_size > 8 * 1024 * 1024:
        raise SystemExit(f"unexpected large timing-pilot artifact: {path}")
PY

mkdir -p "$(dirname "$publish_dir")"
cp -a "$campaign" "$publish_dir"

cat >"$publish_dir/.gitattributes" <<'EOF'
# Raw runtime/fitter logs are preserved byte-for-byte as evidence.
capacity/*.stdout.txt -whitespace
capacity/*.stderr.txt -whitespace
runs/*/server.stdout.txt -whitespace
runs/*/server.stderr.txt -whitespace
runs/*/placement.txt -whitespace
EOF

python3 - "$campaign" "$publish_dir" <<'PY'
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

source = Path(sys.argv[1]).resolve()
dest = Path(sys.argv[2])

summary = json.loads((dest / "pilot-summary.json").read_text(encoding="utf-8"))
build = json.loads((dest / "build-provenance.json").read_text(encoding="utf-8"))
auto = json.loads((dest / "auto-fit.json").read_text(encoding="utf-8"))

artifacts = {}
for path in sorted(p for p in source.rglob("*") if p.is_file()):
    h = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            h.update(chunk)
    artifacts[str(path.relative_to(source))] = {
        "bytes": path.stat().st_size,
        "sha256": h.hexdigest(),
    }

try:
    branch = subprocess.check_output(
        ["git", "branch", "--show-current"],
        text=True,
    ).strip()
except (OSError, subprocess.CalledProcessError):
    branch = ""

manifest = {
    "schema": "tesy.stock_placement_timing_pilot_publication.v1",
    "classification": "MEASURED_SINGLE_OBSERVATION_PILOT_DIAGNOSTIC",
    "source_campaign": source.name,
    "source_output_root": str(source),
    "publication_branch": branch,
    "build_provenance_status": build["status"],
    "placements": [row["placement_id"] for row in summary["placements"]],
    "trajectory_status": summary["trajectory_comparability"]["status"],
    "required_token_count": summary["trajectory_comparability"]["required_token_count"],
    "next_gate": summary["next_gate"],
    "raw_artifacts": artifacts,
    "claim_boundary": (
        "One fresh-process observation per placement. Published timings and sampled "
        "resources are diagnostic only: no stable ranking, Tesy speedup, physical "
        "PCIe/NVMe/DRAM traffic, >RAM or novelty claim follows."
    ),
}
(dest / "publication-manifest.json").write_text(
    json.dumps(manifest, indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
)

def mib(value: int) -> float:
    return value / (1024 * 1024)

def gib(value: int) -> float:
    return value / (1024**3)

rows = [
    "# stock placement timing pilot",
    "",
    f"Campaign: {source.name}",
    "",
    "Classification: MEASURED_SINGLE_OBSERVATION_PILOT_DIAGNOSTIC.",
    "",
    f"Build provenance: {build['status']}.",
    "",
    f"Frozen stock auto-fit argv: {' '.join(auto['argv'])}.",
    "",
    "Trajectory comparability: PASS for exactly 64 generated token IDs.",
    "",
    "| placement | TTFT ms | request wall ms | decode tok/s | peak GPU MiB | peak RSS GiB |",
    "|---|---:|---:|---:|---:|---:|",
]
for row in summary["placements"]:
    rows.append(
        "| {placement} | {ttft:.3f} | {wall:.3f} | {decode:.3f} | {gpu:.1f} | {rss:.3f} |".format(
            placement=row["placement_id"],
            ttft=row["ttft_ms"],
            wall=row["request_wall_ms"],
            decode=row["decode_tps"],
            gpu=mib(row["peak_gpu_memory_used_bytes"]),
            rss=gib(row["peak_process_rss_bytes"]),
        )
    )
rows += [
    "",
    "Each row is one fresh-process observation. The table is not a stable "
    "throughput/latency ranking and is not sufficient for statistical claims.",
    "",
    "The next gate is manual review. N=16/N=20 or repeated observations are "
    "authorized only if this pilot shows a trade-off worth resolving.",
    "",
    "No Tesy speedup, physical PCIe/NVMe/DRAM byte, >RAM or novelty claim follows.",
    "",
]
(dest / "RESULT.md").write_text("\n".join(rows), encoding="utf-8")
PY

echo "PASS_TIMING_PILOT_PUBLICATION_PREPARED"
echo "publication: $publish_dir"
