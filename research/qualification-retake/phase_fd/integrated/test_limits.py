import importlib.util
from pathlib import Path
from types import SimpleNamespace

SPEC = importlib.util.spec_from_file_location("pfj_bounds", Path(__file__).with_name("limits.py"))
bounds = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bounds)


def test_two_thresholds_on_same_clock_and_exclusive_union():
    def event(kind, when, call):
        return SimpleNamespace(kind=kind, ns=int(when * 10**9), a=1, call=call)

    rows = [
        event(9, 2, 1),
        event(19, 3, 1),
        event(20, 4, 1),
        event(23, 5, 1),
        event(9, 9, 3),
        event(19, 10, 3),
        event(20, 12, 3),
        event(23, 13, 3),
    ]
    calls = [{"start_ns": 2 * 10**9}, {"end_ns": 13 * 10**9}]
    row = {"first_final_s": 10.5, "valid_wall_s": 13, "decode_s": 9.5}
    raw = {
        "request_started_monotonic": 1,
        "request_ended_monotonic": 14,
        "stream_metrics": {"first_final_content_chunk_s": 10.5},
        "request_wall_s": 13,
    }
    out = bounds.joint_clock(rows, calls, raw, row)
    assert out["unions"]["remap"] == {
        "until_first_final_ns": 5501000000,
        "in_decode_ns": 4000000000,
    }
    assert out["unions"]["wait"]["until_first_final_ns"] == 2501000000
    assert out["fractions"]["remap"]["joint_minimum_fraction"] > 0.416
    assert out["fractions"]["remap"]["joint_minimum_fraction"] < 0.417


def test_threshold_equality_leaves_only_headroom():
    assert bounds.scenario(100, 30, 69)["decision"] == "NO_GO_FIXED_REMAINDER"
    assert bounds.scenario(100, 30, 70)["decision"] == "HEADROOM_ONLY"
