from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any


class TimingPilotPublicationError(ValueError):
    pass


_SELECTED_FILES = (
    "pilot-summary.json",
    "capacity-summary.json",
    "source-capacity.json",
    "admission-context.json",
    "build-provenance.json",
    "model.json",
    "backend.json",
    "tesy-head.txt",
    "llama-head.txt",
    "server-sha256.txt",
    "fit-tool-sha256.txt",
    "prompt-sha256.txt",
)


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise TimingPilotPublicationError(f"cannot read JSON {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise TimingPilotPublicationError(f"JSON artifact must be an object: {path}")
    return payload


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _git_branch() -> str:
    try:
        return subprocess.check_output(
            ["git", "branch", "--show-current"],
            text=True,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return ""


def _validate_campaign(root: Path) -> tuple[dict[str, Any], ...]:
    if not root.is_dir():
        raise TimingPilotPublicationError(f"missing campaign directory: {root}")
    if (root / "failure.json").exists():
        raise TimingPilotPublicationError("refusing to publish failed timing pilot")

    for name in _SELECTED_FILES:
        if not (root / name).is_file():
            raise TimingPilotPublicationError(f"missing required artifact: {name}")
    if not (root / "doctor.json").is_file():
        raise TimingPilotPublicationError("missing required artifact: doctor.json")

    pilot = _load_json(root / "pilot-summary.json")
    capacity = _load_json(root / "capacity-summary.json")
    source = _load_json(root / "source-capacity.json")
    admission = _load_json(root / "admission-context.json")
    build = _load_json(root / "build-provenance.json")
    model = _load_json(root / "model.json")
    backend = _load_json(root / "backend.json")
    doctor = _load_json(root / "doctor.json")

    if pilot.get("schema") != "tesy.stock_placement_timing_pilot.v1":
        raise TimingPilotPublicationError("unexpected pilot-summary schema")
    if pilot.get("classification") != "MEASURED_STOCK_PLACEMENT_PILOT_DIAGNOSTIC":
        raise TimingPilotPublicationError("unexpected pilot classification")
    expected = ["auto-fit-frozen", "n-cpu-moe-12", "n-cpu-moe-24"]
    if pilot.get("order") != expected:
        raise TimingPilotPublicationError("unexpected pilot placement order")
    trajectory = pilot.get("trajectory_comparability")
    if not isinstance(trajectory, dict) or trajectory.get("status") != "PASS":
        raise TimingPilotPublicationError("trajectory comparability did not PASS")
    if pilot.get("next_gate") != "MANUAL_REVIEW_REQUIRED":
        raise TimingPilotPublicationError("pilot must stop at manual review")
    observations = pilot.get("observations")
    if not isinstance(observations, list) or len(observations) != 3:
        raise TimingPilotPublicationError("pilot must contain exactly three observations")
    for row in observations:
        if not isinstance(row, dict):
            raise TimingPilotPublicationError("pilot observation must be an object")
        if row.get("runtime_provenance_status") != "PASS":
            raise TimingPilotPublicationError("runtime provenance did not PASS")
        if row.get("predicted_n") != 64:
            raise TimingPilotPublicationError("pilot observation is not 64 tokens")
        if row.get("peak_process_swap_bytes") != 0:
            raise TimingPilotPublicationError("pilot observation used process swap")
        if row.get("gpu_failed_samples") != 0:
            raise TimingPilotPublicationError(
                "pilot observation has incomplete GPU telemetry"
            )
        if not row.get("placement_log_lines"):
            raise TimingPilotPublicationError("pilot observation lacks placement evidence")

    if capacity.get("schema") != "tesy.timing_pilot_capacity_gate.v1":
        raise TimingPilotPublicationError("unexpected capacity-summary schema")
    if capacity.get("status") != "PASS":
        raise TimingPilotPublicationError("timing pilot capacity gate did not PASS")
    if source.get("schema") != "tesy.timing_pilot_source_capacity.v1":
        raise TimingPilotPublicationError("unexpected source-capacity schema")
    if admission.get("campaign_mode") != "timing-pilot":
        raise TimingPilotPublicationError("campaign was not timing-pilot mode")
    if build.get("status") != "PASS":
        raise TimingPilotPublicationError("build provenance did not PASS")
    if model.get("status") != "PASS":
        raise TimingPilotPublicationError("model verification did not PASS")
    if backend.get("status") != "PASS":
        raise TimingPilotPublicationError("backend provenance did not PASS")
    if doctor.get("reference_check", {}).get("status") != "PASS":
        raise TimingPilotPublicationError("reference host identity did not PASS")

    if (root / "tesy-status.txt").read_text(encoding="utf-8"):
        raise TimingPilotPublicationError("campaign Tesy worktree was dirty")
    if (root / "llama-status.txt").read_text(encoding="utf-8"):
        raise TimingPilotPublicationError("campaign llama.cpp worktree was dirty")

    return pilot, capacity, source, admission, build, model, backend, doctor



def _validate_raw_observations(root: Path, pilot: dict[str, Any]) -> None:
    expected = [
        ("auto-fit-frozen", root / "01-auto-fit"),
        ("n-cpu-moe-12", root / "02-n12"),
        ("n-cpu-moe-24", root / "03-n24"),
    ]
    observations = pilot["observations"]
    by_placement = {row["placement_id"]: row for row in observations}
    raw_hashes: set[str] = set()

    for placement_id, run_dir in expected:
        if not run_dir.is_dir():
            raise TimingPilotPublicationError(
                f"missing raw run directory for {placement_id}: {run_dir}"
            )
        for name in (
            "run-metadata.json",
            "request.json",
            "resource-summary.json",
            "runtime-provenance.json",
            "token-sha256.txt",
            "placement.txt",
            "server-command.txt",
            "pre-run-resources.json",
            "pre-run-capacity.json",
            "server-ready.json",
            "resources.jsonl",
            "server.stdout.txt",
            "server.stderr.txt",
            "health.json",
        ):
            if not (run_dir / name).is_file():
                raise TimingPilotPublicationError(
                    f"missing raw run artifact for {placement_id}: {name}"
                )

        meta = _load_json(run_dir / "run-metadata.json")
        request = _load_json(run_dir / "request.json")
        resources = _load_json(run_dir / "resource-summary.json")
        runtime = _load_json(run_dir / "runtime-provenance.json")
        pre_run = _load_json(run_dir / "pre-run-resources.json")
        pre_capacity = _load_json(run_dir / "pre-run-capacity.json")
        ready = _load_json(run_dir / "server-ready.json")
        command = (run_dir / "server-command.txt").read_text(
            encoding="utf-8"
        ).strip()
        placement_lines = [
            line.strip()
            for line in (run_dir / "placement.txt").read_text(
                encoding="utf-8"
            ).splitlines()
            if line.strip()
        ]
        token_hash = (run_dir / "token-sha256.txt").read_text(
            encoding="utf-8"
        ).strip()

        if meta.get("schema") != "tesy.stock_placement_run.v1":
            raise TimingPilotPublicationError(
                f"unexpected run metadata schema for {placement_id}"
            )
        if meta.get("placement_id") != placement_id:
            raise TimingPilotPublicationError(
                f"raw placement identity mismatch for {placement_id}"
            )
        if pre_run.get("schema") != "tesy.timing_pilot_pre_run_resources.v1":
            raise TimingPilotPublicationError(
                f"unexpected pre-run resource schema for {placement_id}"
            )
        if pre_capacity.get("schema") != "tesy.placement_capacity_estimate.v1":
            raise TimingPilotPublicationError(
                f"unexpected pre-run capacity schema for {placement_id}"
            )
        if pre_capacity.get("placement_id") != placement_id:
            raise TimingPilotPublicationError(
                f"raw pre-run capacity identity mismatch for {placement_id}"
            )
        if runtime.get("schema") != "tesy.runtime_backend_provenance.v1":
            raise TimingPilotPublicationError(
                f"unexpected runtime provenance schema for {placement_id}"
            )
        if runtime.get("status") != "PASS":
            raise TimingPilotPublicationError(
                f"raw runtime provenance failed for {placement_id}"
            )
        if request.get("schema") != "tesy.stock_server_request.v1":
            raise TimingPilotPublicationError(
                f"unexpected request schema for {placement_id}"
            )
        tokens = request.get("generated_token_ids")
        if not isinstance(tokens, list) or len(tokens) != 64:
            raise TimingPilotPublicationError(
                f"raw generated token IDs are not exactly 64 for {placement_id}"
            )
        if request.get("generated_token_count") != 64:
            raise TimingPilotPublicationError(
                f"raw token count is not 64 for {placement_id}"
            )
        if request.get("timings", {}).get("predicted_n") != 64:
            raise TimingPilotPublicationError(
                f"raw predicted_n is not 64 for {placement_id}"
            )
        if resources.get("gpu_failed_samples") != 0:
            raise TimingPilotPublicationError(
                f"raw GPU telemetry incomplete for {placement_id}"
            )
        if resources.get("peak_process_swap_bytes") != 0:
            raise TimingPilotPublicationError(
                f"raw process swap observed for {placement_id}"
            )
        if not pre_capacity.get("admitted"):
            raise TimingPilotPublicationError(
                f"raw pre-run capacity rejected {placement_id}"
            )
        if not placement_lines:
            raise TimingPilotPublicationError(
                f"raw placement evidence empty for {placement_id}"
            )
        if not token_hash:
            raise TimingPilotPublicationError(
                f"raw token hash missing for {placement_id}"
            )
        computed_hash = hashlib.sha256(
            json.dumps(tokens, separators=(",", ":")).encode()
        ).hexdigest()
        if token_hash != computed_hash:
            raise TimingPilotPublicationError(
                f"raw token hash does not match token IDs for {placement_id}"
            )
        raw_hashes.add(computed_hash)

        row = by_placement.get(placement_id)
        if row is None:
            raise TimingPilotPublicationError(
                f"summary missing placement {placement_id}"
            )
        timings = request["timings"]
        checks = {
            "n_cpu_moe": meta.get("n_cpu_moe"),
            "server_command": command,
            "server_ready_ms": ready.get("server_ready_ms"),
            "pre_run_gpu_free_bytes": pre_run["gpu"]["memory_free_bytes"],
            "pre_run_gpu_temperature_c": pre_run["gpu"]["temperature_c"],
            "pre_run_mem_available_bytes": pre_run["memory"]["available_bytes"],
            "pre_run_capacity_gpu_required_mib": pre_capacity["gpu_required_mib"],
            "pre_run_capacity_host_required_mib": pre_capacity["host_required_mib"],
            "ttft_ms": request["ttft_ms"],
            "request_wall_ms": request["request_wall_ms"],
            "prompt_n": timings["prompt_n"],
            "prompt_ms": timings["prompt_ms"],
            "prompt_tps": timings["prompt_per_second"],
            "predicted_n": timings["predicted_n"],
            "predicted_ms": timings["predicted_ms"],
            "decode_tps": timings["predicted_per_second"],
            "resource_samples": resources["samples"],
            "gpu_valid_samples": resources["gpu_valid_samples"],
            "peak_gpu_memory_bytes": resources["peak_gpu_memory_used_bytes"],
            "min_observed_gpu_free_bytes": resources[
                "min_observed_gpu_free_bytes"
            ],
            "peak_process_rss_bytes": resources["peak_process_rss_bytes"],
            "peak_process_swap_bytes": resources["peak_process_swap_bytes"],
            "min_mem_available_bytes": resources["min_mem_available_bytes"],
            "min_swap_free_bytes": resources["min_swap_free_bytes"],
            "max_gpu_temperature_c": resources["max_gpu_temperature_c"],
            "max_gpu_power_w": resources["max_gpu_power_w"],
            "gpu_failed_samples": resources["gpu_failed_samples"],
            "runtime_provenance_status": runtime["status"],
            "placement_log_lines": placement_lines,
            "token_sha256": computed_hash,
        }
        for key, observed in checks.items():
            if row.get(key) != observed:
                raise TimingPilotPublicationError(
                    f"summary/raw mismatch for {placement_id} {key}: "
                    f"{row.get(key)!r} != {observed!r}"
                )

    if len(raw_hashes) != 1:
        raise TimingPilotPublicationError(
            "raw token trajectories differ across placements"
        )
    summary_hashes = pilot["trajectory_comparability"].get(
        "unique_token_trajectory_hashes"
    )
    if summary_hashes != sorted(raw_hashes):
        raise TimingPilotPublicationError(
            "summary trajectory hash does not match raw runs"
        )

def _raw_manifest(root: Path) -> dict[str, dict[str, int | str]]:
    artifacts: dict[str, dict[str, int | str]] = {}
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        size = path.stat().st_size
        if size > 16 * 1024 * 1024:
            raise TimingPilotPublicationError(
                f"unexpected timing-pilot artifact larger than 16 MiB: {path}"
            )
        artifacts[str(path.relative_to(root))] = {
            "bytes": size,
            "sha256": _sha256(path),
        }
    return artifacts


def _host_summary(doctor: dict[str, Any]) -> dict[str, Any]:
    snapshot = doctor["snapshot"]
    gpus = snapshot["gpu"]["gpus"]
    return {
        "schema": "tesy.timing_pilot_host_summary.v1",
        "classification": "MEASURED_HOST_STATE",
        "reference_status": doctor["reference_check"]["status"],
        "profile_id": doctor["reference_check"]["profile_id"],
        "cpu": snapshot["cpu"],
        "gpu": gpus[0] if len(gpus) == 1 else gpus,
        "memory": snapshot["memory"],
        "gpu_compute_processes": snapshot["gpu_compute_processes"],
        "claim_boundary": (
            "Campaign-start host state summary only. Per-observation runtime "
            "resources are recorded in pilot-summary.json."
        ),
    }


def _result_markdown(pilot: dict[str, Any], source: dict[str, Any]) -> str:
    rows = [
        "# stock placement timing pilot",
        "",
        f"Capacity evidence commit: `{pilot['capacity_evidence_commit']}`.",
        "",
        "Classification: `MEASURED_STOCK_PLACEMENT_PILOT_DIAGNOSTIC`.",
        "",
        "| Placement | TTFT ms | Prompt tok/s | Decode tok/s | Peak VRAM MiB | "
        "RSS GiB | Swap MiB | Temp °C |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for obs in pilot["observations"]:
        rows.append(
            "| {placement} | {ttft:.2f} | {prompt:.2f} | {decode:.3f} | "
            "{vram:.1f} | {rss:.2f} | {swap:.1f} | {temp:.1f} |".format(
                placement=obs["placement_id"],
                ttft=obs["ttft_ms"],
                prompt=obs["prompt_tps"],
                decode=obs["decode_tps"],
                vram=obs["peak_gpu_memory_bytes"] / (1024 * 1024),
                rss=obs["peak_process_rss_bytes"] / (1024**3),
                swap=obs["peak_process_swap_bytes"] / (1024 * 1024),
                temp=obs["max_gpu_temperature_c"],
            )
        )

    trajectory = pilot["trajectory_comparability"]
    rows.extend(
        [
            "",
            "Trajectory comparability: `PASS`; all three observations produced "
            "the same 64-token trajectory SHA-256 "
            f"`{trajectory['unique_token_trajectory_hashes'][0]}`.",
            "",
            "Pilot placements were selected from published capacity evidence; "
            f"admitted manual points there were {source['admitted_n_cpu_moe']}.",
            "",
            "This is one observation per placement. It is diagnostic only: no "
            "confirmatory performance winner or Pareto frontier is claimed.",
            "",
            "No physical PCIe/NVMe traffic, Tesy speedup, >RAM execution or "
            "scientific novelty claim follows.",
            "",
        ]
    )
    return "\n".join(rows)


def publish_timing_pilot(campaign: Path, destination: Path) -> dict[str, Any]:
    root = campaign.expanduser().resolve(strict=True)
    if destination.exists():
        raise TimingPilotPublicationError(
            f"refusing to replace publication directory: {destination}"
        )

    (
        pilot,
        _capacity,
        source,
        _admission,
        build,
        _model,
        _backend,
        doctor,
    ) = _validate_campaign(root)
    _validate_raw_observations(root, pilot)
    raw = _raw_manifest(root)

    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.mkdir()

    for name in _SELECTED_FILES:
        shutil.copy2(root / name, destination / name)

    host = _host_summary(doctor)
    (destination / "host-summary.json").write_text(
        json.dumps(host, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    manifest = {
        "schema": "tesy.stock_placement_timing_pilot_publication.v1",
        "classification": "MEASURED_STOCK_PLACEMENT_PILOT_DIAGNOSTIC",
        "source_campaign": root.name,
        "source_output_root": str(root),
        "publication_branch": _git_branch(),
        "capacity_evidence_commit": pilot["capacity_evidence_commit"],
        "observation_count": len(pilot["observations"]),
        "trajectory_status": pilot["trajectory_comparability"]["status"],
        "build_provenance_status": build["status"],
        "next_gate": pilot["next_gate"],
        "raw_artifacts": raw,
        "published_artifacts": sorted(
            [*_SELECTED_FILES, "host-summary.json", "RESULT.md", "publication-manifest.json"]
        ),
        "claim_boundary": (
            "Derived pilot publication only. Raw request streams, server logs, "
            "resource samples and placement files remain local and are identified "
            "by SHA-256 in raw_artifacts. No confirmatory winner/Pareto, physical "
            "PCIe/NVMe, Tesy speedup, >RAM or novelty claim follows."
        ),
    }
    (destination / "publication-manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (destination / "RESULT.md").write_text(
        _result_markdown(pilot, source),
        encoding="utf-8",
    )
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("campaign", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()

    manifest = publish_timing_pilot(args.campaign, args.destination)
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
