from pathlib import Path
from runpy import run_path

import pytest

HERE = Path(__file__).resolve().parent
API = run_path(str(HERE / "review.py"))
G = run_path(str(HERE.parent / "grade.py"))


def test_intervals_reject_two_different_gpu_destinations():
    G["check_device_upload"]([(0, 32, 700), (32, 32, 700)], 700, 64, "bias")
    with pytest.raises(ValueError):
        G["check_device_upload"]([(0, 32, 700), (32, 32, 701)], 700, 64, "bias")
    with pytest.raises(ValueError):
        G["check_device_upload"]([(0, 32, 700)], 700, 64, "bias")


def test_mapping_lifetime_and_model_inode(tmp_path):
    row = "1000-4000 r--s 00001000 00:26 172 /model.gguf\n"
    for cut in ("load", "context", "freed"):
        (tmp_path / (cut + ".maps")).write_text(row if cut != "freed" else "")
    assert len(API["mappings"](tmp_path, "/model.gguf", 172)["load"]) == 1
    with pytest.raises(ValueError):
        API["mappings"](tmp_path, "/model.gguf", 173)
    (tmp_path / "freed.maps").write_text(row)
    with pytest.raises(ValueError):
        API["mappings"](tmp_path, "/model.gguf", 172)
