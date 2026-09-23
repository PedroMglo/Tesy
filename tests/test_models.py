from __future__ import annotations

import json

import pytest

from tesy.models import ModelLockError, get_model, load_lock, verify_model_file


def test_lock_rejects_duplicate_ids(tmp_path):
    path = tmp_path / "models.json"
    path.write_text(
        json.dumps(
            {
                "schema": "tesy.models.lock.v1",
                "models": [{"id": "a"}, {"id": "a"}],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ModelLockError):
        load_lock(path)


def test_verify_uses_sha_when_locked(tmp_path):
    model_file = tmp_path / "model.gguf"
    model_file.write_bytes(b"tesy")
    model = {
        "id": "fixture",
        "artifact": {
            "filename": "model.gguf",
            "bytes": 4,
            "sha256": "2d6c2bfc66c8caa1533530a7c4a5eea5e8d3d334616e3657d00f16a73d931466",
        },
    }
    result = verify_model_file(model, model_file)
    assert result["status"] == "PASS"


def test_unknown_model_fails():
    with pytest.raises(ModelLockError):
        get_model({"models": []}, "missing")
