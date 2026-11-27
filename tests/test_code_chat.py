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


def test_first_final_can_span_native_code_pieces_with_whitespace():
    lookup = run_path(HERE / "lookup.py")
    intro = lookup["INTRO"]
    text = [*intro, b"def", b" ", b"rle_pairs", b""]
    assert lookup["first_final"](text, [b"def ", b"rle_pairs"]) == len(intro) + 1
    assert lookup["first_final"](text, [b"def ambiguous"]) is None
    assert lookup["first_final"]([*intro, *text], [b"def ", b"rle_pairs"]) is None


def test_replacing_one_block_conserves_ordinary_intervals_and_charges_crossing_first_final():
    lookup = run_path(HERE / "lookup.py")
    steps = [
        dict(at=1, emitted=3, accepted=2, proposal=[6, 7]),
        dict(at=4, emitted=1, accepted=0, proposal=[]),
    ]
    priced = lookup["budget"](steps, [100, 110, 121, 131, 144], 2, 45)
    assert (priced["observed_service_replaced_ns"], priced["ordinary_ns"]) == (31, 13)
    assert priced["decode_ns_if_all_blocks_free"] == 14
    assert (
        priced["blocks_to_first_final"] == 1 and priced["native_replaced_to_first_final_ns"] == 21
    )
    steps[1]["at"] = 3
    with pytest.raises(ValueError, match="contiguous"):
        lookup["budget"](steps, [100, 110, 121, 131, 144], 2, 45)


def test_public_code_conversation_and_ablation_remain_reproducible_without_the_model():
    review = run_path(HERE / "review.py")
    result = review["read"](HERE / "code-chat.json")
    review["check_public"](result)
    replay = review["read"](HERE / "lookup.json")
    assert replay["program_sha256"] == review["sha"](HERE / "lookup.py")
    assert replay["physical_sha256"] == review["sha"](HERE / "code-chat.json")
    assert len(replay["arms"]) == len(result["arms"]) == 6
    for arm, physical in zip(replay["arms"], result["arms"], strict=True):
        assert arm["receipt_sha256"] == physical["receipt_sha256"]
        assert (
            arm["server_decode_ns"]
            == arm["decode_ns_if_all_blocks_free"] + arm["observed_service_replaced_ns"]
        )
        assert arm["samples"] == physical["turns"][1]["output"]


def test_independent_gemv_native_receipt_keeps_both_controls_and_the_real_failure():
    operator = run_path(HERE / "executor.py")
    result = operator["json"].loads((HERE / "executor-result.json").read_bytes())
    assert result["protocol_sha256"] == operator["sha"]((HERE / "executor.md").read_bytes())
    assert result["program_sha256"] == operator["sha"]((HERE / "executor.py").read_bytes())
    assert result["source_sha256"] == operator["SOURCES"]
    assert set(result["builds"]) == {"avx2", "scalar"}
    for label, encoded in operator["fixture"]().items():
        assert len(encoded) == 34 and result["input_sha256"][label] == operator["sha"](encoded)
    for arm in result["builds"].values():
        for kind in ("row", "gemv", "gemv_permuted_input"):
            assert arm["cases"]["constant"][kind]["numerical_mismatches"] == 0
        for kind in ("distinct", "first_real_gate"):
            assert arm["cases"][kind]["gemv"]["numerical_mismatches"] > 0
            assert arm["cases"][kind]["gemv_permuted_input"]["numerical_mismatches"] == 0
    assert result["decision"] == "NO_GO_AS_SHIPPED_EXPERT_GEMV"
