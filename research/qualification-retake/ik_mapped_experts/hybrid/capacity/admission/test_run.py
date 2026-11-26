import hashlib
import io
import json
from pathlib import Path
from runpy import run_path

import pytest

API = run_path(str(Path(__file__).with_name("run.py")))
S = API["S"]


@pytest.mark.parametrize(
    "phase,owners", [("E", []), ("L", [7]), ("C", [7]), ("F", []), ("F", [7]), ("exit", [])]
)
def test_authoritative_gpu_owner(phase, owners):
    API["owner"](phase, owners, 7)


@pytest.mark.parametrize(
    "phase,owners", [("E", [7]), ("L", []), ("C", [8]), ("F", [7, 8]), ("exit", [7])]
)
def test_wrong_owner_or_unreleased_context(phase, owners):
    with pytest.raises(ValueError):
        API["owner"](phase, owners, 7)


def test_deadlines_do_not_reset_from_running_samples():
    check = API["check_time"]
    check(0, {"E": 1}, 180)
    check(0, {"E": 1, "L": 100}, 190)
    check(0, {"L": 100, "C": 180}, 190)
    for marks, t in (
        ({"E": 179}, 181),
        ({"L": 90}, 181),
        ({"C": 170, "L": 100}, 181),
        ({"C": 279, "L": 220}, 281),
    ):
        with pytest.raises(ValueError):
            check(0, marks, t)


def test_model_mapping_uses_actual_device_and_inode():
    example = "3000-6000 r--s 00000000 00:37 871 /private/model.gguf\n"
    assert API["file_in_maps"](example, (0, 55, 871))
    assert not API["file_in_maps"](example, (0, 56, 871))
    assert not API["file_in_maps"](example, (0, 55, 872))
    assert not API["file_in_maps"]("4100-4200 r--p 00000000 00:00 0\n", (0, 55, 871))


def test_failure_records_the_triggering_observation():
    from types import SimpleNamespace

    log = io.StringIO()
    resource = {"gpu": {"used_mib": 7677}}
    g = API["RecordingGuard"](SimpleNamespace(check=lambda sample: "GPU_TOTAL_MEMORY"), log)
    assert g.check(resource) == "GPU_TOTAL_MEMORY"
    row = json.loads(log.getvalue())
    assert row["data"] == resource and row["phase"] == "resource_stop"


def test_incomplete_tiny_fails_before_opening_other_inputs(tmp_path):
    path = tmp_path / "receipt.json"
    path.write_text('{"status":"FAIL_PRESERVED","arms":{"RESIDENT":{"starts":1}}}')
    with pytest.raises(ValueError, match="tiny CUDA prerequisite"):
        S["tiny_gate"](
            tmp_path, hashlib.sha256(path.read_bytes()).hexdigest(), tmp_path / "absent", "0" * 64
        )


def test_endpoint_enforces_both_vram_comparators():
    f = API["vram_gate"]
    f([7600, 7675], 7676)
    f([7676], 7700)
    with pytest.raises(ValueError):
        f([7675, 7676], 7676)
    with pytest.raises(ValueError):
        f([7677], 7700)
