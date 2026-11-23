from __future__ import annotations

import json
import os
import stat
import subprocess
from pathlib import Path
from typing import Any

from tesy.models import sha256_file


class BackendError(ValueError):
    pass


def default_backend_lock_path() -> Path:
    env = os.environ.get("TESY_BACKEND_LOCK")
    if env:
        return Path(env)
    cwd = Path.cwd() / "configs" / "backends.lock.json"
    if cwd.exists():
        return cwd
    return Path(__file__).resolve().parents[2] / "configs" / "backends.lock.json"


def load_backend_lock(path: Path | None = None) -> dict[str, Any]:
    lock_path = (path or default_backend_lock_path()).resolve()
    try:
        payload = json.loads(lock_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BackendError(f"cannot read backend lock {lock_path}: {exc}") from exc
    if payload.get("schema") != "tesy.backends.lock.v1":
        raise BackendError("unsupported backend lock schema")
    backends = payload.get("backends")
    if not isinstance(backends, list):
        raise BackendError("backends must be a list")
    seen: set[str] = set()
    for backend in backends:
        if not isinstance(backend, dict):
            raise BackendError("backend entry must be an object")
        backend_id = backend.get("id")
        if not isinstance(backend_id, str) or not backend_id:
            raise BackendError("backend id must be a non-empty string")
        if backend_id in seen:
            raise BackendError(f"duplicate backend id: {backend_id}")
        seen.add(backend_id)
    return payload


def get_backend(lock: dict[str, Any], backend_id: str) -> dict[str, Any]:
    for backend in lock["backends"]:
        if backend["id"] == backend_id:
            return backend
    raise BackendError(f"unknown backend id: {backend_id}")


def _run(command: list[str], timeout_s: float = 10.0) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            env={**os.environ, "LC_ALL": "C"},
        )
    except FileNotFoundError as exc:
        return {"status": "NOT_AVAILABLE", "command": command, "error": str(exc)}
    except subprocess.TimeoutExpired:
        return {"status": "TIMEOUT", "command": command}
    return {
        "status": "OK" if completed.returncode == 0 else "ERROR",
        "returncode": completed.returncode,
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
        "command": command,
    }


def _regular_nonsymlink(path: Path, label: str) -> Path:
    requested = path.expanduser()
    try:
        info = requested.lstat()
    except OSError as exc:
        raise BackendError(f"cannot stat {label} {requested}: {exc}") from exc
    if stat.S_ISLNK(info.st_mode):
        raise BackendError(f"{label} must not be a symlink")
    resolved = requested.resolve(strict=True)
    if not stat.S_ISREG(resolved.stat().st_mode):
        raise BackendError(f"{label} must be a regular file")
    return resolved


def _source_state(source_dir: Path, expected_commit: str) -> dict[str, Any]:
    root = source_dir.expanduser().resolve(strict=True)
    head = _run(["git", "-C", str(root), "rev-parse", "HEAD"])
    status = _run(["git", "-C", str(root), "status", "--porcelain"])
    observed_head = head.get("stdout") if head["status"] == "OK" else None
    clean = status["status"] == "OK" and status.get("stdout", "") == ""
    exact = observed_head == expected_commit
    return {
        "path": str(root),
        "head": observed_head,
        "expected_head": expected_commit,
        "head_match": exact,
        "clean": clean,
        "probe_status": "PASS" if exact and clean else "FAIL",
    }


def probe_llama_cpp(
    binary: Path,
    source_dir: Path | None = None,
    backend_id: str = "llama-cpp-stock",
) -> dict[str, Any]:
    lock = load_backend_lock()
    backend = get_backend(lock, backend_id)
    expected_commit = backend.get("commit")
    if not isinstance(expected_commit, str) or len(expected_commit) != 40:
        raise BackendError("locked backend commit must be a 40-character SHA")

    resolved = _regular_nonsymlink(binary, "backend binary")
    if not os.access(resolved, os.X_OK):
        raise BackendError("backend binary is not executable")

    version = _run([str(resolved), "--version"])
    devices = _run([str(resolved), "--list-devices"])
    help_result = _run([str(resolved), "--help"])
    help_text = "\n".join(
        [help_result.get("stdout", ""), help_result.get("stderr", "")]
    )

    required_flags = backend.get("expected_features_to_probe", [])
    if not isinstance(required_flags, list) or not all(
        isinstance(flag, str) and flag for flag in required_flags
    ):
        raise BackendError("expected_features_to_probe must be a string list")
    flag_support = {flag: flag in help_text for flag in required_flags}

    commands_ok = all(
        result["status"] == "OK" for result in (version, devices, help_result)
    )
    features_ok = all(flag_support.values())
    source = (
        _source_state(source_dir, expected_commit)
        if source_dir is not None
        else None
    )

    if not commands_ok or not features_ok:
        status = "FAIL"
    elif source is None:
        status = "INCONCLUSIVE"
    elif source["probe_status"] != "PASS":
        status = "FAIL"
    else:
        status = "PASS"

    return {
        "schema": "tesy.backend_probe.v1",
        "classification": "MEASURED_LOCAL_PROVENANCE",
        "backend_id": backend_id,
        "status": status,
        "binary": {
            "path": str(resolved),
            "bytes": resolved.stat().st_size,
            "sha256": sha256_file(resolved),
        },
        "version": version,
        "devices": devices,
        "required_flag_support": flag_support,
        "source": source,
        "claim_boundary": (
            "PASS proves only pinned clean source, runnable binary and expected CLI "
            "surface. It is not model compatibility, exactness or performance."
        ),
    }
