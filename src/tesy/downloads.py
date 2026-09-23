from __future__ import annotations

import os
import shutil
import stat
import subprocess
from pathlib import Path
from typing import Any


class DownloadPlanError(ValueError):
    pass


def build_download_plan(model: dict[str, Any], destination: Path) -> dict[str, Any]:
    artifact = model.get("artifact")
    if not isinstance(artifact, dict):
        raise DownloadPlanError("model has no artifact object")

    repository = artifact.get("repository")
    revision = artifact.get("revision")
    filename = artifact.get("filename")
    locked = (repository, revision, filename)
    if not all(isinstance(value, str) and value for value in locked):
        raise DownloadPlanError(
            "model artifact is not fully locked with repository/revision/filename"
        )

    requested = destination.expanduser()
    if requested.exists():
        info = requested.lstat()
        if stat.S_ISLNK(info.st_mode):
            raise DownloadPlanError("destination must not be a symlink")
        if not stat.S_ISDIR(info.st_mode):
            raise DownloadPlanError("destination must be a directory")

    command = [
        "hf",
        "download",
        repository,
        filename,
        "--revision",
        revision,
        "--local-dir",
        str(requested),
    ]

    return {
        "schema": "tesy.model_download_plan.v1",
        "classification": "LOCK_DERIVED_COMMAND",
        "model_id": model.get("id"),
        "dry_run": True,
        "command": command,
        "expected_artifact": {
            "filename": filename,
            "bytes": artifact.get("bytes"),
            "sha256": artifact.get("sha256"),
        },
        "claim_boundary": (
            "Planning only. No network access or model download occurs unless "
            "the caller explicitly requests execution and confirms it."
        ),
    }


def execute_download_plan(plan: dict[str, Any], yes: bool) -> int:
    if not yes:
        raise DownloadPlanError("execution requires explicit --yes confirmation")

    command = plan.get("command")
    if (
        not isinstance(command, list)
        or not command
        or not all(isinstance(item, str) and item for item in command)
    ):
        raise DownloadPlanError("invalid download command")
    if command[0] != "hf":
        raise DownloadPlanError("only the locked hf download helper is admitted")
    if shutil.which("hf") is None:
        raise DownloadPlanError(
            "hf command not found; install/activate huggingface_hub first"
        )

    completed = subprocess.run(
        command,
        check=False,
        env={**os.environ, "LC_ALL": "C"},
    )
    return completed.returncode
