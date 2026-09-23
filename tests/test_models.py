from __future__ import annotations

import json

import pytest

from tesy.models import (
    ModelLockError,
    get_model,
    inspect_model_file,
    load_lock,
    verify_model_file,
)


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
            "sha256": "66e61a3d7dc6c38ef4cc4dd183733089b1e7116f894fc052558ab12b3decff8f",
        },
    }
    result = verify_model_file(model, model_file)
    assert result["status"] == "PASS"


def test_inspect_rejects_symlink(tmp_path):
    target = tmp_path / "model.gguf"
    target.write_bytes(b"tesy")
    link = tmp_path / "alias.gguf"
    link.symlink_to(target)
    with pytest.raises(ModelLockError):
        inspect_model_file(link)


def test_unknown_model_fails():
    with pytest.raises(ModelLockError):
        get_model({"models": []}, "missing")
