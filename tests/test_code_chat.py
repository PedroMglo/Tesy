from pathlib import Path
from runpy import run_path

import pytest

HERE = Path(__file__).resolve().parents[1] / "research/ready-experts/cpu_wave/code_chat"
WORK = run_path(HERE / "workload.py")


def test_serial_code_turn_needs_a_matching_feed_and_remaining_budget():
    events = [
        ("start",),
        ("sample", 1, 767, 123, 0),
        ("feed", 123, 2105),
        ("eos",),
        ("sample", 2, 766, 200002, 0),
        ("end", 2106),
    ]

    def trace():
        return [((0,), 7, ("start",))] + [((i,), 8, e) for i, e in enumerate(events)]

    native = dict(events=lambda _: trace(), ids_bytes=lambda v: tuple(v), digest=lambda v: v)
    seen = WORK["serial"](b"", 2, 2, 2105, 768, native)
    assert seen["sampled_sha256"] == (123, 200002) and seen["serial"] == 1
    with pytest.raises(ValueError, match="native sample/feed order"):
        WORK["serial"](b"", 2, 2, 2105, 256, native)
    events[2] = ("feed", 123, 2106)
    with pytest.raises(ValueError, match="native sample/feed order"):
        WORK["serial"](b"", 2, 2, 2105, 768, native)


def test_combination_can_pass_when_its_last_component_has_mixed_signs():
    run = run_path(HERE / "run.py")

    def arm(role, seconds):
        turn = dict(valid_s=seconds, first_final_s=seconds - 0.5, decode_s=1, prefill_s=1)
        return dict(role=role, turns=[dict(valid_s=30), turn])

    rows = [arm(role, s) for role, s in zip("RPWWPR", [10, 8, 7, 8, 7, 10], strict=True)]
    result = run["compare"](rows)
    assert result["combined_positive_both_orders"]
    assert result["decision"] == "INCONCLUSIVE_CODE_CHAT"
