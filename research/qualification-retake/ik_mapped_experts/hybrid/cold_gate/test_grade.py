import json
from copy import deepcopy
from pathlib import Path
from runpy import run_path

import pytest

G = run_path(str(Path(__file__).with_name("grade.py")))


@pytest.mark.parametrize(
    ("times", "io", "decision"),
    [
        ((9, 9), (20, 20), "GO"),
        ((9, 9), (20, 21), "INCONCLUSIVE"),
        ((9, 11), (20, 20), "INCONCLUSIVE"),
        ((10, 11), (20, 19), "NO_GO"),
    ],
)
def test_thresholds(times, io, decision):
    orders = {
        name: {
            "DIRECT": {"total_ns": 10, "reads": {"scope_B": 20}},
            "STAGED": {"total_ns": t, "reads": {"scope_B": b}},
        }
        for name, t, b in zip(G["ORDERS"], times, io, strict=True)
    }
    assert G["decide"](orders)[0] == decision


def test_reference_coldness_and_last_fence(tmp_path):
    ref = dict(sets=[dict(sha256=str(i)) for i in range(33)], payload_B=33)
    before = dict(namespace_B=0, scope_B=0, pid_B=0)
    after = dict(namespace_B=512, scope_B=512, pid_B=512)
    base = dict(
        mode="DIRECT",
        verified=[str(i) for i in range(33)],
        guards_B=8192,
        resident_before=0,
        resident_after=1,
        tensor_pages=2,
        check_ns=30,
        events_ns=[[i * 3, i * 3 + 1, i * 3 + 2] for i in range(33)],
        issued_ns=100,
        drain_ns=5,
        total_ns=105,
        before=before,
        after=after,
        delta=after,
    )
    file = tmp_path / "native.json"
    file.write_text(json.dumps(base))
    assert G["one"](file, "DIRECT", ref)["loop_ns"] == 34
    for key, value in (
        ("resident_before", 1),
        ("drain_ns", 4),
        ("verified", []),
        ("guards_B", 4096),
        ("delta", before),
        ("events_ns", [[0, 0, 1]]),
    ):
        bad = deepcopy(base)
        bad[key] = value
        file.write_text(json.dumps(bad))
        with pytest.raises(ValueError):
            G["one"](file, "DIRECT", ref)
