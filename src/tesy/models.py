from __future__ import annotations

import hashlib
import json
import os
import stat
from pathlib import Path
from typing import Any


class ModelLockError(ValueError):
    pass


def default_lock_path() -> Path:
    env = os.environ.get("TESY_MODEL_LOCK")
    if env:
        return Path(env)
    cwd = Path.cwd() / "configs" / "models.lock.json"
    if cwd.exists():
        return cwd
    return Path(__file__).resolve().parents[2] / "configs" / "models.lock.json"


def load_lock(path: Path | None = None) -> dict[str, Any]:
    lock_path = (path or default_lock_path()).resolve()
    try:
        data = json.loads(lock_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ModelLockError(f"cannot read model lock {lock_path}: {exc}") from exc
    if data.get("schema") != "tesy.models.lock.v1":
        raise ModelLockError("unsupported model lock schema")
    models = data.get("models")
    if not isinstance(models, list):
        raise ModelLockError("models must be a list")
    seen: set[str] = set()
    for model in models:
        if not isinstance(model, dict):
            raise ModelLockError("model entry must be an object")
        model_id = model.get("id")
        if not isinstance(model_id, str) or not model_id:
            raise ModelLockError("each model requires a non-empty id")
        if model_id in seen:
            raise ModelLockError(f"duplicate model id: {model_id}")
        seen.add(model_id)
    return data


def get_model(lock: dict[str, Any], model_id: str) -> dict[str, Any]:
    for model in lock["models"]:
        if model["id"] == model_id:
            return model
    raise ModelLockError(f"unknown model id: {model_id}")


def sha256_file(path: Path, chunk_bytes: int = 8 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb", buffering=0) as handle:
        while True:
            chunk = handle.read(chunk_bytes)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def inspect_model_file(path: Path, with_sha256: bool = False) -> dict[str, Any]:
    resolved = path.resolve(strict=True)
    info = resolved.lstat()
    if stat.S_ISLNK(info.st_mode):
        raise ModelLockError("model path must not be a symlink")
    if not stat.S_ISREG(info.st_mode):
        raise ModelLockError("model path must be a regular file")
    result: dict[str, Any] = {
        "path": str(resolved),
        "filename": resolved.name,
        "size_bytes": info.st_size,
        "sha256": None,
    }
    if with_sha256:
        result["sha256"] = sha256_file(resolved)
    return result


def verify_model_file(model: dict[str, Any], path: Path) -> dict[str, Any]:
    expected = model.get("artifact", {})
    observed = inspect_model_file(path, with_sha256=bool(expected.get("sha256")))
    failures: list[str] = []
    expected_name = expected.get("filename")
    if expected_name and observed["filename"] != expected_name:
        failures.append(f"filename: expected {expected_name}, got {observed['filename']}")
    expected_bytes = expected.get("bytes")
    if isinstance(expected_bytes, int) and observed["size_bytes"] != expected_bytes:
        failures.append(
            f"size_bytes: expected {expected_bytes}, got {observed['size_bytes']}"
        )
    expected_sha = expected.get("sha256")
    if expected_sha and observed["sha256"] != expected_sha:
        failures.append(
            f"sha256: expected {expected_sha}, got {observed['sha256']}"
        )
    return {
        "model_id": model["id"],
        "status": "PASS" if not failures else "FAIL",
        "observed": observed,
        "failures": failures,
    }
