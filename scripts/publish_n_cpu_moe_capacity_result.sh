#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 2 ]]; then
  echo "usage: $0 CAPACITY_CAMPAIGN_ROOT PUBLISH_DIR" >&2
  exit 2
fi

campaign="$1"
publish_dir="$2"

[[ -d "$campaign" ]] || { echo "missing campaign directory: $campaign" >&2; exit 1; }
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
  fit-tool-version.txt
  admission-context.json
  auto-fit.json
  auto-fit.stdout.txt
  auto-fit.stderr.txt
  capacity-summary.json
)

for rel in "${required[@]}"; do
  [[ -f "$campaign/$rel" ]] || {
    echo "missing required capacity artifact: $campaign/$rel" >&2
    exit 1
  }
done

[[ -d "$campaign/capacity" ]] || {
  echo "missing capacity artifact directory: $campaign/capacity" >&2
  exit 1
}

if find "$campaign" -type l -print -quit | grep -q .; then
  echo "refusing capacity publication containing symlinks" >&2
  exit 1
fi

python3 - "$campaign" <<'PY'
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])

doctor = json.loads((root / "doctor.json").read_text(encoding="utf-8"))
reference = doctor.get("reference_check")
if not isinstance(reference, dict) or reference.get("status") != "PASS":
    raise SystemExit("reference host identity did not PASS")
snapshot = doctor.get("snapshot")
virtualization = snapshot.get("virtualization") if isinstance(snapshot, dict) else None
if (
    not isinstance(virtualization, dict)
    or virtualization.get("status") != "PHYSICAL"
):
    raise SystemExit("capacity publication requires virtualization=PHYSICAL")

admission = json.loads((root / "admission-context.json").read_text(encoding="utf-8"))
if admission.get("schema") != "tesy.placement_admission_context.v1":
    raise SystemExit("unexpected admission-context schema")
if admission.get("campaign_mode") != "capacity-only":
    raise SystemExit("publication helper accepts capacity-only campaigns only")

build = json.loads((root / "build-provenance.json").read_text(encoding="utf-8"))
if build.get("schema") != "tesy.llama_build_provenance.v1":
    raise SystemExit("unexpected build-provenance schema")
if build.get("status") != "PASS":
    raise SystemExit("build provenance did not PASS")

capacity = json.loads((root / "capacity-summary.json").read_text(encoding="utf-8"))
if capacity.get("schema") != "tesy.n_cpu_moe_capacity_gate.v1":
    raise SystemExit("unexpected capacity-summary schema")

auto_fit = json.loads((root / "auto-fit.json").read_text(encoding="utf-8"))
if auto_fit.get("schema") != "tesy.llama_fit_args.v1":
    raise SystemExit("unexpected auto-fit schema")
if auto_fit.get("ctx_size") != 4096:
    raise SystemExit("auto-fit did not preserve context 4096")

if (root / "tesy-status.txt").read_text(encoding="utf-8"):
    raise SystemExit("campaign Tesy worktree was dirty")
if (root / "llama-status.txt").read_text(encoding="utf-8"):
    raise SystemExit("campaign llama.cpp worktree was dirty")

expected = {0, 4, 8, 12, 16, 20, 24}
observed = {
    int(path.stem[1:])
    for path in (root / "capacity").glob("n??.json")
}
if observed != expected:
    raise SystemExit(f"capacity point set mismatch: {sorted(observed)!r}")

for path in root.rglob("*"):
    if path.is_file() and path.stat().st_size > 4 * 1024 * 1024:
        raise SystemExit(f"unexpected large capacity artifact: {path}")
PY

mkdir -p "$(dirname "$publish_dir")"
cp -a "$campaign" "$publish_dir"

cat >"$publish_dir/.gitattributes" <<'EOF'
# Raw llama-fit-params stdout is preserved byte-for-byte as evidence.
# The upstream tool emits a trailing space before newline; this is not a
# publication formatting defect and must not be normalized.
auto-fit.stdout.txt -whitespace
capacity/*.stdout.txt -whitespace
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

capacity = json.loads((dest / "capacity-summary.json").read_text(encoding="utf-8"))
build = json.loads((dest / "build-provenance.json").read_text(encoding="utf-8"))
doctor = json.loads((dest / "doctor.json").read_text(encoding="utf-8"))
auto_fit = json.loads((dest / "auto-fit.json").read_text(encoding="utf-8"))

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
    "schema": "tesy.n_cpu_moe_capacity_publication.v1",
    "classification": "SOURCE_BACKED_CAPACITY_GATE",
    "source_campaign": source.name,
    "source_output_root": str(source),
    "publication_branch": branch,
    "build_provenance_status": build["status"],
    "physical_host_status": doctor["snapshot"]["virtualization"]["status"],
    "admitted_n_cpu_moe": capacity["admitted_n_cpu_moe"],
    "rejected_n_cpu_moe": capacity["rejected_n_cpu_moe"],
    "performance_gate": capacity["performance_gate"],
    "raw_artifacts": artifacts,
    "claim_boundary": (
        "Capacity-only publication. Estimates are source-backed projected "
        "model/context/compute memory, not measured runtime VRAM/RAM traffic. "
        "No timing, Tesy speedup, physical PCIe/NVMe, >RAM or novelty claim follows."
    ),
}
(dest / "publication-manifest.json").write_text(
    json.dumps(manifest, indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
)

auto_argv = " ".join(auto_fit["argv"])
rows = [
    "# n-cpu-moe capacity-only diagnostic",
    "",
    f"Campaign: `{source.name}`",
    "",
    "Classification: `SOURCE_BACKED_CAPACITY_GATE`.",
    "",
    f"Build provenance: `{build['status']}`.",
    "",
    "Physical host verification: `PASS` (`virtualization=PHYSICAL`).",
    "",
    f"Frozen stock auto-fit argv: `{auto_argv}`.",
    "",
    "Admitted manual N values: "
    + (", ".join(map(str, capacity["admitted_n_cpu_moe"])) or "none")
    + ".",
    "",
    "Rejected manual N values: "
    + (", ".join(map(str, capacity["rejected_n_cpu_moe"])) or "none")
    + ".",
    "",
    f"Performance gate: `{capacity['performance_gate']}`.",
    "",
    "This campaign stops before timed llama-server observations. "
    "No rejected point was deliberately loaded to induce OOM.",
    "",
    "The estimates are source-backed memory projections, not measured peak "
    "VRAM/RAM or physical transfer traffic. No Tesy speedup, >RAM or novelty "
    "claim follows.",
    "",
]
(dest / "RESULT.md").write_text("\n".join(rows), encoding="utf-8")
PY

echo "PASS_CAPACITY_PUBLICATION_PREPARED"
echo "publication: $publish_dir"
