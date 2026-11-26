"""A phase loss is charged to its order, even when the other phases improve."""

from pathlib import Path
from runpy import run_path

G = run_path(str(Path(__file__).with_name("grade.py")))


def test_both_signs_and_cleanup():
    def row(prefill, teacher, cleanup):
        return {"native_ns": dict(prefill=prefill, teacher=teacher, cleanup=cleanup)}

    arms = {"D1": row(10, 10, 2), "D2": row(15, 10, 2), "P1": row(6, 8, 4), "P2": row(7, 14, 2)}
    assert G["compare"](arms) == {
        "decision": "GO_NATURAL_WORKLOAD",
        "direct_minus_pread_ns": [
            {"prefill": 4, "teacher": 2, "cleanup": -2, "total": 4},
            {"prefill": 8, "teacher": -4, "cleanup": 0, "total": 4},
        ],
    }
    arms["P2"] = row(7, 14, 7)
    assert G["compare"](arms)["decision"] == "INCONCLUSIVE"
    arms["P1"] = row(6, 8, 8)
    assert G["compare"](arms)["decision"] == "NO_GO_COLD_C110"
