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


def test_monitor_receipt_identity_even_with_identical_library(tmp_path, monkeypatch):
    gate = API["monitor_authority"]
    provider = tmp_path / "real-NVML.so"
    provider.write_bytes(b"same-library")
    right, wrong = (tmp_path / n for n in ("qualified", "different"))
    for parent in (right, wrong):
        (parent / "lib").mkdir(parents=True)
        (parent / "lib/libnvidia-ml.so.1").symlink_to(provider)
    (right / "receipt.json").write_text('{"status":"PASS_CPU_CAMPAIGN_MONITOR"}')
    (wrong / "receipt.json").write_text('{"status":"PASS_STATIC_C270_C281_DRIVER_SELECTION"}')
    expected = hashlib.sha256((right / "receipt.json").read_bytes()).hexdigest()
    monkeypatch.setitem(gate.__globals__, "MONITOR_RECEIPT", expected)
    calls = []

    def probe(_):
        calls.append("probe")
        return {
            "mode": "PRIVATE_MATCHED_NVML",
            "monitor_receipt_sha256": expected,
            "kernel_driver": "pin",
        }, lambda: calls.append("stat")

    monkeypatch.setenv("LD_LIBRARY_PATH", str(wrong / "lib"))
    with pytest.raises(ValueError, match="wrong packed-service"):
        gate(None, probe)
    assert calls == []
    monkeypatch.setenv("LD_LIBRARY_PATH", str(right / "lib"))
    pre, _ = gate(None, probe)
    actual, unchanged = gate({"monitor_provider": pre}, probe)
    assert actual == pre
    assert calls.count("probe") == 2
    with pytest.raises(ValueError, match="differs from preflight"):
        gate({"monitor_provider": pre | {"kernel_driver": "foreign"}}, probe)
    (right / "receipt.json").write_text('{"status":"changed"}')
    with pytest.raises(ValueError, match="receipt changed"):
        unchanged()


@pytest.mark.parametrize("valid", [False, True])
def test_prepared_receipt_waits_for_monitor(valid, tmp_path, monkeypatch):
    from types import SimpleNamespace

    run = API["run"]
    plan = tmp_path / "fixture"
    plan.touch()
    bound = (plan, None, (1,), plan, None, {}, {}, None, None)
    fake = {
        "bind": lambda *args: None,
        "tiny_gate": lambda *args: {},
        "c55": lambda *args: ({"canonical_policy_sha256": "h"}, {}, {"cgroup": {}}, None),
        "inputs": lambda *args: bound,
    }
    monkeypatch.setitem(run.__globals__, "S", fake)
    monkeypatch.setitem(run.__globals__, "run_path", lambda *args: {"monitor_provider": object()})
    tested = []

    def monitor(prior, probe):
        tested.append(prior)
        if not valid:
            raise ValueError("monitor rejected")
        return {"mode": "TEST"}, None

    monkeypatch.setitem(run.__globals__, "monitor_authority", monitor)
    a = SimpleNamespace(
        tiny=None, tiny_sha256=None, tiny_review=None, tiny_review_sha256=None, execute=False
    )
    terminal = {"status": "FAIL_PRESERVED"}
    if valid:
        run(a, tmp_path, terminal)
        assert terminal["status"] == "PREPARED_ONLY" and terminal["monitor_provider"] == {
            "mode": "TEST"
        }
    else:
        with pytest.raises(ValueError, match="monitor rejected"):
            run(a, tmp_path, terminal)
        assert terminal["status"] == "FAIL_PRESERVED"
    assert tested == [None]
