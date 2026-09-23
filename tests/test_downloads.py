from __future__ import annotations

import pytest

from tesy.downloads import DownloadPlanError, build_download_plan


def _model() -> dict:
    return {
        "id": "fixture",
        "artifact": {
            "repository": "owner/repo",
            "revision": "0123456789012345678901234567890123456789",
            "filename": "model.gguf",
            "bytes": 123,
            "sha256": "a" * 64,
        },
    }


def test_download_plan_is_dry_run_and_pinned(tmp_path):
    destination = tmp_path / "models"
    plan = build_download_plan(_model(), destination)
    assert plan["dry_run"] is True
    assert plan["command"] == [
        "hf",
        "download",
        "owner/repo",
        "model.gguf",
        "--revision",
        "0123456789012345678901234567890123456789",
        "--local-dir",
        str(destination),
    ]


def test_download_plan_rejects_unlocked_artifact(tmp_path):
    model = _model()
    model["artifact"]["revision"] = None
    with pytest.raises(DownloadPlanError):
        build_download_plan(model, tmp_path / "models")


def test_download_plan_rejects_symlink_destination(tmp_path):
    real = tmp_path / "real"
    real.mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(real, target_is_directory=True)
    with pytest.raises(DownloadPlanError):
        build_download_plan(_model(), alias)
