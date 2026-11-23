from pathlib import Path

import pytest

from tesy.vertical_capacity import (
    GIB,
    _validated_process_rows,
    build_report,
    classify_bytes,
)


def test_three_capacity_classes():
    ram = 32 * GIB
    assert classify_bytes(12 * GIB, ram) == "ENCODED_WEIGHTS_RAM_ADMISSIBLE_ONLY"
    assert classify_bytes(28 * GIB, ram) == "WORKING_SET_NEAR_HOST_BUDGET"
    assert classify_bytes(60 * GIB, ram) == "WEIGHTS_EXCEED_RAM"


def test_report_separates_observed_and_unknown():
    models = {
        "schema": "tesy.models.lock.v1",
        "models": [
            {"id": "gpt-oss-20b-mxfp4-gguf", "artifact": {"bytes": 12 * GIB}},
            {"id": "qwen3-30b-a3b-instruct-2507-q4km", "artifact": {
                "bytes": None, "revision": None, "sha256": None,
                "source_reported_size": "18.557 GB",
            }},
            {"id": "gpt-oss-120b-mxfp4", "artifact": {
                "bytes": None, "revision": None, "sha256": None,
            }, "upstream": {"source_reported_checkpoint_size": "60.8 GiB"}},
        ],
    }
    doctor = {
        "reference_check": {"status": "PASS"},
        "snapshot": {
            "virtualization": {"status": "PHYSICAL"},
            "memory": {"total_bytes": 32 * GIB},
            "gpu": {"gpus": [{"memory_total_bytes": 8 * GIB}]},
        },
    }
    rows = [{"process": {"VmRSS_bytes": 13 * GIB, "VmSwap_bytes": 0},
             "gpu": {"memory_used_bytes": GIB}}]
    report = build_report(models, doctor, rows, 50_000_000)
    assert report["installed_model"]["observed_peak_process_rss_bytes"] == 13 * GIB
    assert report["loader"]["validated_over_ram_support"] is False
    assert report["candidates"][1]["exact_artifact_bytes"] is None
    assert "GGUF_ARTIFACT_UNKNOWN" in report["candidates"][2]["classification"]


def test_terminal_rows_do_not_prove_swap_free(tmp_path: Path):
    path = tmp_path / "samples.jsonl"
    path.write_text('{"process":{},"gpu":{"status":"OK"}}\n')
    with pytest.raises(ValueError, match="missing process samples"):
        _validated_process_rows(path)
