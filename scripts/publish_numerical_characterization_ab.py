"""Publish the bounded A+B evidence without model/build/cache or verbose private logs."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

from tesy.numerical_characterization_ab import analyze_a, analyze_b


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(repo: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(repo), *args], text=True).strip()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True, type=Path)
    parser.add_argument("--a-root", required=True, type=Path)
    parser.add_argument("--b-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    repo = args.repo.resolve()
    a_root = args.a_root.resolve()
    b_root = args.b_root.resolve()
    output = args.output.resolve()
    if output.exists():
        raise SystemExit(f"refusing to replace evidence: {output}")
    if git(repo, "status", "--porcelain"):
        raise SystemExit("measurement/publication requires clean Tesy worktree")
    a_build = json.loads((a_root / "build-provenance.json").read_text())
    b_build = json.loads((b_root / "build-provenance.json").read_text())
    if a_build["tesy_head"] != b_build["tesy_head"] or a_build["tesy_tree"] != b_build["tesy_tree"]:
        raise SystemExit("A/B measurement commit or tree differs")
    analysis = {
        "schema": "tesy.numerical_characterization_ab_analysis.v1",
        "A": analyze_a(repo, a_root),
        "B": analyze_b(repo, b_root),
        "tesy_n2_candidate_requalified": False,
        "pending_external_audit": True,
    }
    output.mkdir(parents=True)
    published: list[dict[str, object]] = []

    def record(path: Path, origin: str) -> None:
        published.append(
            {
                "path": str(path.relative_to(output)),
                "size_bytes": path.stat().st_size,
                "sha256": sha(path),
                "origin": origin,
            }
        )

    def copy(source: Path, relative: str) -> None:
        target = output / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        with source.open("rb") as src, target.open("xb") as dst:
            shutil.copyfileobj(src, dst)
        record(target, str(source))

    def write_json(relative: str, payload: dict, origin: str) -> None:
        target = output / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("x", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
        record(target, origin)

    def public_doctor(source: Path, relative: str) -> None:
        raw = json.loads(source.read_text())
        snap = raw["snapshot"]
        payload = {
            "schema": "tesy.numerical_characterization_public_doctor.v1",
            "reference_check": raw["reference_check"],
            "snapshot": {
                key: snap[key]
                for key in (
                    "cpu",
                    "gpu",
                    "gpu_compute_processes",
                    "memory",
                    "virtualization",
                    "disk",
                    "platform",
                )
            },
            "excluded": ["storage_topology mountpoint enumeration", "raw system details"],
        }
        write_json(relative, payload, str(source) + " (redacted)")

    for name in (
        "raw.json",
        "down-matrix-raw.json",
        "build-provenance.json",
        "runtime-provenance.json",
        "resource-summary.json",
        "resources.jsonl",
        "argv.json",
    ):
        copy(a_root / name, f"A/{name}")
    for arm in ("C_xC", "C_xG", "G_xC", "G_xG"):
        for repeat in (1, 2):
            name = f"{arm}-r{repeat}.f32"
            copy(a_root / name, f"A/{name}")
    public_doctor(a_root / "doctor.json", "A/doctor-public.json")
    a_lines = (a_root / "tool.stderr.txt").read_text().splitlines()
    selected_a = [
        line
        for line in a_lines
        if any(
            fragment in line
            for fragment in (
                "vertical diagnostic slot=",
                "vertical diagnostic layer=2",
                "vertical FFN parity token=0 layer=2",
                "vertical logits failure token=0",
                "vertical event layer=2",
                "segmented-stage replay bitwise FFN=1",
            )
        )
    ]
    (output / "A/tool-excerpt.log").write_text("\n".join(selected_a) + "\n")
    record(output / "A/tool-excerpt.log", str(a_root / "tool.stderr.txt") + " (filtered)")

    copy(b_root / "build-provenance.json", "B/build-provenance.json")
    public_doctor(b_root / "doctor.json", "B/doctor-public.json")
    for label in ("historical", "code"):
        for repeat in (1, 2):
            for ngl in (0, 12):
                key = f"{label}-r{repeat}-ngl{ngl}"
                run = b_root / key
                for name in (
                    "P.f32",
                    "D.f32",
                    "raw.json",
                    "argv.json",
                    "runtime-provenance.json",
                    "resource-summary.json",
                    "resources.jsonl",
                ):
                    copy(run / name, f"B/{key}/{name}")
                lines = (run / "stderr.txt").read_text().splitlines()
                placement = [
                    line
                    for line in lines
                    if (
                        "load_tensors: layer " in line
                        or "load_tensors: offloading " in line
                        or "load_tensors: offloaded " in line
                    )
                ]
                target = output / "B" / key / "stderr.txt"
                target.write_text("\n".join(placement) + "\n")
                record(target, str(run / "stderr.txt") + " (placement excerpt)")

    write_json("analysis.json", analysis, "independent Python recomputation")
    manifest = {
        "schema": "tesy.numerical_characterization_ab_evidence_manifest.v1",
        "classification": "MEASURED_NUMERICAL_DIAGNOSTIC_NO_CONTRACT_CHANGE",
        "measurement_commit": a_build["tesy_head"],
        "measurement_tree": a_build["tesy_tree"],
        "analysis_commit": git(repo, "rev-parse", "HEAD"),
        "analysis_tree": git(repo, "rev-parse", "HEAD^{tree}"),
        "protocol_path": "research/NUMERICAL-CHARACTERIZATION-AB-PROTOCOL-20260925.md",
        "a_root": str(a_root.relative_to(repo)),
        "b_root": str(b_root.relative_to(repo)),
        "published_files": published,
        "failed_roots_preserved_local_only": [
            "results/numerical-characterization-a-20260925T004600Z/",
            "results/numerical-characterization-publication-attempt-20260925T005100Z/",
        ],
        "not_published": [
            "model weights, binaries, build products, caches",
            "verbose native stderr (only relevant diagnostic/placement excerpts published)",
            "unredacted doctor mountpoint enumeration",
        ],
        "pending_external_audit": True,
    }
    (output / "evidence-manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    )
    # Verify that the public bundle alone can recompute A+B; N2 sidecars stay in repo.
    if analyze_a(repo, output / "A") != analysis["A"]:
        raise SystemExit("published A differs from local analysis")
    if analyze_b(repo, output / "B") != analysis["B"]:
        raise SystemExit("published B differs from local analysis")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
