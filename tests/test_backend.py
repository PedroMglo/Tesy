from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from tesy.backend import BackendError, load_backend_lock, probe_llama_cpp


def _write_fake_backend(path: Path) -> None:
    path.write_text(
        """#!/usr/bin/env python3
import sys

if "--version" in sys.argv:
    print("version: 0.0.0 (build 1, commit aaaaaaaa)")
    raise SystemExit(0)
if "--list-devices" in sys.argv:
    print("CUDA0: fake")
    raise SystemExit(0)
if "--help" in sys.argv:
    print("--cpu-moe --n-cpu-moe --lazy-mode --override-tensor --n-gpu-layers")
    raise SystemExit(0)
raise SystemExit(2)
""",
        encoding="utf-8",
    )
    path.chmod(0o755)


def test_backend_lock_rejects_duplicate_ids(tmp_path):
    lock = tmp_path / "backends.json"
    lock.write_text(
        json.dumps(
            {
                "schema": "tesy.backends.lock.v1",
                "backends": [{"id": "x"}, {"id": "x"}],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(BackendError):
        load_backend_lock(lock)


def test_probe_without_source_is_inconclusive(tmp_path, monkeypatch):
    binary = tmp_path / "llama-cli"
    _write_fake_backend(binary)
    lock = tmp_path / "backends.json"
    lock.write_text(
        json.dumps(
            {
                "schema": "tesy.backends.lock.v1",
                "backends": [
                    {
                        "id": "llama-cpp-stock",
                        "commit": "a" * 40,
                        "expected_features_to_probe": [
                            "--cpu-moe",
                            "--n-cpu-moe",
                            "--lazy-mode",
                            "--override-tensor",
                            "--n-gpu-layers",
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("TESY_BACKEND_LOCK", str(lock))
    result = probe_llama_cpp(binary)
    assert result["status"] == "INCONCLUSIVE"
    assert all(result["required_flag_support"].values())


def test_probe_rejects_symlink(tmp_path, monkeypatch):
    binary = tmp_path / "llama-cli-real"
    _write_fake_backend(binary)
    link = tmp_path / "llama-cli"
    link.symlink_to(binary)
    lock = tmp_path / "backends.json"
    lock.write_text(
        json.dumps(
            {
                "schema": "tesy.backends.lock.v1",
                "backends": [
                    {
                        "id": "llama-cpp-stock",
                        "commit": "a" * 40,
                        "expected_features_to_probe": [],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("TESY_BACKEND_LOCK", str(lock))
    with pytest.raises(BackendError):
        probe_llama_cpp(link)


def test_fake_backend_is_executable(tmp_path):
    binary = tmp_path / "llama-cli"
    _write_fake_backend(binary)
    assert os.access(binary, os.X_OK)


def test_probe_rejects_binary_commit_mismatch(tmp_path, monkeypatch):
    binary = tmp_path / "llama-cli"
    _write_fake_backend(binary)
    lock = tmp_path / "backends.json"
    lock.write_text(
        json.dumps(
            {
                "schema": "tesy.backends.lock.v1",
                "backends": [
                    {
                        "id": "llama-cpp-stock",
                        "commit": "b" * 40,
                        "expected_features_to_probe": [
                            "--cpu-moe",
                            "--n-cpu-moe",
                            "--lazy-mode",
                            "--override-tensor",
                            "--n-gpu-layers",
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("TESY_BACKEND_LOCK", str(lock))
    result = probe_llama_cpp(binary)
    assert result["status"] == "FAIL"
    assert result["binary"]["reported_commit"] == "aaaaaaaa"
    assert result["binary"]["commit_match"] is False
